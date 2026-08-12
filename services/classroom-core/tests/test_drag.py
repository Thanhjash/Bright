"""`matching` and `sentence_builder`: several moves, one graded answer.

`grade()` used to treat the first drag as final, which is right for a one-pair
exercise and wrong for every real one: a three-pair matching board would end on
the first pair a child joined. The rule these tests pin down is that **a list
under a `drag` `expect.correct` is a list of required moves**, so the activity
is graded when the last one lands — with the partial progress on the board in
between, because a child who has joined two of three pairs must be able to see
that they have.
"""

from __future__ import annotations

import asyncio

import pytest

from bright_contracts import Activity, Branch, Expect, LessonRun, Narration
from runner import LessonRunner, grade_drag


def scenes(bus) -> list[dict]:
    return [f["payload"] for f in bus.history if f["type"] == "scene.update"]


def said(bus) -> list[str]:
    return [f["payload"]["delta"] for f in bus.history if f["type"] == "speech.text.delta"]


@pytest.fixture
def drag_lesson() -> LessonRun:
    return LessonRun(
        lessonId="drag-01",
        classId="test",
        title="Drag",
        focus=["animal_vocab"],
        activities=[
            Activity(
                id="m1",
                scene="matching",
                props={
                    "left": [{"id": "cat", "text": "cat"}, {"id": "dog", "text": "dog"}],
                    "right": [{"id": "meow", "text": "meow"}, {"id": "woof", "text": "woof"}],
                    "solved": [],
                },
                expect=Expect(
                    kind="drag",
                    correct=["cat>meow", "dog>woof"],
                    acceptFuzzy=["cat>woof"],
                ),
                branches=[
                    Branch(on="correct", goto="done", narration=[Narration(text="all matched")]),
                    Branch(on="near", goto="help"),
                    Branch(on="wrong", goto="help"),
                    Branch(on="silence", goto="help"),
                    Branch(on="timeout", goto="help"),
                ],
            ),
            Activity(
                id="s1",
                scene="sentence_builder",
                props={
                    "tokens": [
                        {"id": "t_i", "text": "I"},
                        {"id": "t_like", "text": "like"},
                        {"id": "t_cats", "text": "cats"},
                    ],
                    "placed": [],
                    "target": "I like cats",
                },
                expect=Expect(kind="drag", correct=["t_i", "t_like", "t_cats"]),
                branches=[
                    Branch(on="correct", goto="done"),
                    Branch(on="wrong", goto="help"),
                    Branch(on="silence", goto="help"),
                    Branch(on="timeout", goto="help"),
                ],
            ),
            Activity(id="help", scene="text", props={"text": "look again"}),
            Activity(id="done", scene="text", props={"text": "well done"}),
        ],
    )


@pytest.fixture
def drag_runner(bus, store, drag_lesson: LessonRun) -> LessonRunner:
    return LessonRunner(bus, store, drag_lesson, silence_timeout_s=0.2, reveal_hold_s=0.0)


# ---------------------------------------------------------------- the grader


def test_a_single_required_move_still_grades_on_the_first_drag():
    """The pre-existing shape must be untouched: one entry, one drag, done."""
    expect = Expect(kind="drag", correct=["meow"], acceptFuzzy=["cat>woof"])
    assert grade_drag(expect, {"fromId": "cat", "toId": "meow"}, []) == ("correct", "meow")
    assert grade_drag(expect, {"fromId": "cat", "toId": "woof"}, []) == ("near", None)
    assert grade_drag(expect, {"fromId": "cat", "toId": "tweet"}, []) == ("wrong", None)


def test_both_authored_forms_are_accepted():
    """PROTOCOL §9.4: either `toId` or the pair `fromId>toId`."""
    payload = {"fromId": "cat", "toId": "meow"}
    assert grade_drag(Expect(kind="drag", correct="meow"), payload, [])[0] == "correct"
    assert grade_drag(Expect(kind="drag", correct="cat>meow"), payload, [])[0] == "correct"


def test_a_list_of_correct_entries_is_a_list_of_required_moves():
    expect = Expect(kind="drag", correct=["cat>meow", "dog>woof"])
    outcome, matched = grade_drag(expect, {"fromId": "cat", "toId": "meow"}, [])
    assert (outcome, matched) == (None, "cat>meow"), "the first of two pairs ended the activity"
    outcome, matched = grade_drag(expect, {"fromId": "dog", "toId": "woof"}, ["cat>meow"])
    assert (outcome, matched) == ("correct", "dog>woof")


def test_a_repeated_move_is_a_no_op_not_a_wrong_answer():
    expect = Expect(kind="drag", correct=["cat>meow", "dog>woof"])
    assert grade_drag(expect, {"fromId": "cat", "toId": "meow"}, ["cat>meow"]) == (None, None)


def test_matching_is_a_set_and_a_sentence_is_a_sequence():
    pairs = Expect(kind="drag", correct=["cat>meow", "dog>woof"])
    # any unsolved pair counts, in any order
    assert grade_drag(pairs, {"fromId": "dog", "toId": "woof"}, [])[1] == "dog>woof"

    tokens = Expect(kind="drag", correct=["t_i", "t_like", "t_cats"])
    # ...but "cats" is not the first word of the sentence
    assert grade_drag(tokens, {"fromId": "t_cats", "toId": "t_cats"}, [], ordered=True) == (
        "wrong",
        None,
    )
    assert grade_drag(tokens, {"fromId": "t_i", "toId": "t_i"}, [], ordered=True)[1] == "t_i"


def test_a_sentence_token_is_identified_by_the_token_it_dragged():
    """`SentenceBuilderProps` has no drop-zone ids, so `toId` may be anything."""
    tokens = Expect(kind="drag", correct=["t_i"])
    assert grade_drag(
        tokens, {"fromId": "t_i", "toId": "slot1"}, [], ordered=True, include_from=True
    ) == ("correct", "t_i")


def test_an_empty_drag_is_silence():
    assert grade_drag(Expect(kind="drag", correct=["x"]), {}, []) == ("silence", None)


# ---------------------------------------------------------------- the runner


async def test_several_moves_before_the_activity_is_graded(drag_runner, store, bus):
    await drag_runner.start(0)

    first = await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})
    assert first is None, "the first of two pairs was graded as the answer"
    assert drag_runner.current.id == "m1", "the lesson moved on after one pair"
    assert drag_runner.answered is False, "one pair used up the answer for the whole activity"

    second = await drag_runner.handle_interaction("interaction.drag", {"fromId": "dog", "toId": "woof"})
    await drag_runner.drain()
    assert second == "correct"
    assert drag_runner.current.id == "done"
    assert "all matched" in said(bus)
    await drag_runner.stop()


async def test_partial_progress_round_trips_through_scene_update(drag_runner, store, bus):
    await drag_runner.start(0)
    await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})

    solved = [s["props"].get("solved") for s in scenes(bus) if s["kind"] == "matching"]
    assert solved[-1] == [["cat", "meow"]], f"the joined pair never reached the board: {solved}"
    assert store.scene.props["solved"] == [["cat", "meow"]]
    # ...and the child can still see the pair when the activity is graded
    await drag_runner.handle_interaction("interaction.drag", {"fromId": "dog", "toId": "woof"})
    matching = [s for s in scenes(bus) if s["kind"] == "matching"]
    assert matching[-1]["props"]["solved"] == [["cat", "meow"], ["dog", "woof"]]
    await drag_runner.drain()
    await drag_runner.stop()


async def test_every_move_moves_the_state_version(drag_runner, store):
    """A partial move is still a graded interaction: agents gate on the version."""
    await drag_runner.start(0)
    before = store.state_version
    await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})
    assert store.state_version > before
    await drag_runner.stop()


async def test_a_repeated_pair_changes_nothing(drag_runner, store):
    await drag_runner.start(0)
    await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})
    version = store.state_version
    outcome = await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})
    assert outcome is None
    assert store.state_version == version, "a re-drop redrew the board"
    assert store.scene.props["solved"] == [["cat", "meow"]]
    await drag_runner.stop()


async def test_a_wrong_pair_is_graded_immediately(drag_runner):
    await drag_runner.start(0)
    outcome = await drag_runner.handle_interaction("interaction.drag", {"fromId": "dog", "toId": "meow"})
    await drag_runner.drain()
    assert outcome == "wrong"
    assert drag_runner.current.id == "help"
    await drag_runner.stop()


async def test_a_near_miss_pair_is_graded_near(drag_runner):
    await drag_runner.start(0)
    outcome = await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "woof"})
    await drag_runner.drain()
    assert outcome == "near"
    await drag_runner.stop()


async def test_a_child_working_through_the_pairs_is_not_timed_out(drag_runner):
    """Each accepted move gives the answer window back.

    The silence window is 0.2 s here. A child who joins a pair at 0.15 s and is
    still thinking at 0.30 s is working, not silent — but the window is armed
    once at ``_enter``, so without re-arming they would be moved on mid-solve.
    """
    await drag_runner.start(0)
    await asyncio.sleep(0.15)
    await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})
    await asyncio.sleep(0.15)                       # 0.30s in: the original window has passed

    assert drag_runner.current.id == "m1", "the board moved on while the child was solving"
    assert drag_runner.last_outcome is None

    assert await drag_runner.handle_interaction(
        "interaction.drag", {"fromId": "dog", "toId": "woof"}
    ) == "correct"
    await drag_runner.drain()
    await drag_runner.stop()


async def test_sentence_tokens_round_trip_in_order(drag_runner, store):
    await drag_runner.start(1)
    assert await drag_runner.handle_interaction(
        "interaction.drag", {"fromId": "t_i", "toId": "line"}
    ) is None
    assert store.scene.props["placed"] == ["t_i"]
    assert await drag_runner.handle_interaction(
        "interaction.drag", {"fromId": "t_like", "toId": "t_like"}
    ) is None
    assert store.scene.props["placed"] == ["t_i", "t_like"]
    outcome = await drag_runner.handle_interaction(
        "interaction.drag", {"fromId": "t_cats", "toId": "line"}
    )
    await drag_runner.drain()
    assert outcome == "correct"
    assert drag_runner.current.id == "done"
    await drag_runner.stop()


async def test_a_token_out_of_order_is_wrong(drag_runner):
    await drag_runner.start(1)
    outcome = await drag_runner.handle_interaction(
        "interaction.drag", {"fromId": "t_cats", "toId": "line"}
    )
    await drag_runner.drain()
    assert outcome == "wrong"
    assert drag_runner.current.id == "help"
    await drag_runner.stop()


async def test_progress_is_thrown_away_when_the_activity_is_re_entered(drag_runner, store):
    await drag_runner.start(0)
    await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})
    await drag_runner.control("repeat")
    assert store.scene.props["solved"] == [], "a repeated exercise kept the old pairs"
    outcome = await drag_runner.handle_interaction("interaction.drag", {"fromId": "cat", "toId": "meow"})
    assert outcome is None, "the first pair of a fresh attempt graded the whole activity"
    await drag_runner.stop()
