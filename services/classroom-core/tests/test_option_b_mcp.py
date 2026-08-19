from __future__ import annotations

import asyncio
from types import SimpleNamespace

import httpx
import pytest
from fastapi import FastAPI

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


async def test_turn_registry_replays_a_repeated_mutation_instead_of_doing_it_twice():
    """A retried tool call must not teach the same thing twice.

    Hermes retries on a dropped stream, so the same `write_board` can arrive
    again with identical arguments. Replaying the first answer is what keeps a
    network hiccup from writing the board twice, or -- far worse on the
    equivalent path -- recording the same evidence twice against one child.

    This used to be asserted against `classroom_propose_move`, which
    `tools/call` rejects before the registry ever sees it, so it proved nothing
    about anything that can actually happen.
    """
    core = minimal_core()
    calls = 0

    async def execute(_name, _arguments):
        nonlocal calls
        calls += 1
        core.store.update_lesson(stage="RUNNING")
        return {"ok": True, "calls": calls}

    core.turn_registry.register("secret", execute, student_id="s01")
    args = {"turn_id": "secret", "text": "# Hello"}

    first = await core.turn_registry.invoke("write_board", args)
    replay = await core.turn_registry.invoke("write_board", args)

    assert first == replay == {"ok": True, "calls": 1}
    assert calls == 1, "the second arrival must be answered from the first result"

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
            "read_library",
            "search_library",
            "write_board",
            "read_board",
            "show_image",
            "show_exercise",
            "play_clip",
            "plan",
            "say",
            "record_evidence",
        }
        assert "classroom_say" not in names
        assert all("turn_id" in tool["inputSchema"]["required"] for tool in TOOLS)
