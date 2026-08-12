"""I7 — two rapid interactions before the first response lands.

A room of children does not take turns. Two taps arrive 30 ms apart, or the
same child double-taps because nothing visibly happened yet. The failure this
guards against is silent in the worst way: the lesson advances twice, one
activity is never seen, and the only evidence is a teacher afterwards saying
"I think it skipped something."

Four shapes, in increasing nastiness:

1. the same answer twice, back to back
2. two *different* answers, back to back
3. a third tap during the reveal hold, after grading but before the branch
4. two clients (stage and console) watching the whole thing — they must end on
   the same `stateVersion` and the same scene

Shape 4 is the one a single-client test cannot see, and desync between the
stage and the console is a bug this project has already had once.
"""

from __future__ import annotations

import asyncio

import pytest

from harness import BusClient

pytestmark = pytest.mark.slow


def _positions(client: BusClient) -> list[int]:
    return [e["payload"]["activityIndex"] for e in client.of_type("lesson.position")]


def _no_double_advance(positions: list[int], start: int) -> None:
    """Every step forward is exactly one authored transition, and none repeats."""
    seen = [p for p in positions if p != start]
    assert len(set(seen)) == len(seen) or len(set(seen)) <= 1, (
        f"the lesson visited an activity twice: {positions}"
    )


@pytest.mark.itest(id="I7", title="Two rapid interactions: no desync, no double-advance")
async def test_duplicate_answer_grades_once(core):
    stage = BusClient(core.ws, role="stage")
    await stage.connect()
    core.start_lesson(2)  # q_meow
    await stage.wait_for_scene("choice", timeout=30)
    start_index = core.state()["runner"]["index"]

    before = len(stage.events)
    await stage.choose("cat")
    await stage.choose("cat")  # no await in between: both are in flight

    await stage.wait_for(
        "scene.update",
        timeout=15,
        since=before,
        predicate=lambda e: bool((e["payload"].get("props") or {}).get("revealed")),
    )
    await asyncio.sleep(4.0)  # past the reveal hold and the decision gate

    state = core.state()
    assert state["runner"]["lastOutcome"] == "correct"
    # q_meow --correct--> q_legs. Two taps must not carry it past q_legs.
    assert state["runner"]["index"] == start_index + 2, (
        f"index went from {start_index} to {state['runner']['index']} on a duplicate tap "
        "(q_meow --correct--> q_legs is a single step of two)"
    )
    _no_double_advance(_positions(stage), start_index)
    stage.assert_clean()
    await stage.close()
    core.control("pause")


@pytest.mark.itest(id="I7", title="Two rapid interactions: no desync, no double-advance")
async def test_two_different_answers_do_not_both_grade(core):
    stage = BusClient(core.ws, role="stage")
    await stage.connect()
    core.start_lesson(2)
    await stage.wait_for_scene("choice", timeout=30)
    start_index = core.state()["runner"]["index"]

    before = len(stage.events)
    await stage.choose("cat")   # correct → q_legs
    await stage.choose("dog")   # wrong   → help_meow
    await stage.wait_for(
        "scene.update",
        timeout=15,
        since=before,
        predicate=lambda e: bool((e["payload"].get("props") or {}).get("revealed")),
    )
    await asyncio.sleep(4.0)

    state = core.state()
    index = state["runner"]["index"]
    # Whichever won, exactly one branch may have been taken.
    assert index in (start_index + 1, start_index + 2), (
        f"two conflicting answers left the lesson at index {index} (started {start_index}); "
        "only one authored branch may fire per question"
    )
    reveals = [
        (s.get("props") or {}).get("revealed")
        for s in stage.scenes()
        if (s.get("props") or {}).get("revealed")
    ]
    chosen = {r["chosenId"] for r in reveals}
    assert len(chosen) == 1, f"the board revealed two different chosen answers: {chosen}"
    stage.assert_clean()
    await stage.close()
    core.control("pause")


@pytest.mark.itest(id="I7", title="Two rapid interactions: no desync, no double-advance")
async def test_tap_during_the_reveal_hold_does_not_advance_again(core):
    """The nastiest window: graded, revealed, branch not yet taken."""
    stage = BusClient(core.ws, role="stage")
    await stage.connect()
    core.start_lesson(2)
    await stage.wait_for_scene("choice", timeout=30)
    start_index = core.state()["runner"]["index"]

    before = len(stage.events)
    await stage.choose("cat")
    await stage.wait_for(
        "scene.update",
        timeout=15,
        since=before,
        predicate=lambda e: bool((e["payload"].get("props") or {}).get("revealed")),
    )
    await stage.choose("dog")   # inside the reveal hold
    await asyncio.sleep(5.0)

    index = core.state()["runner"]["index"]
    assert index == start_index + 2, (
        f"a tap during the reveal hold moved the lesson to {index} instead of "
        f"{start_index + 2} — one graded outcome, one transition"
    )
    stage.assert_clean()
    await stage.close()
    core.control("pause")


@pytest.mark.itest(id="I7", title="Two rapid interactions: no desync, no double-advance")
async def test_stage_and_console_stay_in_sync(core):
    """Two live sockets, one classroom. They must agree at the end."""
    stage = BusClient(core.ws, role="stage")
    console = BusClient(core.ws, role="control")
    await stage.connect()
    await console.connect()

    core.start_lesson(2)
    await stage.wait_for_scene("choice", timeout=30)
    await console.wait_for_scene("choice", timeout=30)

    await stage.choose("cat")
    await console.send("interaction.choice", {"optionId": "cat"})
    await asyncio.sleep(5.0)

    server_version = core.state()["stateVersion"]
    assert stage.state_version == console.state_version, (
        f"stage saw stateVersion {stage.state_version}, console saw {console.state_version}"
    )
    assert stage.state_version == server_version, (
        f"clients are at {stage.state_version}, core is at {server_version}"
    )
    assert stage.scenes()[-1]["kind"] == console.scenes()[-1]["kind"]

    stage.assert_clean()
    console.assert_clean()
    await stage.close()
    await console.close()
    core.control("pause")
