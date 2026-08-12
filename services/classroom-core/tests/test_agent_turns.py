"""The automatic agent turn -- the decision gate the runner consults.

What is under test is not "does the model teach well". It is the frame around
the model: that grading still happens at reflex speed, that every way the agent
can fail lands on the authored branch, and that removing the agent removes the
code path (NS-1).

No test here touches the network. `AgentDriver` takes an agent *factory*, and
`take_turn` only ever reads `event.type` / `.reason` / `.usage` off whatever the
agent yields, so a scripted async generator is a complete stand-in.
"""

from __future__ import annotations

import asyncio

from conftest import choose, nothing, wire  # noqa: F401 -- shared agent fakes

from agent_bridge import available_actions
from app import Core


async def answer(core: Core, option_id: str) -> None:
    """Answer the choice activity and let every follow-up settle."""
    await core.runner.handle_interaction("choice", {"optionId": option_id})
    await core.runner.drain()


# -------------------------------------------------------------- the gate


async def test_the_agent_can_override_the_authored_branch(core: Core):
    """`wrong` is authored to a4. The agent sends the class to a3 instead."""
    wire(core, choose("goto:a3"))
    await core.runner.start(1)

    await answer(core, "z")

    assert core.runner.current.id == "a3"
    assert core.auto_turn.stats()["applied"] == 1


async def test_a_slow_agent_loses_the_turn_and_the_branch_is_taken(core: Core):
    """Bounded means bounded. The class does not wait on a thinking model."""
    agent = wire(core, choose("goto:a3"), delay=5.0)
    await core.runner.start(1)

    await answer(core, "z")

    assert agent.started == 1, "the turn was offered"
    assert core.runner.current.id == "a4", "and the authored branch was taken anyway"
    stats = core.auto_turn.stats()
    assert stats["timeouts"] == 1 and stats["applied"] == 0
    assert stats["lastElapsedMs"] < 2000, "cut off at the timeout, not at the agent's pace"


async def test_an_illegal_action_falls_through_to_the_branch(core: Core):
    """The agent cannot invent a destination; core offered these and no others."""
    wire(core, choose("goto:atlantis"))
    await core.runner.start(1)

    await answer(core, "z")

    assert core.runner.current.id == "a4"
    assert core.auto_turn.stats()["applied"] == 0


async def test_a_stale_state_version_falls_through_to_the_branch(core: Core):
    wire(core, lambda ctx: [("classroom_choose_next", {"action_id": "goto:a3", "state_version": 1})])
    await core.runner.start(1)

    await answer(core, "z")

    assert core.runner.current.id == "a4"


async def test_an_agent_that_crashes_falls_through_to_the_branch(core: Core):
    def explode(_ctx):
        raise RuntimeError("model on fire")

    wire(core, explode)
    await core.runner.start(1)

    await answer(core, "z")

    assert core.runner.current.id == "a4"


async def test_an_agent_that_decides_nothing_falls_through_to_the_branch(core: Core):
    wire(core, nothing)
    await core.runner.start(1)

    await answer(core, "z")

    assert core.runner.current.id == "a4"
    assert core.auto_turn.stats()["turns"] == 1


async def test_say_only_defers_the_branch_it_does_not_cancel_it(core: Core):
    """A hint buys time. It must not buy silence forever.

    `say_only` leaves the board where it is, so the authored branch is
    re-armed behind a fresh silence window rather than dropped -- otherwise a
    model that only ever hints stalls the lesson while sounding busy.
    """
    wire(core, choose("say_only", text="Listen again: which one says meow?"))
    await core.runner.start(1)

    await answer(core, "z")
    assert core.runner.current.id == "a2", "still on the question, as asked"

    await asyncio.sleep(0.25)  # past silence_timeout_s
    await core.runner.drain()
    assert core.runner.current.id == "a4", "the authored branch fired late, not never"


async def test_a_deferred_branch_does_not_ask_the_agent_twice(core: Core):
    """One outcome, one turn. The second pass is the branch, not another turn."""
    wire(core, choose("say_only", text="Try once more."))
    await core.runner.start(1)

    await answer(core, "z")
    await asyncio.sleep(0.25)
    await core.runner.drain()

    assert core.auto_turn.stats()["turns"] == 1


async def test_a_student_who_answers_during_the_hint_supersedes_it(core: Core):
    wire(core, choose("say_only", text="Try once more."))
    await core.runner.start(1)

    await answer(core, "z")
    assert core.runner.current.id == "a2"

    # Second answer, this time right: the deferred branch is superseded the
    # ordinary way, by the generation bump.
    core.auto_turn.timeout_s = 0.0        # no second opinion needed for this
    await core.runner.handle_interaction("choice", {"optionId": "x"})
    await core.runner.drain()
    await asyncio.sleep(0.25)
    await core.runner.drain()

    assert core.runner.current.id == "a3", "the correct answer won, not the stale hint"


async def test_silence_gets_a_turn_too(core: Core):
    """A child who says nothing is the most informative outcome there is."""
    agent = wire(core, choose("say_only", text="It is alright. Listen once more."))
    await core.runner.start(4)                      # a5: speech, no durationS

    await asyncio.sleep(0.25)                        # past silence_timeout_s
    await core.runner.drain()

    assert agent.started == 1
    assert agent.contexts[0].last_interaction.outcome == "silence"


async def test_no_turn_when_the_mode_is_not_full(core: Core):
    """DEGRADED and OFFLINE mean core plays lesson_run (PROTOCOL §7)."""
    agent = wire(core, choose("goto:a3"))
    core.modes.forced_mode = None
    core.modes.apply("DEGRADED", "test")
    await core.runner.start(1)

    await answer(core, "z")

    assert agent.started == 0
    assert core.runner.current.id == "a4"
    assert core.auto_turn.stats()["skippedNotFull"] == 1


async def test_turns_are_serialised_one_classroom_one_teacher(core: Core):
    agent = wire(core, choose("say_only", text="hm"), delay=0.15)
    await core.runner.start(1)

    results = await asyncio.gather(
        core.agent_driver.take_turn(), core.agent_driver.take_turn()
    )

    assert agent.max_in_flight == 1
    assert [r.rejected for r in results].count("turn already in flight") == 1
    assert core.agent_driver.skipped == 1


async def test_a_busy_driver_does_not_stall_the_lesson(core: Core):
    """A skipped turn is still an answer: take the branch."""
    wire(core, choose("say_only", text="hm"), delay=0.3)
    await core.runner.start(1)

    holding = asyncio.ensure_future(core.agent_driver.take_turn())
    await asyncio.sleep(0.02)
    await answer(core, "z")
    await holding

    assert core.runner.current.id == "a4"


# ------------------------------------------------------------------ NS-1


async def test_without_an_agent_the_gate_does_not_exist(core: Core):
    """Not "a hook that returns early" -- absent."""
    assert core.agent_driver is None
    assert core.runner.decide_next is None

    await core.runner.start(1)
    await answer(core, "z")

    assert core.runner.current.id == "a4"
    assert core.auto_turn is None


async def test_grading_stays_on_the_reflex_path_with_the_agent_wired(core: Core):
    """The agent may change what comes next. It may not slow down the answer.

    `handle_interaction` returns once grading and the reveal frame are done;
    the turn runs behind it.
    """
    wire(core, choose("goto:a3"), delay=0.3)
    await core.runner.start(1)

    outcome = await core.runner.handle_interaction("choice", {"optionId": "z"})

    assert outcome == "wrong"
    assert core.runner.last_latency_ms < 50, core.runner.last_latency_ms
    assert core.store.scene.props["revealed"]["chosenId"] == "z", "reveal already on the board"
    await core.runner.drain()


# ------------------------------------------------- the option set itself


async def test_available_actions_can_be_restricted(core: Core):
    await core.runner.start(1)

    every = {a.id for a in available_actions(core)}
    assert {"goto:a3", "goto:a4", "repeat_activity", "next_activity", "say_only"} <= every

    only = available_actions(core, only=("say_only",))
    assert [a.id for a in only] == ["say_only"]


async def test_a_restricted_turn_cannot_take_an_unoffered_action(core: Core):
    """The prompt and the admission check must read from the same list.

    Filtering only the prompt would leave the executor happily applying an
    action the model was never shown.
    """
    wire(core, choose("goto:a3"))
    await core.runner.start(1)

    result = await core.agent_driver.take_turn(only=("say_only",))

    assert result.applied is False
    assert "illegal action_id" in (result.rejected or "")
    assert core.runner.current.id == "a2"


async def test_the_turn_context_carries_what_just_happened(core: Core):
    agent = wire(core, nothing)
    await core.runner.start(1)

    await answer(core, "z")

    last = agent.contexts[0].last_interaction
    assert last.kind == "choice" and last.outcome == "wrong"
    assert "a2" in last.detail and "z" in last.detail
