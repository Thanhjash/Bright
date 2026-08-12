"""The scenario corpus — five classes, from SP-3.

Grading rule that makes this honest: **every scenario carries an acceptable
*set* of action ids, never a single right answer.** A live class usually has
two or three defensible next moves; grading against one of them measures the
grader's opinion, not the model. `reject` lists the choices that are actually
wrong, and those are what the score punishes.

Class sizes are deliberately uneven. SP-3's kill criterion is "< 85% on
tool_routing", so tool_routing gets enough scenarios to tell 84% from 90%;
the other four only need enough to rank variants against each other.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

from bright_contracts import (
    AvailableAction,
    LastInteraction,
    LessonPosition,
    RecalledMemory,
    Scene,
    StudentBrief,
    TurnContext,
)

EvalClass = Literal["tool_routing", "pedagogy", "bilingual", "recovery", "lesson_policy"]

CLASSES: tuple[EvalClass, ...] = (
    "tool_routing",
    "pedagogy",
    "bilingual",
    "recovery",
    "lesson_policy",
)


# ------------------------------------------------------------ executor spec


@dataclass(frozen=True)
class ExecutorSpec:
    """How the injected ToolExecutor behaves for this scenario.

    Two failure modes, graded separately (they are not the same thing):

    * `raises` — a hard failure. Core's executor threw. The contract says the
      turn ends immediately with one `ToolResult(ok=False)` + `Done("error")`.
      What we grade is that the agent does **not** spiral.
    * `soft_errors` — the call succeeded at transport level but the result
      says "no". The model sees it and has a chance to adapt inside the turn.
    """

    results: dict[str, Any] = field(default_factory=dict)
    raises: frozenset[str] = frozenset()
    soft_errors: dict[str, Any] = field(default_factory=dict)


DEFAULT_EXEC = ExecutorSpec()


# ---------------------------------------------------------------- scenario


@dataclass(frozen=True)
class Scenario:
    id: str
    cls: EvalClass
    ctx: TurnContext
    #: Defensible next moves. Empty means "no action should be chosen at all".
    accept: frozenset[str] = frozenset()
    #: Choices that are pedagogically or procedurally wrong. Scored explicitly.
    reject: frozenset[str] = frozenset()
    #: Tool names that must appear in the turn.
    must_call: frozenset[str] = frozenset()
    #: Tool names that must NOT appear.
    must_not_call: frozenset[str] = frozenset()
    #: Acceptable terminal reasons.
    expect_done: frozenset[str] = frozenset({"complete"})
    #: Named policy checks, implemented in graders.py.
    checks: tuple[str, ...] = ()
    executor: ExecutorSpec = DEFAULT_EXEC
    note: str = ""


# ----------------------------------------------------------------- helpers


def _acts(*specs: tuple[str, str] | tuple[str, str, list[str]]) -> list[AvailableAction]:
    out = []
    for s in specs:
        out.append(AvailableAction(id=s[0], label=s[1], params=s[2] if len(s) > 2 else None))  # type: ignore[misc]
    return out


def ctx(
    *,
    state_version: int = 88,
    lesson_id: str = "en-a1-market-01",
    class_id: str = "7A",
    stage: str = "PRACTICE",
    index: int = 2,
    count: int = 9,
    kind: str = "choice",
    props: dict[str, Any] | None = None,
    student: tuple[str, str, dict[str, float]] | None = ("s17", "Minh", {"food_vocab": 0.82}),
    last: tuple[str, str, str | None] | None = ("choice", "picked banana", "wrong"),
    actions: Iterable[AvailableAction] = (),
    recalled: list[tuple[str, str]] | None = None,
) -> TurnContext:
    return TurnContext(
        stateVersion=state_version,
        lesson=LessonPosition(
            lessonId=lesson_id,
            classId=class_id,
            activityIndex=index,
            activityCount=count,
            stage=stage,
            currentStudentId=student[0] if student else None,
        ),
        scene=Scene(stateVersion=state_version, kind=kind, props=props or {}),  # type: ignore[arg-type]
        student=StudentBrief(id=student[0], name=student[1], skills=student[2]) if student else None,
        lastInteraction=LastInteraction(kind=last[0], detail=last[1], outcome=last[2]) if last else None,  # type: ignore[arg-type]
        availableActions=list(actions),
        recalled=[RecalledMemory(text=t, when=w) for t, w in (recalled or [])] or None,
    )


CHOICE_APPLE = {
    "prompt": "Which one is the apple?",
    "options": [{"id": "o1", "text": "apple"}, {"id": "o2", "text": "banana"}],
}
VOCAB_FRUIT = {
    "items": [
        {"id": "i1", "text": "apple"},
        {"id": "i2", "text": "banana"},
        {"id": "i3", "text": "mango"},
    ]
}

# The ladder, as action ids. `scaffold_down` is one step; `explain_vietnamese`
# is the jump the north star forbids (§5). Offering both every time is what
# makes the pedagogy class gradeable at all.
LADDER = _acts(
    ("scaffold_down", "drop one step: show the picture and point"),
    ("explain_vietnamese", "explain the whole thing in Vietnamese"),
    ("repeat_activity", "repeat vocabulary_grid"),
    ("next_activity", "advance to sentence_builder"),
)


# ================================================================ corpus


def _tool_routing() -> list[Scenario]:
    """Given class state + objective, is the tool choice right?

    The routing question is two-part: pick the right *tool*, then the right
    *action id* out of the offered set.
    """
    S: list[Scenario] = []

    A_STD = _acts(
        ("next_activity", "advance to sentence_builder"),
        ("repeat_activity", "repeat vocabulary_grid"),
        ("scaffold_down", "drop to image support"),
        ("call_student", "call on a student", ["student_id"]),
    )

    S.append(Scenario(
        "tr01_correct_answer_advances", "tool_routing",
        ctx(props=CHOICE_APPLE, last=("choice", "picked apple", "correct"), actions=A_STD),
        accept=frozenset({"next_activity"}),
        reject=frozenset({"scaffold_down"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="student got it right — do not scaffold down",
    ))

    S.append(Scenario(
        "tr02_wrong_answer_scaffolds", "tool_routing",
        ctx(props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"), actions=A_STD),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="wrong answer — advancing past it is the failure mode",
    ))

    S.append(Scenario(
        "tr03_silence_calls_or_scaffolds", "tool_routing",
        ctx(props=CHOICE_APPLE, last=("choice", "no response for 12 seconds", "silence"), actions=A_STD),
        accept=frozenset({"scaffold_down", "repeat_activity", "call_student"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="silence != wrong. Both are 'not yet', neither is 'move on'.",
    ))

    S.append(Scenario(
        "tr04_call_student_needs_param", "tool_routing",
        ctx(
            props={"prompt": "Who can say 'mango'?", "options": [{"id": "o1", "text": "mango"}]},
            student=None, last=("stage", "opened INTERACTION", None),
            actions=_acts(
                ("call_student", "call on a student", ["student_id"]),
                ("next_activity", "advance to pronunciation"),
            ),
        ),
        accept=frozenset({"call_student", "next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("params_present_if_required",),
        note="call_student declares params — omitting student_id is a rejection",
    ))

    S.append(Scenario(
        "tr05_record_then_choose", "tool_routing",
        ctx(props=CHOICE_APPLE, last=("speech", "Minh said 'this is a apple'", "near"), actions=A_STD),
        accept=frozenset({"repeat_activity", "next_activity", "scaffold_down"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("observation_if_named_student",),
        note="a named student demonstrated something — record_observation is the write path",
    ))

    S.append(Scenario(
        "tr06_no_actions_offered", "tool_routing",
        ctx(props={"text": "Break time"}, kind="text", last=None, actions=[]),
        accept=frozenset(),
        must_not_call=frozenset({"classroom_choose_next"}),
        expect_done=frozenset({"complete", "no_action"}),
        note="core offered nothing. Choosing anyway is a hallucinated action.",
    ))

    S.append(Scenario(
        "tr07_stale_version_trap", "tool_routing",
        ctx(state_version=104, props=CHOICE_APPLE, actions=A_STD,
            recalled=[("in the last class the state_version was 88", "2026-08-04")]),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("state_version_exact",),
        note="a stale-looking number is planted in MEMORY; it must use 104",
    ))

    S.append(Scenario(
        "tr08_explore_opportunity", "tool_routing",
        ctx(
            stage="EXPLORE", kind="vocabulary", props={"items": [{"id": "i1", "text": "penguin"}]},
            last=("speech", "Minh asked 'what is penguin?'", None),
            actions=_acts(
                ("open_explore", "open EXPLORE on 'penguin'"),
                ("next_activity", "advance to exit check"),
                ("repeat_activity", "repeat the vocabulary grid"),
            ),
        ),
        accept=frozenset({"open_explore"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="NS §5 EXPLORE: curiosity is the whole product, do not skip past it",
    ))

    S.append(Scenario(
        "tr09_roleplay_start", "tool_routing",
        ctx(
            stage="ROLEPLAY", kind="roleplay", props={"environment": "market", "aiRole": "seller"},
            last=("stage", "entered ROLEPLAY", None),
            actions=_acts(
                ("start_roleplay", "start market roleplay"),
                ("scaffold_down", "show the phrase card first"),
                ("next_activity", "skip to exit check"),
            ),
        ),
        accept=frozenset({"start_roleplay", "scaffold_down"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
    ))

    S.append(Scenario(
        "tr10_exit_check_finishes", "tool_routing",
        ctx(
            stage="EXIT_CHECK", index=8, kind="choice",
            props={"prompt": "Say one fruit you like", "options": [{"id": "o1", "text": "apple"}]},
            last=("speech", "Minh said 'I like apple'", "correct"),
            actions=_acts(
                ("end_lesson", "finish the lesson"),
                ("repeat_activity", "ask one more student"),
            ),
        ),
        accept=frozenset({"end_lesson", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
    ))

    S.append(Scenario(
        "tr11_pronunciation_near", "tool_routing",
        ctx(
            stage="PRODUCTION", kind="pronunciation", props={"word": "banana"},
            last=("pronunciation", "Minh said /bəˈnɑːnə/ score 0.61", "near"),
            actions=_acts(
                ("repeat_activity", "model the word again"),
                ("next_activity", "move to the next word"),
                ("scaffold_down", "break it into syllables"),
            ),
        ),
        accept=frozenset({"repeat_activity", "scaffold_down"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
    ))

    S.append(Scenario(
        "tr12_matching_solved", "tool_routing",
        ctx(
            kind="matching", props={"left": [1, 2, 3], "solved": [1, 2, 3]},
            last=("drag", "all pairs matched", "correct"),
            actions=_acts(
                ("next_activity", "advance to sentence_builder"),
                ("repeat_activity", "repeat the matching"),
            ),
        ),
        accept=frozenset({"next_activity"}),
        reject=frozenset({"repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="finished cleanly — repeating wastes class time",
    ))

    S.append(Scenario(
        "tr13_recall_available", "tool_routing",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"), recalled=None,
            actions=A_STD,
        ),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="no MEMORY block supplied; recall is allowed but must not replace choosing",
    ))

    S.append(Scenario(
        "tr14_single_action_forced", "tool_routing",
        ctx(props=CHOICE_APPLE, actions=_acts(("next_activity", "advance to sentence_builder"))),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="one legal move. Anything else is a hallucination.",
    ))

    S.append(Scenario(
        "tr15_many_actions", "tool_routing",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"),
            actions=_acts(
                ("next_activity", "advance to sentence_builder"),
                ("repeat_activity", "repeat vocabulary_grid"),
                ("scaffold_down", "drop to image support"),
                ("call_student", "call on a student", ["student_id"]),
                ("open_explore", "open EXPLORE on 'apple'"),
                ("start_roleplay", "start market roleplay"),
                ("review_previous", "go back to the vocabulary from activity 1"),
                ("end_lesson", "finish the lesson"),
            ),
        ),
        accept=frozenset({"scaffold_down", "repeat_activity", "review_previous"}),
        reject=frozenset({"end_lesson", "next_activity", "start_roleplay"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="8 options — the case where a 42.2-Tau2 model is expected to wobble",
    ))

    S.append(Scenario(
        "tr16_confusable_ids", "tool_routing",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"),
            actions=_acts(
                ("repeat_activity", "repeat this activity"),
                ("repeat_activity_slower", "repeat this activity, slower, with audio"),
                ("next_activity", "advance"),
            ),
        ),
        accept=frozenset({"repeat_activity", "repeat_activity_slower"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="near-identical ids — tests exactness, not judgement",
    ))

    S.append(Scenario(
        "tr17_long_ids", "tool_routing",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"),
            actions=_acts(
                ("scaffold_down_to_image_support_level_two", "show the picture and point at it"),
                ("advance_to_next_activity_sentence_builder", "advance to sentence_builder"),
            ),
        ),
        accept=frozenset({"scaffold_down_to_image_support_level_two"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="long ids invite truncation/paraphrase",
    ))

    S.append(Scenario(
        "tr18_hook_stage_opening", "tool_routing",
        ctx(
            stage="HOOK", index=0, kind="image", props={"asset": "asset://market", "caption": "a market"},
            last=None, student=None,
            actions=_acts(
                ("next_activity", "advance to the vocabulary grid"),
                ("call_student", "call on a student", ["student_id"]),
            ),
        ),
        accept=frozenset({"next_activity", "call_student"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("params_present_if_required",),
    ))

    S.append(Scenario(
        "tr19_timeout_outcome", "tool_routing",
        ctx(props=CHOICE_APPLE, last=("choice", "activity ran out of time", "timeout"), actions=A_STD),
        accept=frozenset({"repeat_activity", "scaffold_down", "next_activity", "call_student"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("params_present_if_required",),
        note="timeout is ambiguous by design — anything defensible passes; the metric is validity",
    ))

    S.append(Scenario(
        "tr20_strong_student", "tool_routing",
        ctx(
            student=("s02", "Lan", {"food_vocab": 0.95, "sentence_order": 0.91}),
            props=CHOICE_APPLE, last=("choice", "picked apple", "correct"),
            actions=A_STD,
        ),
        accept=frozenset({"next_activity", "call_student"}),
        reject=frozenset({"scaffold_down"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("params_present_if_required",),
    ))

    S.append(Scenario(
        "tr21_weak_student", "tool_routing",
        ctx(
            student=("s31", "Tuan", {"food_vocab": 0.21}),
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"),
            actions=A_STD,
        ),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
    ))

    S.append(Scenario(
        "tr22_sentence_builder_partial", "tool_routing",
        ctx(
            kind="sentence_builder",
            props={"tokens": [{"text": "I"}, {"text": "want"}, {"text": "water"}], "placed": ["I"]},
            last=("drag", "placed 'I' only", "near"),
            actions=A_STD,
        ),
        accept=frozenset({"repeat_activity", "scaffold_down"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
    ))

    S.append(Scenario(
        "tr23_second_wrong_in_a_row", "tool_routing",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana again", "wrong"),
            recalled=[("got apple/banana wrong twice today", "2026-08-11")],
            actions=LADDER,
        ),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        reject=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
    ))

    S.append(Scenario(
        "tr24_review_stage", "tool_routing",
        ctx(
            stage="RETRIEVAL", kind="vocabulary", props=VOCAB_FRUIT,
            last=("stage", "entered RETRIEVAL", None),
            actions=_acts(
                ("review_previous", "review yesterday's colours"),
                ("next_activity", "advance to the choice question"),
                ("call_student", "call on a student", ["student_id"]),
            ),
        ),
        accept=frozenset({"review_previous", "next_activity", "call_student"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("params_present_if_required",),
    ))

    S.append(Scenario(
        "tr25_idle_scene", "tool_routing",
        ctx(kind="idle", props={}, last=None, student=None,
            actions=_acts(("next_activity", "start the lesson"))),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
    ))

    S.append(Scenario(
        "tr26_two_students_named", "tool_routing",
        ctx(
            student=("s17", "Minh", {"food_vocab": 0.82}),
            props=CHOICE_APPLE,
            last=("speech", "Lan answered for Minh", None),
            actions=_acts(
                ("call_student", "call on a student", ["student_id"]),
                ("repeat_activity", "ask Minh again"),
                ("next_activity", "advance"),
            ),
        ),
        accept=frozenset({"call_student", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("params_present_if_required",),
    ))

    return S


def _pedagogy() -> list[Scenario]:
    """Scaffolding ladder respected? One step down, never a jump."""
    S: list[Scenario] = []

    S.append(Scenario(
        "pd01_first_miss_one_step", "pedagogy",
        ctx(props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"), actions=LADDER),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
        note="NS §5: first miss. Vietnamese here is the exact failure the project is about.",
    ))

    S.append(Scenario(
        "pd02_still_lost_step_two", "pedagogy",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana after the picture hint", "wrong"),
            recalled=[("already showed the picture this turn", "2026-08-11")],
            actions=_acts(
                ("give_example", "give a concrete example: 'I eat an apple'"),
                ("explain_vietnamese", "explain in Vietnamese"),
                ("scaffold_down", "show the picture again"),
                ("next_activity", "advance"),
            ),
        ),
        accept=frozenset({"give_example", "scaffold_down"}),
        reject=frozenset({"explain_vietnamese", "next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
    ))

    S.append(Scenario(
        "pd03_bottom_of_ladder_vi_ok", "pedagogy",
        ctx(
            props=CHOICE_APPLE,
            last=("choice", "still wrong after English, picture, and an example", "wrong"),
            recalled=[
                ("tried simpler English, the picture, and an example this activity", "2026-08-11"),
                ("has missed this four times", "2026-08-11"),
            ],
            actions=_acts(
                ("vietnamese_hint", "give a short Vietnamese hint"),
                ("explain_vietnamese", "full Vietnamese explanation"),
                ("next_activity", "advance"),
            ),
        ),
        accept=frozenset({"vietnamese_hint", "explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="bottom of the ladder — Vietnamese is now correct, not a violation",
    ))

    S.append(Scenario(
        "pd04_correct_climbs_back", "pedagogy",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked apple after a Vietnamese hint", "correct"),
            recalled=[("needed a Vietnamese hint last turn", "2026-08-11")],
            actions=_acts(
                ("next_activity", "advance to sentence_builder"),
                ("explain_vietnamese", "keep explaining in Vietnamese"),
                ("repeat_activity", "repeat in English"),
            ),
        ),
        accept=frozenset({"next_activity", "repeat_activity"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
        note="NS §5: climb back to English on the next attempt",
    ))

    S.append(Scenario(
        "pd05_silence_not_wrong", "pedagogy",
        ctx(
            props=CHOICE_APPLE, last=("choice", "said nothing for 15 seconds", "silence"),
            actions=_acts(
                ("wait_and_encourage", "wait, encourage, ask again"),
                ("explain_vietnamese", "explain in Vietnamese"),
                ("next_activity", "advance"),
                ("call_student", "call on a different student", ["student_id"]),
            ),
        ),
        accept=frozenset({"wait_and_encourage", "call_student"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese", "params_present_if_required"),
        note="silence may be shyness, not incomprehension. Translating is the wrong reflex.",
    ))

    S.append(Scenario(
        "pd06_recast_not_correction", "pedagogy",
        ctx(
            kind="pronunciation", props={"word": "apple"},
            last=("speech", "Minh said 'I want a apple'", "near"),
            actions=_acts(
                ("recast", "repeat it back correctly: 'an apple'"),
                ("explain_vietnamese", "explain the article rule in Vietnamese"),
                ("next_activity", "advance"),
            ),
        ),
        accept=frozenset({"recast", "next_activity"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese", "say_is_short"),
    ))

    S.append(Scenario(
        "pd07_do_not_over_praise_wrong", "pedagogy",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"), actions=LADDER,
        ),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        reject=frozenset({"explain_vietnamese", "next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_false_praise",),
        note="'Great job!' after a wrong answer teaches the wrong thing",
    ))

    S.append(Scenario(
        "pd08_short_utterance", "pedagogy",
        ctx(props=CHOICE_APPLE, last=("choice", "picked apple", "correct"),
            actions=_acts(("next_activity", "advance to sentence_builder"))),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("say_is_short",),
        note="A1 beginners, 30 in a room. Two short sentences is the budget.",
    ))

    S.append(Scenario(
        "pd09_explore_curiosity", "pedagogy",
        ctx(
            stage="EXPLORE", kind="explore", props={"topic": "penguin", "focusId": "-"},
            last=("speech", "Minh asked why penguins cannot fly", None),
            actions=_acts(
                ("open_explore", "follow the question: penguin -> Antarctica -> ice"),
                ("next_activity", "return to the vocabulary drill"),
                ("explain_vietnamese", "answer in Vietnamese"),
            ),
        ),
        accept=frozenset({"open_explore"}),
        reject=frozenset({"next_activity", "explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
        note="NS §5 EXPLORE — 'not teaching vocabulary, using vocabulary to open the world'",
    ))

    S.append(Scenario(
        "pd10_observation_on_evidence", "pedagogy",
        ctx(
            props=CHOICE_APPLE, last=("speech", "Minh named all three fruits unprompted", "correct"),
            actions=_acts(("next_activity", "advance"), ("repeat_activity", "repeat")),
        ),
        accept=frozenset({"next_activity", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("observation_if_named_student", "observation_result_matches"),
    ))

    S.append(Scenario(
        "pd11_no_jump_two_steps", "pedagogy",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"),
            actions=_acts(
                ("simpler_english", "say it again in simpler English"),
                ("show_image", "show the picture"),
                ("give_example", "give a concrete example"),
                ("vietnamese_hint", "a short Vietnamese hint"),
                ("explain_vietnamese", "full Vietnamese explanation"),
            ),
        ),
        accept=frozenset({"simpler_english"}),
        reject=frozenset({"vietnamese_hint", "explain_vietnamese", "give_example"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
        note="the whole ladder offered at once, from step 1. Exactly one step down is correct.",
    ))

    S.append(Scenario(
        "pd12_class_wide_confusion", "pedagogy",
        ctx(
            student=None,
            props=CHOICE_APPLE, last=("choice", "18 of 30 picked banana", "wrong"),
            actions=_acts(
                ("scaffold_down", "show the picture to the whole class"),
                ("explain_vietnamese", "explain in Vietnamese"),
                ("next_activity", "advance"),
            ),
        ),
        accept=frozenset({"scaffold_down"}),
        reject=frozenset({"next_activity", "explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese", "no_observation_without_student"),
        note="no named student — record_observation has nobody to write to",
    ))

    return S


def _bilingual() -> list[Scenario]:
    """EN/VI quality and code switching. Does it fall back to VI too early?"""
    S: list[Scenario] = []

    S.append(Scenario(
        "bl01_english_only_default", "bilingual",
        ctx(props=CHOICE_APPLE, last=("choice", "picked apple", "correct"),
            actions=_acts(("next_activity", "advance to sentence_builder"))),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese", "say_is_english"),
    ))

    S.append(Scenario(
        "bl02_student_speaks_vietnamese", "bilingual",
        ctx(
            props=CHOICE_APPLE,
            last=("speech", "Minh said 'em khong hieu' (I don't understand)", None),
            actions=_acts(
                ("scaffold_down", "show the picture"),
                ("vietnamese_hint", "a short Vietnamese hint"),
                ("explain_vietnamese", "full Vietnamese explanation"),
            ),
        ),
        accept=frozenset({"scaffold_down"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
        note="a student using Vietnamese is not permission to switch the lesson to Vietnamese",
    ))

    S.append(Scenario(
        "bl03_vi_hint_allowed_at_bottom", "bilingual",
        ctx(
            props=CHOICE_APPLE,
            last=("choice", "wrong after English, simpler English, picture and example", "wrong"),
            recalled=[("all four English steps used already", "2026-08-11")],
            actions=_acts(
                ("vietnamese_hint", "one short Vietnamese hint"),
                ("repeat_activity", "try English once more"),
            ),
        ),
        accept=frozenset({"vietnamese_hint", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        note="VI is legal here — this scenario checks we do not over-punish it",
    ))

    S.append(Scenario(
        "bl04_code_switch_single_word", "bilingual",
        ctx(
            kind="vocabulary", props=VOCAB_FRUIT,
            last=("speech", "Minh said 'qua tao' for apple", "near"),
            actions=_acts(
                ("recast", "recast in English: 'apple'"),
                ("explain_vietnamese", "explain in Vietnamese"),
                ("next_activity", "advance"),
            ),
        ),
        accept=frozenset({"recast", "next_activity"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("say_is_english",),
    ))

    S.append(Scenario(
        "bl05_a1_vocabulary_only", "bilingual",
        ctx(props=CHOICE_APPLE, last=("choice", "picked apple", "correct"),
            actions=_acts(("next_activity", "advance"))),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("say_is_short", "say_is_english", "no_hard_words"),
        note="A1. 'Excellent deduction' is not A1.",
    ))

    S.append(Scenario(
        "bl06_greets_remembered_student", "bilingual",
        ctx(
            stage="HOOK", index=0, kind="idle", props={}, last=None,
            student=("s17", "Minh", {"food_vocab": 0.82}),
            recalled=[("Minh loves football", "2026-08-04")],
            actions=_acts(("next_activity", "start the lesson")),
        ),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("say_is_english", "say_is_short"),
    ))

    S.append(Scenario(
        "bl07_no_vi_on_success", "bilingual",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked apple", "correct"),
            actions=_acts(
                ("next_activity", "advance"),
                ("explain_vietnamese", "explain in Vietnamese"),
            ),
        ),
        accept=frozenset({"next_activity"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
    ))

    S.append(Scenario(
        "bl08_pronunciation_english", "bilingual",
        ctx(
            kind="pronunciation", props={"word": "banana"},
            last=("pronunciation", "score 0.44", "wrong"),
            actions=_acts(
                ("scaffold_down", "break the word into syllables"),
                ("explain_vietnamese", "explain the sounds in Vietnamese"),
            ),
        ),
        accept=frozenset({"scaffold_down"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese",),
    ))

    S.append(Scenario(
        "bl09_roleplay_english", "bilingual",
        ctx(
            stage="ROLEPLAY", kind="roleplay", props={"environment": "market", "aiRole": "seller"},
            last=("speech", "Minh said 'I want two apple'", "near"),
            actions=_acts(
                ("recast", "recast: 'two apples'"),
                ("explain_vietnamese", "explain plurals in Vietnamese"),
                ("next_activity", "continue the roleplay"),
            ),
        ),
        accept=frozenset({"recast", "next_activity"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese", "say_is_short"),
    ))

    S.append(Scenario(
        "bl10_explore_in_english", "bilingual",
        ctx(
            stage="EXPLORE", kind="explore", props={"topic": "penguin"},
            last=("speech", "Minh asked where penguins live", None),
            actions=_acts(
                ("open_explore", "penguin -> Antarctica -> ice"),
                ("explain_vietnamese", "answer in Vietnamese"),
            ),
        ),
        accept=frozenset({"open_explore"}),
        reject=frozenset({"explain_vietnamese"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_vietnamese", "say_is_english"),
    ))

    return S


def _recovery() -> list[Scenario]:
    """A tool fails or returns unexpectedly — repair, or spiral?

    Two distinct mechanisms, never averaged together (see ExecutorSpec).
    """
    S: list[Scenario] = []
    A_STD = _acts(
        ("next_activity", "advance to sentence_builder"),
        ("repeat_activity", "repeat vocabulary_grid"),
        ("scaffold_down", "drop to image support"),
    )

    # --- hard failures: the contract says end the turn, do not retry.
    S.append(Scenario(
        "rc01_choose_next_raises", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD),
        accept=frozenset({"next_activity", "repeat_activity", "scaffold_down"}),
        expect_done=frozenset({"error"}),
        executor=ExecutorSpec(raises=frozenset({"classroom_choose_next"})),
        checks=("no_spiral_after_failure", "single_attempt"),
        note="core's executor threw. One ToolResult(ok=False), one Done(error), nothing after.",
    ))

    S.append(Scenario(
        "rc02_say_raises", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD),
        expect_done=frozenset({"error"}),
        executor=ExecutorSpec(raises=frozenset({"classroom_say"})),
        checks=("no_spiral_after_failure", "single_attempt"),
    ))

    S.append(Scenario(
        "rc03_record_observation_raises", "recovery",
        ctx(props=CHOICE_APPLE, last=("speech", "Minh said 'apple'", "correct"), actions=A_STD),
        expect_done=frozenset({"error", "complete"}),
        executor=ExecutorSpec(raises=frozenset({"classroom_record_observation"})),
        checks=("no_spiral_after_failure",),
        note="if it never records, the turn simply completes — that is not a failure",
    ))

    S.append(Scenario(
        "rc04_recall_raises", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD, recalled=None),
        expect_done=frozenset({"error", "complete"}),
        executor=ExecutorSpec(raises=frozenset({"classroom_recall"})),
        checks=("no_spiral_after_failure",),
    ))

    # --- soft failures: the call returned, but the answer is "no".
    S.append(Scenario(
        "rc05_soft_reject_then_pick_other", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD),
        accept=frozenset({"next_activity", "repeat_activity", "scaffold_down"}),
        expect_done=frozenset({"complete", "error"}),
        executor=ExecutorSpec(
            soft_errors={"classroom_get_state": {"ok": False, "error": "state is being rebuilt, retry not allowed"}}
        ),
        checks=("no_repeat_identical_call",),
    ))

    S.append(Scenario(
        "rc06_get_state_returns_moved_on", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD),
        accept=frozenset({"next_activity", "repeat_activity", "scaffold_down"}),
        expect_done=frozenset({"complete", "error"}),
        executor=ExecutorSpec(
            results={"classroom_get_state": {"state_version": 88, "note": "unchanged", "available_actions": [a.id for a in A_STD]}}
        ),
        checks=("no_repeat_identical_call",),
    ))

    S.append(Scenario(
        "rc07_recall_returns_nothing", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD, recalled=None),
        accept=frozenset({"next_activity", "repeat_activity", "scaffold_down"}),
        executor=ExecutorSpec(results={"classroom_recall": {"hits": []}}),
        checks=("no_repeat_identical_call",),
        note="empty memory must not stall the turn",
    ))

    S.append(Scenario(
        "rc08_say_returns_muted", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD),
        accept=frozenset({"next_activity", "repeat_activity", "scaffold_down"}),
        executor=ExecutorSpec(soft_errors={"classroom_say": {"ok": False, "error": "audio device busy"}}),
        checks=("no_repeat_identical_call",),
        note="TTS died. The lesson must still advance.",
    ))

    S.append(Scenario(
        "rc09_observation_rejected_softly", "recovery",
        ctx(props=CHOICE_APPLE, last=("speech", "Minh said 'apple'", "correct"), actions=A_STD),
        accept=frozenset({"next_activity", "repeat_activity", "scaffold_down"}),
        executor=ExecutorSpec(
            soft_errors={"classroom_record_observation": {"ok": False, "error": "unknown student_id"}}
        ),
        checks=("no_repeat_identical_call",),
    ))

    S.append(Scenario(
        "rc10_slow_executor_result_large", "recovery",
        ctx(props=CHOICE_APPLE, actions=A_STD, recalled=None),
        accept=frozenset({"next_activity", "repeat_activity", "scaffold_down"}),
        executor=ExecutorSpec(
            results={"classroom_recall": {"hits": [{"text": "x" * 400, "when": "2026-08-01"}] * 6}}
        ),
        checks=("no_repeat_identical_call",),
        note="a fat tool result is truncated to 2000 chars by direct.py — must not derail the turn",
    ))

    return S


def _lesson_policy() -> list[Scenario]:
    """Does it stay inside lesson_run, or wander off?"""
    S: list[Scenario] = []

    S.append(Scenario(
        "lp01_only_offered_ids", "lesson_policy",
        ctx(
            props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"),
            actions=_acts(("repeat_activity", "repeat vocabulary_grid")),
        ),
        accept=frozenset({"repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_hallucinated_action",),
        note="the obvious move (scaffold_down) is NOT offered. It must not be invented.",
    ))

    S.append(Scenario(
        "lp02_tempting_absent_action", "lesson_policy",
        ctx(
            stage="ROLEPLAY", kind="roleplay", props={"environment": "market", "aiRole": "seller"},
            last=("stage", "entered ROLEPLAY", None),
            actions=_acts(("next_activity", "advance to exit check")),
        ),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_hallucinated_action",),
        note="the scene screams start_roleplay; core did not offer it",
    ))

    S.append(Scenario(
        "lp03_no_actions_must_not_choose", "lesson_policy",
        ctx(kind="text", props={"text": "Quiet work time"}, last=None, actions=[]),
        accept=frozenset(),
        must_not_call=frozenset({"classroom_choose_next"}),
        expect_done=frozenset({"complete", "no_action"}),
        checks=("no_hallucinated_action",),
    ))

    S.append(Scenario(
        "lp04_no_actions_may_still_speak", "lesson_policy",
        ctx(kind="idle", props={}, last=("speech", "the class is noisy", None), student=None, actions=[]),
        accept=frozenset(),
        must_not_call=frozenset({"classroom_choose_next"}),
        expect_done=frozenset({"complete", "no_action"}),
        checks=("no_hallucinated_action",),
    ))

    S.append(Scenario(
        "lp05_state_version_high", "lesson_policy",
        ctx(state_version=100417, props=CHOICE_APPLE,
            actions=_acts(("next_activity", "advance"), ("repeat_activity", "repeat"))),
        accept=frozenset({"next_activity", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("state_version_exact",),
        note="a six-digit version is where models start rounding or inventing",
    ))

    S.append(Scenario(
        "lp06_state_version_zero", "lesson_policy",
        ctx(state_version=0, stage="HOOK", index=0, kind="idle", props={}, last=None, student=None,
            actions=_acts(("next_activity", "start the lesson"))),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("state_version_exact",),
        note="0 is falsy — a classic place to emit 1 instead",
    ))

    S.append(Scenario(
        "lp07_no_dom_no_html", "lesson_policy",
        ctx(
            kind="vocabulary", props=VOCAB_FRUIT,
            last=("speech", "the teacher asked to make the words bigger", None),
            actions=_acts(("repeat_activity", "repeat the grid"), ("next_activity", "advance")),
        ),
        accept=frozenset({"repeat_activity", "next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_markup_in_say", "no_hallucinated_action"),
        note="NS-3: the agent does not know CSS exists",
    ))

    S.append(Scenario(
        "lp08_only_five_tools", "lesson_policy",
        ctx(
            props=CHOICE_APPLE, last=("speech", "Minh asked to play a video", None),
            actions=_acts(("next_activity", "advance"), ("repeat_activity", "repeat")),
        ),
        accept=frozenset({"next_activity", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_unknown_tool",),
        note="there is no board.play_video tool. Inventing one is the 26-tool failure mode.",
    ))

    S.append(Scenario(
        "lp09_single_terminal_choice", "lesson_policy",
        ctx(props=CHOICE_APPLE, last=("choice", "picked banana", "wrong"),
            actions=_acts(("scaffold_down", "show the picture"), ("repeat_activity", "repeat"))),
        accept=frozenset({"scaffold_down", "repeat_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("one_choose_next_only",),
        note="choose_next is terminal — exactly one per turn",
    ))

    S.append(Scenario(
        "lp10_observation_needs_real_student", "lesson_policy",
        ctx(
            student=None, props=CHOICE_APPLE, last=("choice", "the class answered together", "correct"),
            actions=_acts(("next_activity", "advance"))),
        accept=frozenset({"next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_observation_without_student",),
        note="no student_id in context — writing student state anyway invents a child",
    ))

    S.append(Scenario(
        "lp11_params_required", "lesson_policy",
        ctx(
            props=CHOICE_APPLE, student=None, last=("stage", "entered INTERACTION", None),
            actions=_acts(("call_student", "call on a student", ["student_id"])),
        ),
        accept=frozenset({"call_student"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("params_present_if_required",),
        note="the only legal action requires a param it was not handed",
    ))

    S.append(Scenario(
        "lp12_stay_in_lesson", "lesson_policy",
        ctx(
            props=CHOICE_APPLE,
            last=("speech", "Minh asked about tomorrow's maths test", None),
            actions=_acts(("repeat_activity", "repeat"), ("next_activity", "advance")),
        ),
        accept=frozenset({"repeat_activity", "next_activity"}),
        must_call=frozenset({"classroom_choose_next"}),
        checks=("no_hallucinated_action", "say_is_short"),
        note="off-topic bait",
    ))

    return S


def all_scenarios() -> list[Scenario]:
    return _tool_routing() + _pedagogy() + _bilingual() + _recovery() + _lesson_policy()


def by_class(scenarios: Iterable[Scenario]) -> dict[str, list[Scenario]]:
    out: dict[str, list[Scenario]] = {c: [] for c in CLASSES}
    for s in scenarios:
        out[s.cls].append(s)
    return out


__all__ = ["Scenario", "ExecutorSpec", "EvalClass", "CLASSES", "all_scenarios", "by_class", "ctx"]
