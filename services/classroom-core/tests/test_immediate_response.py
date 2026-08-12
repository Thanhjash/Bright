"""The teacher answers **now**, not when the model is finished.

Measured on the running system, three runs each, answer→board:

    agent OFF (DEGRADED)   1.24 s
    agent ON  (FULL)       4.45 s

Every individual latency row had been checked; nobody had summed the column.
The reflex tier was giving visual feedback in 3 ms and then the room sat in
silence for four seconds, so FULL felt *worse* than OFFLINE — the intelligence,
which is the whole point of the product, made it feel broken.

The dead air is a turn-taking problem, not a compute problem
(docs/4-build/execution-plan.md §3). The fix is that the authored branch
narration core already holds is spoken immediately, and the model's decision
takes over when it lands. The four seconds still pass; they are full of
teaching instead of silence.

What these tests pin down:

1. the spoken response is the **authored** line for the graded branch, not a
   canned filler, and it is emitted on the reflex path
2. a model that decides differently supersedes it cleanly (`speech.cancel`)
3. a model that agrees does not cause it to be said twice
4. with no agent wired the behaviour is unchanged apart from being sooner
"""

from __future__ import annotations

import asyncio
import time

import pytest

from bright_contracts import Activity, Branch, Expect, LessonRun, Narration
from runner import LessonRunner


def frames(bus, type_: str) -> list[dict]:
    return [f["payload"] for f in bus.history if f["type"] == type_]


def said(bus) -> list[str]:
    return [p["delta"] for p in frames(bus, "speech.text.delta")]


@pytest.fixture
def lesson() -> LessonRun:
    return LessonRun(
        lessonId="turn-taking",
        classId="test",
        title="Turn taking",
        focus=["animal_vocab"],
        activities=[
            Activity(
                id="q",
                scene="choice",
                props={"prompt": "which?", "options": [{"id": "cat"}, {"id": "dog"}]},
                expect=Expect(kind="choice", correct="cat"),
                branches=[
                    Branch(
                        on="correct",
                        goto="praise",
                        narration=[Narration(text="Yes! The cat says meow.")],
                    ),
                    Branch(
                        on="wrong",
                        goto="help",
                        narration=[Narration(text="Almost! Listen again.")],
                    ),
                    Branch(on="silence", goto="help", narration=[Narration(text="Take your time.")]),
                    Branch(on="timeout", goto="help"),
                ],
            ),
            Activity(id="praise", scene="text", props={"text": "well done"}),
            Activity(id="help", scene="text", props={"text": "look again"}),
            Activity(id="elsewhere", scene="text", props={"text": "somewhere else"}),
        ],
    )


def build(bus, store, lesson: LessonRun, decide=None, hold: float = 1.2) -> LessonRunner:
    runner = LessonRunner(bus, store, lesson, silence_timeout_s=0.2, reveal_hold_s=hold)
    runner.decide_next = decide
    return runner


# ------------------------------------------------------------ the reflex line


async def test_the_authored_line_is_spoken_before_the_reveal_hold(bus, store, lesson):
    """Sub-100 ms, and it is the line the author wrote for this branch."""
    runner = build(bus, store, lesson)
    await runner.start(0)

    started = time.perf_counter()
    await runner.handle_interaction("interaction.choice", {"optionId": "dog"})
    await asyncio.sleep(0)          # let the follow-up task start; no hold has passed
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert "Almost! Listen again." in said(bus), (
        f"the class heard nothing for the whole reveal hold: {said(bus)}"
    )
    assert elapsed_ms < 100, f"the spoken response took {elapsed_ms:.1f}ms"
    assert runner.current.id == "q", "the board moved before the hold was over"
    await runner.drain()
    await runner.stop()


async def test_the_line_is_not_repeated_when_the_branch_is_taken(bus, store, lesson):
    runner = build(bus, store, lesson, hold=0.0)
    await runner.start(0)
    await runner.handle_interaction("interaction.choice", {"optionId": "cat"})
    await runner.drain()

    assert runner.current.id == "praise"
    assert said(bus).count("Yes! The cat says meow.") == 1, (
        f"the branch narration was spoken twice: {said(bus)}"
    )
    await runner.stop()


async def test_silence_and_timeout_are_answered_too(bus, store, lesson):
    """A child who says nothing is answered by the authored `silence` line."""
    runner = build(bus, store, lesson, hold=0.0)
    await runner.start(0)
    await asyncio.sleep(0.35)       # silence window is 0.2s
    await runner.drain()

    assert runner.last_outcome == "silence"
    assert said(bus).count("Take your time.") == 1
    await runner.stop()


async def test_with_no_agent_the_behaviour_is_the_old_one_sooner(bus, store, lesson):
    """NS-1: nothing here may depend on a gate existing."""
    runner = build(bus, store, lesson, hold=0.0)
    assert runner.decide_next is None
    await runner.start(0)
    await runner.handle_interaction("interaction.choice", {"optionId": "dog"})
    await runner.drain()

    assert runner.current.id == "help"
    assert said(bus).count("Almost! Listen again.") == 1
    assert not frames(bus, "speech.cancel")
    await runner.stop()


# ------------------------------------------------------- handing over cleanly


async def test_a_model_that_decides_differently_supersedes_the_line(bus, store, lesson):
    """It cannot be left contradicting the board it is no longer about."""

    async def decide(activity, outcome, payload):
        await asyncio.sleep(0.05)
        await runner.start(runner.index_of("elsewhere"))
        return "goto:elsewhere"

    runner = build(bus, store, lesson, decide=decide, hold=0.0)
    await runner.start(0)
    await runner.handle_interaction("interaction.choice", {"optionId": "dog"})
    await runner.drain()
    await asyncio.sleep(0.1)

    assert runner.current.id == "elsewhere"
    spoken = said(bus)
    assert "Almost! Listen again." in spoken, "the reflex response never happened"
    cancelled = [p["speechTurnId"] for p in frames(bus, "speech.cancel")]
    assert cancelled, "the superseded line was left running under a different activity"
    assert all(t.startswith("q#wrong") for t in cancelled)
    await runner.stop()


async def test_a_model_that_agrees_leaves_the_line_alone(bus, store, lesson):
    """Same destination: the line is still right, and cutting it is gratuitous."""

    async def decide(activity, outcome, payload):
        await asyncio.sleep(0.05)
        await runner.start(runner.index_of("help"))     # the authored `wrong` target
        return "goto:help"

    runner = build(bus, store, lesson, decide=decide, hold=0.0)
    await runner.start(0)
    await runner.handle_interaction("interaction.choice", {"optionId": "dog"})
    await runner.drain()
    await asyncio.sleep(0.1)

    assert runner.current.id == "help"
    assert said(bus).count("Almost! Listen again.") == 1, "said twice for one wrong answer"
    assert not frames(bus, "speech.cancel"), "the correct line was cut for no reason"
    await runner.stop()


async def test_a_hint_follows_the_authored_line_and_the_branch_still_lands(bus, store, lesson):
    """`say_only`: the model adds to what was said; nothing is cancelled."""

    async def decide(activity, outcome, payload):
        bus.publish("speech.turn.started", {
            "speechTurnId": "agent-1",
            "behavior": "queue",
            "source": "agent",
            "conversationTurnId": "agent-conversation-1",
        })
        bus.publish("speech.text.delta", {"speechTurnId": "agent-1", "delta": "Try once more."})
        bus.publish("speech.turn.ended", {"speechTurnId": "agent-1", "status": "completed"})
        return "say_only"

    runner = build(bus, store, lesson, decide=decide, hold=0.0)
    await runner.start(0)
    await runner.handle_interaction("interaction.choice", {"optionId": "dog"})
    await runner.drain()

    spoken = said(bus)
    assert spoken.index("Almost! Listen again.") < spoken.index("Try once more."), (
        "the model's hint arrived before the reflex response"
    )
    assert not frames(bus, "speech.cancel")

    # ...and the deferred branch still lands, without saying the line again
    await asyncio.sleep(0.35)
    await runner.drain()
    assert runner.current.id == "help"
    assert said(bus).count("Almost! Listen again.") == 1
    await runner.stop()


async def test_the_gate_never_delays_the_spoken_response(bus, store, lesson):
    """A slow model must not hold the answer back — that is the whole bug."""
    gate_started = asyncio.Event()

    async def decide(activity, outcome, payload):
        gate_started.set()
        await asyncio.sleep(3.0)
        return None

    runner = build(bus, store, lesson, decide=decide, hold=0.0)
    await runner.start(0)

    started = time.perf_counter()
    await runner.handle_interaction("interaction.choice", {"optionId": "dog"})
    await gate_started.wait()
    elapsed_ms = (time.perf_counter() - started) * 1000

    assert "Almost! Listen again." in said(bus)
    assert elapsed_ms < 200, (
        f"the class waited {elapsed_ms:.0f}ms to be answered while the model thought"
    )
    await runner.stop()
