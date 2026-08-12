from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from agent_bridge import AgentDriver, TurnResult, TurnScope, build_turn_context, make_tool_executor
from app import ConversationCoordinator
from bright_contracts import Activity
from bus import EventBus
from mcp_server import TOOLS, TurnRegistry, TurnRejected, build_mcp_router
from state import StateStore


class FakeDB:
    def get_student(self, _student_id):
        return {"name": "Mai", "skills": {}}

    def recall(self, *_args, **_kwargs):
        return []


def minimal_core():
    store = StateStore(mode="FULL")
    activity = Activity(id="a1", scene="text", props={"text": "hello"})
    runner = SimpleNamespace(
        activities=[activity],
        current=activity,
        index=0,
        entry_counts={"a1": 1},
        _generation=4,
    )
    core = SimpleNamespace(
        store=store,
        runner=runner,
        student_id="s01",
        lesson=None,
        db=FakeDB(),
        settings=SimpleNamespace(
            agent_context_policy="hosted-minimal",
            agent_turn_timeout_s=0.2,
            agent_greeting_timeout_s=0.2,
        ),
        conversations=ConversationCoordinator(),
    )
    core.conversations.begin("session-1")
    core.bus = EventBus(lambda: store.state_version)
    core.cancel_speech = lambda speech_turn_id, reason="superseded": core.bus.publish(
        "speech.cancel", {"speechTurnId": speech_turn_id, "reason": reason}
    )
    core.turn_registry = TurnRegistry(core, default_ttl_s=1)
    return core


async def test_turn_registry_deduplicates_a_mutation_after_it_moves_state():
    core = minimal_core()
    calls = 0

    async def execute(_name, _arguments):
        nonlocal calls
        calls += 1
        core.store.update_lesson(stage="RUNNING")
        return {"ok": True, "calls": calls}

    core.turn_registry.register("secret", execute, student_id="s01")
    args = {"turn_id": "secret", "state_version": 0, "action_id": "next_activity"}
    first = await core.turn_registry.invoke("classroom_choose_next", args)
    replay = await core.turn_registry.invoke("classroom_choose_next", args)

    assert first == replay == {"ok": True, "calls": 1}
    assert calls == 1
    with pytest.raises(TurnRejected, match="stale"):
        await core.turn_registry.invoke(
            "classroom_choose_next",
            {**args, "action_id": "repeat_activity"},
        )


async def test_turn_registry_rejects_wrong_learner_and_retired_turn():
    core = minimal_core()

    async def execute(_name, _arguments):
        return {"ok": True}

    core.turn_registry.register("secret", execute, student_id="s01")
    core.student_id = "s02"
    with pytest.raises(TurnRejected, match="learner"):
        await core.turn_registry.invoke("classroom_get_state", {"turn_id": "secret"})
    core.turn_registry.retire("secret")
    with pytest.raises(TurnRejected, match="unknown or expired"):
        await core.turn_registry.invoke("classroom_get_state", {"turn_id": "secret"})


async def test_retiring_turn_cancels_an_inflight_tool_before_late_mutation():
    core = minimal_core()
    entered = asyncio.Event()
    mutated = False

    async def execute(_name, _arguments):
        nonlocal mutated
        entered.set()
        await asyncio.sleep(60)
        mutated = True

    core.turn_registry.register("interrupt-me", execute, student_id="s01")
    invocation = asyncio.create_task(
        core.turn_registry.invoke("classroom_choose_next", {
            "turn_id": "interrupt-me",
            "state_version": 0,
            "action_id": "repeat_activity",
        })
    )
    await entered.wait()
    core.turn_registry.retire("interrupt-me")
    with pytest.raises(asyncio.CancelledError):
        await invocation
    assert mutated is False


def test_hosted_context_scrubs_display_subtitle_but_local_keeps_it():
    core = minimal_core()
    core.store.set_overlay(subtitle="Mai said the raw sentence")

    hosted = build_turn_context(core, student_id="s01", context_policy="hosted-minimal")
    local = build_turn_context(core, student_id="s01", context_policy="local-trusted")

    assert hosted.scene.overlay.subtitle is None
    assert hosted.lesson.current_student_id is None
    assert local.scene.overlay.subtitle == "Mai said the raw sentence"


async def test_hosted_context_cannot_recall_learner_notes_through_mcp_executor():
    core = minimal_core()
    execute = make_tool_executor(
        core,
        TurnResult(),
        lambda: TurnScope(student_id="s01", context_policy="hosted-minimal"),
    )

    result = await execute("classroom_recall", {"query": "anything", "k": 3})

    assert result == {
        "ok": False,
        "reason": "recall unavailable for this context policy",
    }


async def test_mcp_is_authenticated_and_never_exposes_classroom_say():
    core = minimal_core()
    app = FastAPI()
    app.include_router(build_mcp_router(lambda: core, "mcp-secret"))
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://core") as client:
        denied = await client.post(
            "/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list"}
        )
        assert denied.status_code == 401
        response = await client.post(
            "/mcp",
            headers={"Authorization": "Bearer mcp-secret"},
            json={"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
        )
        names = {tool["name"] for tool in response.json()["result"]["tools"]}
        assert names == {
            "classroom_get_state",
            "classroom_choose_next",
            "classroom_record_observation",
            "classroom_recall",
        }
        assert "classroom_say" not in names
        assert all("turn_id" in tool["inputSchema"]["required"] for tool in TOOLS)


class StreamingHermesFake:
    streams_text_as_voice = True

    def __init__(self):
        self.prepared = None

    def prepare_turn(self, turn_id):
        self.prepared = turn_id

    async def turn(self, _ctx):
        assert self.prepared and self.prepared.startswith("bright-")
        yield SimpleNamespace(type="text_delta", text="Good ")
        yield SimpleNamespace(type="text_delta", text="work!")
        yield SimpleNamespace(type="done", reason="complete", detail=None, usage=None)


async def test_driver_publishes_one_correlated_stream_and_retires_capability():
    core = minimal_core()
    fake = StreamingHermesFake()
    driver = AgentDriver(core, lambda _executor: fake)

    result = await driver.take_turn(student_id="s01")

    types = [frame["type"] for frame in core.bus.history]
    assert types == [
        "speech.turn.started",
        "speech.text.delta",
        "speech.text.delta",
        "speech.turn.ended",
    ]
    starts = [frame for frame in core.bus.history if frame["type"] == "speech.turn.started"]
    assert len(starts) == 1
    turn_id = starts[0]["payload"]["speechTurnId"]
    assert all(
        frame["payload"].get("speechTurnId") == turn_id
        for frame in core.bus.history
        if frame["type"].startswith("speech.")
    )
    assert result.said == ["Good work!"]
    assert fake.prepared not in core.turn_registry._turns


class BlockingHermesFake(StreamingHermesFake):
    async def turn(self, _ctx):
        yield SimpleNamespace(type="text_delta", text="Wait")
        await asyncio.sleep(60)


async def test_cancelling_driver_cancels_the_exact_open_speech_turn_once():
    core = minimal_core()
    driver = AgentDriver(core, lambda _executor: BlockingHermesFake())
    task = asyncio.create_task(driver.take_turn(student_id="s01"))
    await asyncio.sleep(0)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    ended = [frame for frame in core.bus.history if frame["type"] == "speech.turn.ended"]
    cancelled = [frame for frame in core.bus.history if frame["type"] == "speech.cancel"]
    assert len(ended) == len(cancelled) == 1
    assert ended[0]["payload"]["status"] == "cancelled"
    assert ended[0]["payload"]["speechTurnId"] == cancelled[0]["payload"]["speechTurnId"]


async def test_driver_refuses_to_cancel_a_different_speech_turn():
    core = minimal_core()
    driver = AgentDriver(core, lambda _executor: BlockingHermesFake())
    task = asyncio.create_task(driver.take_turn(student_id="s01"))
    await asyncio.sleep(0)

    assert driver.cancel_speech_turn("not-the-active-turn", "barge") is False
    assert not [f for f in core.bus.history if f["type"] == "speech.cancel"]

    assert driver.cancel_speech_turn(driver._speech_turn_id, "barge") is True
    with pytest.raises(asyncio.CancelledError):
        await task
    cancelled = [f for f in core.bus.history if f["type"] == "speech.cancel"]
    assert len(cancelled) == 1


class TwoDeltaHermesFake(StreamingHermesFake):
    def __init__(self, release):
        super().__init__()
        self.release = release

    async def turn(self, _ctx):
        yield SimpleNamespace(type="text_delta", text="first")
        await self.release.wait()
        yield SimpleNamespace(type="text_delta", text=" stale")
        yield SimpleNamespace(type="done", reason="complete", detail=None, usage=None)


async def test_generation_takeover_stops_late_deltas_and_cancels_exact_turn():
    core = minimal_core()
    release = asyncio.Event()
    driver = AgentDriver(core, lambda _executor: TwoDeltaHermesFake(release))
    task = asyncio.create_task(driver.take_turn(student_id="s01"))
    await asyncio.sleep(0)
    core.runner._generation += 1
    release.set()
    result = await task

    deltas = [
        frame["payload"]["delta"]
        for frame in core.bus.history
        if frame["type"] == "speech.text.delta"
    ]
    assert deltas == ["first"]
    assert "generation changed" in (result.rejected or "")
    ended = [frame for frame in core.bus.history if frame["type"] == "speech.turn.ended"]
    cancelled = [frame for frame in core.bus.history if frame["type"] == "speech.cancel"]
    assert len(ended) == len(cancelled) == 1
    assert ended[0]["payload"]["speechTurnId"] == cancelled[0]["payload"]["speechTurnId"]


class ErrorHermesFake(StreamingHermesFake):
    async def turn(self, _ctx):
        yield SimpleNamespace(type="done", reason="error", detail="sidecar down", usage=None)


async def test_driver_marks_done_error_as_operational_not_a_bad_proposal():
    core = minimal_core()
    driver = AgentDriver(core, lambda _executor: ErrorHermesFake())

    result = await driver.take_turn(student_id="s01")

    assert result.operational_error is True
    assert result.rejected == "agent reported error"
