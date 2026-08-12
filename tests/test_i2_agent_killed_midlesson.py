"""I2 — kill the agent mid-lesson. RELEASE GATE.

Three separate claims, tested separately so a failure names itself:

1. **The class continues.** The lesson must reach the end after the agent dies.
2. **Nothing hangs and nothing crashes.** A turn against a dead endpoint must
   fail fast and leave core serving.
3. **The mode degrades.** This is the one that has already bitten this project
   once — "the facilitator console reported a healthy agent while the agent was
   unreachable" — and it is the reason the mode is specified as a *measurement*
   (PROTOCOL §7) rather than a setting.

Claim 3 is tested as a causal link in both directions, not as a snapshot. A
system that reports OFFLINE unconditionally would pass "mode is not FULL after
the agent dies" while being exactly as blind as one that reports FULL
unconditionally.

The agent is killed by killing the process that serves the model endpoint —
by PID, from the port we spawned it on. Never `pkill -f`.
"""

from __future__ import annotations

import asyncio
import time

import pytest

from harness import BusClient
from harness import llm_script as script

pytestmark = pytest.mark.slow


async def _wait_for_mode(core, wanted: set[str], timeout: float) -> str:
    deadline = time.monotonic() + timeout
    mode = core.health()["mode"]
    while time.monotonic() < deadline:
        mode = core.health()["mode"]
        if mode in wanted:
            return mode
        await asyncio.sleep(0.5)
    return mode


@pytest.mark.itest(id="I2", title="Agent killed mid-lesson: class continues, mode degrades", gate=True)
async def test_class_continues_after_the_agent_is_killed(core, llm, stack):
    lesson = core.lesson()
    activity_ids = [a["id"] for a in lesson["activities"]]

    client = BusClient(core.ws)
    await client.connect()

    # The agent is alive and driving before we touch anything.
    core.start_lesson(0)
    info = core.agent_actions()
    llm.script(
        [script.tool_call("classroom_choose_next", {"state_version": info["stateVersion"], "action_id": "next_activity"})]
    )
    warm = core.agent_turn()
    assert warm["applied"] is True, f"the agent was not driving before the kill: {warm}"

    # ── the agent dies, mid-lesson ───────────────────────────────────────
    # Everything below is scanned from `mark`, not from the start of the
    # connection: the warm-up turn above already put a vocabulary scene on the
    # board, and a wait that matches it would race ahead of the lesson.
    mark = client.cursor()
    core.start_lesson(0)
    await client.wait_for_scene("vocabulary", timeout=45, since=mark)
    llm.stop()
    assert not llm.alive()

    # ── the lesson keeps running, on its own, to the end ─────────────────
    choice = await client.wait_for_scene("choice", timeout=60, since=mark)
    assert choice["props"]["options"], "the board went blank after the agent died"
    await client.choose("cat")
    await client.wait_for(
        "lesson.position",
        timeout=45,
        since=mark,
        predicate=lambda e: e["payload"]["activityIndex"] == activity_ids.index("q_legs"),
    )
    await client.choose("two")
    done = await client.wait_for(
        "lesson.position",
        timeout=60,
        since=mark,
        predicate=lambda e: e["payload"]["stage"] == "DONE",
    )
    assert done["payload"]["stage"] == "DONE"

    # ── nothing crashed ──────────────────────────────────────────────────
    client.assert_clean()
    assert client.closed_code is None, f"core dropped the stage socket: {client.closed_code}"
    assert core.health()["status"] == "ok"
    assert core.alive(), "the core process died with the agent"
    await client.close()

    stack.restart_llm()


@pytest.mark.itest(id="I2", title="Agent killed mid-lesson: class continues, mode degrades", gate=True)
async def test_agent_turn_fails_fast_when_the_agent_is_dead(core, llm, stack):
    core.start_lesson(0)
    llm.stop()

    t0 = time.monotonic()
    result = core.agent_turn(timeout=45)
    elapsed = time.monotonic() - t0

    assert result["applied"] is False
    assert result["rejected"], "a turn against a dead model endpoint reported success"
    assert elapsed < 20, f"a dead agent held the turn for {elapsed:.1f}s — a class was waiting"
    assert core.health()["status"] == "ok"
    core.control("pause")
    stack.restart_llm()


@pytest.mark.itest(id="I2", title="Agent killed mid-lesson: class continues, mode degrades", gate=True)
async def test_mode_tracks_agent_health(probing_core, llm, stack):
    """The mode must be a measurement of the agent, in both directions.

    Runs on its own core with a live probe interval; the shared one has probing
    turned down so that every other test's mode is an input, not a race.
    """
    core = probing_core
    core.start_lesson(0)
    llm.script([script.text("hello")])

    # Probes run every 5s in the test configuration (CORE_PROBE_INTERVAL_S).
    healthy_mode = await _wait_for_mode(core, {"FULL"}, timeout=20)
    assert healthy_mode == "FULL", (
        f"core reports mode={healthy_mode} while the agent is wired and answering in "
        "milliseconds. PROTOCOL §7 makes the mode a measurement of agent latency; "
        "a mode that never reflects a healthy agent cannot reflect a dead one either."
    )

    llm.stop()
    degraded = await _wait_for_mode(core, {"DEGRADED", "OFFLINE"}, timeout=30)
    assert degraded in ("DEGRADED", "OFFLINE"), (
        f"the agent is unreachable and core still reports mode={degraded}"
    )

    stack.restart_llm()
    core.control("pause")
