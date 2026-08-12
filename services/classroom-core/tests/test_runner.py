from __future__ import annotations

import asyncio
import time

import pytest
from pydantic import ValidationError

from bright_contracts import Activity, Branch, Expect, LessonRun
from runner import LessonRunner, grade, normalize_text, resolve_branch, stage_for


def types_of(bus) -> list[str]:
    return [f["type"] for f in bus.history]


# ------------------------------------------------------------------ grading


@pytest.mark.parametrize(
    "payload,expected",
    [
        ({"optionId": "x"}, "correct"),
        ({"optionId": "y"}, "near"),      # acceptFuzzy generalised to ids
        ({"optionId": "z"}, "wrong"),
        ({"optionId": ""}, "silence"),
    ],
)
def test_grade_choice(payload, expected):
    expect = Expect(kind="choice", correct="x", acceptFuzzy=["y"])
    assert grade(expect, "choice", payload) == expected


def test_grade_accepts_a_list_of_correct_ids():
    expect = Expect(kind="choice", correct=["x", "w"])
    assert grade(expect, "choice", {"optionId": "w"}) == "correct"


def test_grade_point_and_drag():
    assert grade(Expect(kind="point", correct="cat"), "point", {"targetId": "cat"}) == "correct"
    assert grade(Expect(kind="point", correct="cat"), "point", {"targetId": "dog"}) == "wrong"
    drag = Expect(kind="drag", correct=["cat>animal", "animal"])
    assert grade(drag, "drag", {"fromId": "cat", "toId": "animal"}) == "correct"
    assert grade(drag, "drag", {"fromId": "cat", "toId": "food"}) == "wrong"


@pytest.mark.parametrize(
    "said,confidence,expected",
    [
        ("I like cats.", 0.95, "correct"),
        ("i like cats", 0.75, "correct"),
        ("Um, I like cats!", 0.99, "near"),
        ("I do not like cats", 0.99, "wrong"),
        ("I like cats but I hate dogs", 0.99, "wrong"),
        ("I like cats", 0.74, "near"),
        ("I like cats", None, "near"),
        ("I like cat", 0.99, "near"),
        ("I hate homework", 0.99, "wrong"),
        ("   ", 0.99, "silence"),
    ],
)
def test_grade_speech(said, confidence, expected):
    expect = Expect(kind="speech", correct=["I like cats"], acceptFuzzy=["I like cat"])
    payload = {"text": said}
    if confidence is not None:
        payload["confidence"] = confidence
    assert grade(expect, "speech", payload) == expected


def test_grade_ignores_mismatched_or_absent_expectations():
    assert grade(None, "choice", {"optionId": "x"}) is None
    assert grade(Expect(kind="none"), "choice", {"optionId": "x"}) is None
    assert grade(Expect(kind="choice", correct="x"), "point", {"targetId": "x"}) is None


def test_normalize_text():
    assert normalize_text("  I  LIKE, cats!! ") == "i like cats"


# ----------------------------------------------------------------- branches


def test_resolve_branch_prefers_exact_then_always():
    activity = Activity(
        id="a",
        scene="choice",
        branches=[Branch(on="correct", goto="good"), Branch(on="always", goto="fallback")],
    )
    assert resolve_branch(activity, "correct").goto == "good"
    assert resolve_branch(activity, "wrong").goto == "fallback"
    assert resolve_branch(Activity(id="b", scene="text"), "wrong") is None


def test_sample_lesson_satisfies_the_lesson_lint_rule(sample_lesson: LessonRun):
    """PROTOCOL §4: every activity with an expect covers wrong AND silence, or always."""
    for activity in sample_lesson.activities:
        if activity.expect is None or activity.expect.kind == "none":
            continue
        ons = {b.on for b in activity.branches or []}
        assert "always" in ons or {"wrong", "silence"} <= ons, activity.id


def test_lesson_run_rejects_an_obsolete_protocol_version():
    with pytest.raises(ValidationError):
        LessonRun.model_validate(
            {
                "v": 1,
                "lessonId": "obsolete",
                "classId": "demo",
                "title": "Old lesson",
                "activities": [],
            }
        )


def test_stage_for():
    activities = [
        Activity(id="a", scene="text"),
        Activity(id="b", scene="vocabulary"),
        Activity(id="c", scene="choice"),
        Activity(id="d", scene="text"),
    ]
    stages = [stage_for(a, i, len(activities)) for i, a in enumerate(activities)]
    assert stages == ["HOOK", "INPUT", "PRACTICE", "WRAP"]


# ------------------------------------------------------------------ playing


async def test_start_renders_the_first_activity(runner: LessonRunner, store, bus):
    await runner.start()
    assert runner.index == 0
    assert store.scene.kind == "text"
    assert store.scene.props["text"] == "hello"
    assert store.lesson.activity_index == 0
    assert store.lesson.activity_count == 5
    assert store.lesson.lesson_id == "tiny-01"
    assert "scene.update" in types_of(bus)
    assert "lesson.position" in types_of(bus)
    assert "speech.turn.started" in types_of(bus)
    assert "speech.text.delta" in types_of(bus)
    assert "speech.turn.ended" in types_of(bus)
    await runner.stop()


async def test_correct_answer_takes_the_correct_branch(runner: LessonRunner, store, bus):
    await runner.start(1)
    outcome = await runner.handle_interaction("interaction.choice", {"optionId": "x"})
    await runner.drain()
    assert outcome == "correct"
    assert runner.current.id == "a3"
    assert store.scene.props["text"] == "well done"
    said = [f["payload"]["delta"] for f in bus.history if f["type"] == "speech.text.delta"]
    assert "yes!" in said           # branch narration is spoken before the jump
    await runner.stop()


async def test_wrong_answer_takes_the_wrong_branch(runner: LessonRunner):
    await runner.start(1)
    outcome = await runner.handle_interaction("interaction.choice", {"optionId": "zzz"})
    await runner.drain()
    assert outcome == "wrong"
    assert runner.current.id == "a4"
    await runner.stop()


async def test_near_miss_is_graded_near(runner: LessonRunner):
    await runner.start(1)
    assert await runner.handle_interaction("interaction.choice", {"optionId": "y"}) == "near"
    await runner.drain()
    assert runner.current.id == "a3"
    await runner.stop()


async def test_choice_reveal_is_emitted_before_the_jump(runner: LessonRunner, bus):
    await runner.start(1)
    await runner.handle_interaction("interaction.choice", {"optionId": "y"})
    revealed = [
        f for f in bus.history
        if f["type"] == "scene.update" and "revealed" in (f["payload"].get("props") or {})
    ]
    assert revealed, "the board must show the answer immediately"
    assert revealed[0]["payload"]["props"]["revealed"] == {"correctId": "x", "chosenId": "y"}
    await runner.drain()
    await runner.stop()


async def test_speech_answer_is_graded(runner: LessonRunner):
    await runner.start(4)
    assert await runner.handle_interaction(
        "student.speech.final", {"text": "I like cats", "confidence": 0.95}
    ) == "correct"
    await runner.drain()
    assert runner.current.id == "a3"
    await runner.stop()


async def test_answer_generation_is_immediately_published(runner: LessonRunner, store, bus):
    await runner.start(1)
    before = store.lesson.activity_generation
    assert await runner.handle_interaction("choice", {"optionId": "x"}) == "correct"
    assert store.lesson.activity_generation == before + 1
    positions = [f["payload"] for f in bus.history if f["type"] == "lesson.position"]
    assert positions[-1]["activityGeneration"] == before + 1
    await runner.stop()


async def test_missing_playback_ack_releases_speech_activity(tiny_lesson, store, bus):
    from runner import LessonRunner
    from bright_contracts import Narration

    tiny_lesson.activities[4].narration = [Narration(text="Your turn")]

    runner = LessonRunner(
        bus,
        store,
        tiny_lesson,
        silence_timeout_s=1.0,
        reveal_hold_s=0.0,
        playback_ack_timeout_s=0.01,
        publish_speech=lambda *_args, **_kwargs: "turn-prompt",
    )
    await runner.start(4)
    assert store.scene.overlay is None or store.scene.overlay.listening is not True
    await asyncio.sleep(0.13)
    assert store.scene.overlay is not None and store.scene.overlay.listening is True
    assert runner._timer is not None
    await runner.stop()


async def test_each_queued_narration_turn_gets_its_own_playback_deadline(
    tiny_lesson, store, bus
):
    from runner import LessonRunner
    from bright_contracts import Narration

    tiny_lesson.activities[4].narration = [
        Narration(text="First line"),
        Narration(text="Your turn"),
    ]
    ids = iter(("turn-first", "turn-final"))
    runner = LessonRunner(
        bus,
        store,
        tiny_lesson,
        silence_timeout_s=1.0,
        reveal_hold_s=0.0,
        playback_ack_timeout_s=0.08,
        publish_speech=lambda *_args, **_kwargs: next(ids),
    )
    await runner.start(4)
    await asyncio.sleep(0.05)
    assert runner.on_playback_finished("turn-first") is True
    await asyncio.sleep(0.05)  # beyond the old single publish-time deadline
    assert store.scene.overlay is None or store.scene.overlay.listening is not True
    assert runner.on_playback_finished("turn-final") is True
    assert store.scene.overlay is not None and store.scene.overlay.listening is True
    await runner.stop()


async def test_grading_is_faster_than_100ms(runner: LessonRunner):
    await runner.start(1)
    started = time.perf_counter()
    await runner.handle_interaction("interaction.choice", {"optionId": "x"})
    elapsed_ms = (time.perf_counter() - started) * 1000
    assert elapsed_ms < 100, f"reflex tier took {elapsed_ms:.1f}ms"
    await runner.drain()
    await runner.stop()


async def test_auto_advance_on_duration(runner: LessonRunner):
    await runner.start(0)
    assert runner.index == 0
    await asyncio.sleep(1.25)
    assert runner.index == 1        # durationS=1 elapsed, no expect -> next
    await runner.stop()


async def test_timeout_outcome_when_an_expected_answer_never_comes(runner: LessonRunner):
    await runner.start(1)
    await asyncio.sleep(1.25)
    await runner.drain()
    assert runner.last_outcome == "timeout"
    assert runner.current.id == "a4"
    await runner.stop()


async def test_silence_outcome_without_a_duration(runner: LessonRunner):
    await runner.start(4)           # expect, no durationS -> silence timer
    await asyncio.sleep(0.2)
    await runner.drain()
    assert runner.last_outcome == "silence"
    assert runner.current.id == "a4"
    await runner.stop()


async def test_stale_timer_cannot_double_advance(runner: LessonRunner):
    """Answer just before the auto-advance timer fires: exactly one advance."""
    await runner.start(1)
    await asyncio.sleep(0.9)
    await runner.handle_interaction("interaction.choice", {"optionId": "x"})
    await runner.drain()
    assert runner.current.id == "a3"
    await asyncio.sleep(0.5)        # the old timer for a2 would fire here
    assert runner.current.id == "a3"
    assert runner.index == 2
    await runner.stop()


async def test_always_branch_is_followed_on_auto_advance(bus, store, sample_lesson):
    lesson_runner = LessonRunner(bus, store, sample_lesson, reveal_hold_s=0.0)
    help_index = lesson_runner.index_of("help_meow")
    sample_lesson.activities[help_index].duration_s = 1
    await lesson_runner.start(help_index)
    await asyncio.sleep(1.25)
    assert lesson_runner.current.id == "q_legs"
    await lesson_runner.stop()


async def test_controls(runner: LessonRunner):
    await runner.start(0)
    await runner.control("skip")
    assert runner.index == 1
    await runner.control("back")
    assert runner.index == 0
    await runner.control("pause")
    assert runner.paused is True
    await asyncio.sleep(1.25)
    assert runner.index == 0, "a paused lesson must not auto-advance"
    await runner.control("resume")
    assert runner.paused is False
    await runner.control("repeat")
    assert runner.index == 0
    await runner.stop()


async def test_lesson_finishes_cleanly(runner: LessonRunner, store):
    await runner.start(3)           # a4 has no duration and no expect
    await runner.control("skip")    # -> a5
    await runner.control("skip")    # -> past the end
    assert runner.finished is True
    assert store.scene.kind == "idle"
    assert store.lesson.stage == "DONE"
    await runner.stop()


async def test_full_sample_lesson_runs_with_no_llm(bus, store, sample_lesson):
    """NS-1: the whole run plays from lesson_run.json alone."""
    lesson_runner = LessonRunner(bus, store, sample_lesson, reveal_hold_s=0.0)
    await lesson_runner.start()
    visited = [lesson_runner.current.id]
    guard = 0
    while not lesson_runner.finished and guard < 20:
        guard += 1
        activity = lesson_runner.current
        if activity is None:
            break
        if activity.expect is not None and activity.expect.kind == "choice":
            correct = activity.expect.correct
            option = correct if isinstance(correct, str) else correct[0]
            await lesson_runner.handle_interaction("interaction.choice", {"optionId": option})
            await lesson_runner.drain()
        else:
            await lesson_runner.control("skip")
        if lesson_runner.current is not None:
            visited.append(lesson_runner.current.id)
    assert lesson_runner.finished is True
    assert visited[:3] == ["hook_hello", "vocab_animals", "q_meow"]
    assert "wrap_bye" in visited
    assert visited[-1] == sample_lesson.activities[-1].id
    await lesson_runner.stop()


def test_sample_lesson_says_goodbye_only_at_the_end(sample_lesson):
    """A polished demo must not dismiss the class halfway through the run."""
    farewell_words = ("goodbye", "see you next time", "that is everything")
    for activity in sample_lesson.activities[:-1]:
        spoken = " ".join(line.text for line in activity.narration or []).lower()
        assert not any(word in spoken for word in farewell_words), activity.id
    final_spoken = " ".join(
        line.text for line in sample_lesson.activities[-1].narration or []
    ).lower()
    assert "goodbye" in final_spoken
