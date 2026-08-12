from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

from agent_bridge import AutoTurn, AgentDriver, TurnResult, TurnScope, build_turn_context, make_tool_executor
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
            playback_ack_timeout_s=0.2,
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


async def test_turn_registry_deduplicates_one_terminal_proposal():
    core = minimal_core()
    calls = 0

    async def execute(_name, _arguments):
        nonlocal calls
        calls += 1
        core.store.update_lesson(stage="RUNNING")
        return {"ok": True, "calls": calls}

    core.turn_registry.register(
        "secret", execute, student_id="s01", moves={"opaque-next": "next_activity"}
    )
    args = {"turn_id": "secret", "move_id": "opaque-next", "teacher_line": "Let's continue."}
    first = await core.turn_registry.invoke("classroom_propose_move", args)
    replay = await core.turn_registry.invoke("classroom_propose_move", args)

    assert first == replay == {"ok": True, "calls": 1}
    assert calls == 1
    with pytest.raises(TurnRejected, match="terminal proposal already used"):
        await core.turn_registry.invoke(
            "classroom_propose_move",
            {**args, "teacher_line": "Try the next one."},
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

    core.turn_registry.register(
        "interrupt-me", execute, student_id="s01", moves={"repeat": "repeat_activity"}
    )
    invocation = asyncio.create_task(
        core.turn_registry.invoke("classroom_propose_move", {
            "turn_id": "interrupt-me",
            "move_id": "repeat",
            "teacher_line": "Let's try once more.",
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
        assert names == {"classroom_propose_move"}
        assert "classroom_say" not in names
        assert all("turn_id" in tool["inputSchema"]["required"] for tool in TOOLS)


class ProposalHermesFake:
    streams_text_as_voice = True

    def __init__(self, core, teacher_line="Let's continue."):
        self.core = core
        self.teacher_line = teacher_line
        self.prepared = None

    def prepare_turn(self, turn_id):
        self.prepared = turn_id

    async def turn(self, ctx):
        move_id = ctx.available_actions[0].id
        result = await self.core.turn_registry.invoke(
            "classroom_propose_move",
            {
                "turn_id": self.prepared,
                "move_id": move_id,
                "teacher_line": self.teacher_line,
            },
        )
        assert result["ok"] is True and result["applied"] is False
        yield SimpleNamespace(type="text_delta", text=self.teacher_line)
        yield SimpleNamespace(type="done", reason="complete", detail=None, usage=None)


async def test_driver_keeps_proposal_pending_until_physical_playback_ack():
    core = minimal_core()
    moved = []

    async def start(index):
        moved.append(index)

    core.runner.start = start
    driver = AgentDriver(core, lambda _executor: ProposalHermesFake(core))
    core.agent_driver = driver
    task = asyncio.create_task(driver.take_turn(student_id="s01"))
    for _ in range(10):
        await asyncio.sleep(0)
        if driver._speech_turn_id:
            break
    assert moved == []
    assert driver.note_playback_result(driver._speech_turn_id, "completed") is True
    result = await task
    assert result.applied is True and result.chose == "repeat_activity"
    assert moved == [0]
    assert result.said == ["Let's continue."]


async def test_failed_agent_playback_discards_pending_move():
    core = minimal_core()
    moved = []

    async def start(index):
        moved.append(index)

    core.runner.start = start
    driver = AgentDriver(core, lambda _executor: ProposalHermesFake(core))
    core.agent_driver = driver
    task = asyncio.create_task(driver.take_turn(student_id="s01"))
    for _ in range(10):
        await asyncio.sleep(0)
        if driver._speech_turn_id:
            break
    driver.note_playback_result(driver._speech_turn_id, "failed")
    result = await task
    assert result.applied is False
    assert moved == []


async def test_inference_budget_ends_before_independent_playback_ack_budget():
    core = minimal_core()
    moved = []

    async def start(index):
        moved.append(index)

    core.runner.start = start
    driver = AgentDriver(core, lambda _executor: ProposalHermesFake(core))
    core.agent_driver = driver
    gate = AutoTurn(core, timeout_s=0.01)
    task = asyncio.create_task(gate(core.runner.current, "wrong", {}))
    for _ in range(20):
        await asyncio.sleep(0)
        if driver._speech_turn_id:
            break
    # Exceed the model budget while the authored teacher line is queued. This
    # is physical playback latency, not a provider timeout.
    await asyncio.sleep(0.03)
    assert task.done() is False
    assert gate.timeouts == 0
    assert driver.note_playback_result(driver._speech_turn_id, "completed") is True
    assert await task == "repeat_activity"
    assert moved == [0]


@pytest.mark.parametrize(
    "line",
    ["Correct!", "Well done.", "https://bad.example", "<|ACT {}|>", "Mai, continue."],
)
async def test_truth_identity_and_markup_teacher_lines_are_rejected(line):
    core = minimal_core()
    core.session_controller = SimpleNamespace(
        roster={"s01": SimpleNamespace(display_name="Mai")}
    )
    result = TurnResult()
    execute = make_tool_executor(core, result)
    answer = await execute(
        "classroom_propose_move",
        {"_action_id": "repeat_activity", "teacher_line": line},
    )
    assert answer["ok"] is False
    assert result.pending_action is None


class ErrorHermesFake:
    streams_text_as_voice = True

    def prepare_turn(self, _turn_id):
        pass

    async def turn(self, _ctx):
        yield SimpleNamespace(type="done", reason="error", detail="sidecar down", usage=None)


async def test_driver_marks_done_error_as_operational_not_a_bad_proposal():
    core = minimal_core()
    driver = AgentDriver(core, lambda _executor: ErrorHermesFake())

    result = await driver.take_turn(student_id="s01")

    assert result.operational_error is True
    assert result.rejected == "agent reported error"
