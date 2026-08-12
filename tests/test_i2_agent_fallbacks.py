"""I2 — every non-ideal agent path falls back to the authored branch.

`/dev/agent/turn` (which I4 and I5 use) is the *manual* path. This file uses
the runtime one: `AutoTurn`, the decision gate the runner consults after every
graded outcome. It is the path a real class actually runs through, and its
contract is the one NS-1 rests on —

    slow · crashed · illegal action · stale version · busy · mode ≠ FULL
        → all the same answer: take the branch the author wrote.

Each case is driven by scripting the model endpoint into that exact failure and
then checking the lesson went where `lesson_run.json` says it should.
"""

from __future__ import annotations

import asyncio

import pytest

from harness import BusClient
from harness import llm_script as script

pytestmark = pytest.mark.slow

#: q_meow --wrong--> help_meow (index 3) is the authored branch under test.
Q_MEOW = 2
HELP_MEOW = 3
Q_LEGS = 4


def _pin_full(core) -> None:
    """The gate only runs in FULL (PROTOCOL §7).

    Pinned rather than waited for: reaching FULL naturally needs two good
    probes at the probe interval, and paying that in every test here would
    triple the suite's runtime to re-prove something `test_mode_tracks_agent_health`
    already proves once. A healthy probe keeps it there.
    """
    core.set_mode("FULL", "pinned by the I2 fallback matrix")


async def _answer_and_settle(core, option: str = "dog", settle: float = 9.0) -> int:
    assert core.health()["mode"] == "FULL", "the gate cannot run outside FULL"
    core.interaction("interaction.choice", {"optionId": option})
    await asyncio.sleep(settle)
    return core.state()["runner"]["index"]


@pytest.mark.parametrize(
    ("name", "responses"),
    [
        ("agent hangs past its turn budget", [script.slow(30, script.text("too late"))]),
        ("agent returns HTTP 500", [script.http_error(500)]),
        ("agent returns HTTP 401", [script.http_error(401, "bad key")]),
        ("agent emits an illegal action_id", [
            script.tool_call(
                "classroom_choose_next",
                {"state_version": "__STATE_VERSION__", "action_id": "goto:nowhere"},
            )
        ]),
        ("agent emits a stale state_version", [
            script.tool_call(
                "classroom_choose_next", {"state_version": 1, "action_id": "next_activity"}
            )
        ]),
        ("agent emits unparseable tool arguments", [
            {"chunks": [{"tool": {"index": 0, "id": "c1", "name": "classroom_choose_next",
                                  "args": "{not json"}}], "finish": "tool_calls"}
        ]),
        ("agent says nothing at all", [script.text("")]),
    ],
)
@pytest.mark.itest(id="I2", title="Agent killed mid-lesson: class continues, mode degrades", gate=True)
async def test_broken_agent_falls_back_to_the_authored_branch(core, llm, name, responses):
    core.start_lesson(Q_MEOW)
    llm.script(responses, non_stream={"content": "ok"})
    _pin_full(core)

    index = await _answer_and_settle(core, "dog")
    assert index == HELP_MEOW, (
        f"{name}: the lesson went to activity {index}; the authored `wrong` branch "
        f"for q_meow is help_meow ({HELP_MEOW}). A broken agent must not change "
        "where the class goes."
    )
    core.control("pause")


@pytest.mark.itest(id="I2", title="Agent killed mid-lesson: class continues, mode degrades", gate=True)
async def test_a_healthy_agent_can_actually_change_the_branch(core, llm):
    """Positive control for the whole file.

    Without this, every case above would pass on a system where the gate is
    never consulted at all — which is indistinguishable from a perfect
    fallback, and is not the same thing.
    """
    core.start_lesson(Q_MEOW)
    llm.script(
        [
            script.tool_call(
                "classroom_choose_next",
                {"state_version": "__STATE_VERSION__", "action_id": f"goto:q_legs"},
            )
        ],
        non_stream={"content": "ok"},
    )
    _pin_full(core)
    index = await _answer_and_settle(core, "dog")
    assert index == Q_LEGS, (
        f"a healthy agent chose goto:q_legs after a wrong answer and the lesson went "
        f"to {index} instead. The decision gate is not wired, so every fallback test "
        "in this file is vacuous."
    )
    core.control("pause")


@pytest.mark.itest(id="I2", title="Agent killed mid-lesson: class continues, mode degrades", gate=True)
async def test_the_gate_is_skipped_when_the_mode_is_not_full(core, llm):
    """PROTOCOL §7: DEGRADED and OFFLINE mean core plays `lesson_run` itself."""
    core.start_lesson(Q_MEOW)
    llm.script(
        [
            script.tool_call(
                "classroom_choose_next",
                {"state_version": "__STATE_VERSION__", "action_id": "goto:q_legs"},
            )
        ],
        non_stream={"content": "ok"},
    )
    _pin_full(core)
    core.set_mode("DEGRADED", "pinned by I2")
    calls_before = llm.request_count()

    core.interaction("interaction.choice", {"optionId": "dog"})
    await asyncio.sleep(9.0)
    index = core.state()["runner"]["index"]
    assert index == HELP_MEOW, (
        f"the agent drove the lesson to {index} while the mode was DEGRADED; "
        "in DEGRADED core plays the authored run and the agent is advisory only"
    )
    assert llm.request_count() == calls_before, (
        "the model was called while the mode was DEGRADED"
    )
    core.control("pause")


@pytest.mark.itest(id="I2", title="Agent killed mid-lesson: class continues, mode degrades", gate=True)
async def test_repeats_are_capped(core, llm):
    """An agent that always says "again" must not be able to stall the class.

    Reported by the lead and reproduced here: `repeat_activity` re-enters the
    activity, the gate fires again on the next outcome, and it repeats again.
    Nothing counts. Thirty children sit through the same question until a
    human intervenes.

    The assertion is deliberately generous — five consecutive repeats of one
    activity is already far past pedagogically useful — so it fails only on a
    genuinely unbounded loop.
    """
    core.start_lesson(Q_MEOW)
    llm.script(
        [
            script.tool_call(
                "classroom_choose_next",
                {"state_version": "__STATE_VERSION__", "action_id": "repeat_activity"},
            )
        ],
        non_stream={"content": "ok"},
    )

    _pin_full(core)
    client = BusClient(core.ws)
    await client.connect()

    indexes = []
    for _ in range(6):
        core.interaction("interaction.choice", {"optionId": "dog"})
        await asyncio.sleep(5.0)
        indexes.append(core.state()["runner"]["index"])
        if indexes[-1] != Q_MEOW:
            break

    await client.close()
    repeats = sum(1 for i in indexes if i == Q_MEOW)
    assert repeats <= 5, (
        f"the agent repeated the same activity {repeats} times in a row and the "
        f"lesson never moved (indexes seen: {indexes}). There is no per-activity "
        "repeat cap, so an agent stuck on `repeat_activity` stalls the class "
        "indefinitely at ~1,500 prompt tokens a cycle."
    )
    core.control("pause")
