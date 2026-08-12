"""Offline tests for the eval suite itself.

An eval you cannot trust is worse than no eval, because it produces numbers.
These run with no network and no cassette: they pin the grader logic, the
Tier C parser and the corpus's own invariants.
"""

from __future__ import annotations

import json

import pytest
from bright_contracts import AvailableAction

from bright_agent.tools import CHOOSE_NEXT, SAY, build_tools
from evals import graders, variants
from evals.runner import Trace
from evals.scenarios import CLASSES, Scenario, all_scenarios, ctx

# ------------------------------------------------------------ the corpus


def test_corpus_shape():
    S = all_scenarios()
    assert len(S) == 70
    ids = [s.id for s in S]
    assert len(ids) == len(set(ids)), "duplicate scenario ids"
    # SP-3's kill criterion is on tool_routing; it needs the resolution.
    assert sum(1 for s in S if s.cls == "tool_routing") >= 25


def test_every_check_name_exists():
    unknown = {n for s in all_scenarios() for n in s.checks} - set(graders.CHECKS)
    assert not unknown, f"scenarios reference checks that do not exist: {unknown}"


def test_accept_and_reject_are_actually_offered():
    """An expectation naming an action core never offers is a broken scenario."""
    for s in all_scenarios():
        legal = {a.id for a in s.ctx.available_actions}
        assert s.accept <= legal, f"{s.id}: accept {s.accept - legal} not in available_actions"
        assert s.reject <= legal, f"{s.id}: reject {s.reject - legal} not in available_actions"
        assert not (s.accept & s.reject), f"{s.id}: an action is both accepted and rejected"


def test_scenarios_with_no_actions_expect_no_choice():
    for s in all_scenarios():
        if not s.ctx.available_actions:
            assert not s.accept
            assert CHOOSE_NEXT in s.must_not_call


# ------------------------------------------------------- language graders


@pytest.mark.parametrize(
    "text",
    ["Quả táo màu đỏ.", "Em không hiểu à?", "day la mot qua tao", "Nghia la apple, cac em"],
)
def test_detects_vietnamese(text):
    assert graders.looks_vietnamese(text)


@pytest.mark.parametrize(
    "text",
    [
        "Look at the picture. Which one is the apple?",
        "Good try, Minh! Let's look again.",
        "Lan, can you say banana?",
        "Tuan, point to the mango.",
    ],
)
def test_does_not_flag_english_or_names(text):
    # Minh / Lan / Tuan are unmarked Vietnamese names in English sentences.
    assert not graders.looks_vietnamese(text)


def test_say_length_check():
    sc = all_scenarios()[0]
    long = Trace("x", "v", "m", tool_calls=[{"call_id": "1", "name": SAY,
                 "arguments": {"text": " ".join(["word"] * 60) + "."}}])
    assert graders.CHECKS["say_is_short"](sc, long)
    short = Trace("x", "v", "m", tool_calls=[{"call_id": "1", "name": SAY,
                  "arguments": {"text": "Look at the picture."}}])
    assert graders.CHECKS["say_is_short"](sc, short) is None


def test_act_tokens_do_not_count_as_speech():
    sc = all_scenarios()[0]
    tr = Trace("x", "v", "m", tool_calls=[{"call_id": "1", "name": SAY,
               "arguments": {"text": '<|ACT {"emotion":"happy"}|> Good try!'}}])
    assert graders.CHECKS["no_markup_in_say"](sc, tr) is None


# ------------------------------------------------------------ arg schemas


def test_args_valid_rejects_bad_enum_and_types():
    c = ctx(actions=[AvailableAction(id="next_activity", label="advance")])
    tools = build_tools(c)
    ok = {"name": CHOOSE_NEXT, "arguments": {"state_version": 88, "action_id": "next_activity"}}
    assert graders.args_valid(ok, tools)
    assert not graders.args_valid(
        {"name": CHOOSE_NEXT, "arguments": {"state_version": 88, "action_id": "invented"}}, tools
    )
    assert not graders.args_valid(
        {"name": CHOOSE_NEXT, "arguments": {"state_version": "88", "action_id": "next_activity"}}, tools
    )
    assert not graders.args_valid({"name": CHOOSE_NEXT, "arguments": {"action_id": "next_activity"}}, tools)
    assert not graders.args_valid({"name": "board_show_video", "arguments": {}}, tools)


# ------------------------------------------------------------ Tier C parse


@pytest.mark.parametrize(
    "raw",
    [
        '{"say":"Look again.","action_id":"scaffold_down","state_version":88}',
        '```json\n{"say":"Look again.","action_id":"scaffold_down","state_version":88}\n```',
        'Sure! {"say":"Look again.","action_id":"scaffold_down","state_version":88} done',
        '{"say":"He said \\"apple\\" }","action_id":"scaffold_down","state_version":88}',
    ],
)
def test_tier_c_parses(raw):
    obj, err = variants.parse_tier_c(raw)
    assert err is None and obj is not None
    assert obj["action_id"] == "scaffold_down"


@pytest.mark.parametrize("raw", ["no json here", '{"say": "unterminated', "{bad json}"])
def test_tier_c_parse_failures_are_reported_not_raised(raw):
    obj, err = variants.parse_tier_c(raw)
    assert obj is None and err


# --------------------------------------------------------------- variants


def test_static_schema_tool_block_is_identical_across_turns():
    """The whole point of the variant: no per-turn bytes in the tool block."""
    a = ctx(actions=[AvailableAction(id="next_activity", label="advance")])
    b = ctx(state_version=999, actions=[AvailableAction(id="open_explore", label="explore penguins")])
    v = variants.get("static_schema")
    assert json.dumps(v.tools_builder(a)) == json.dumps(v.tools_builder(b))  # type: ignore[misc]

    base = variants.get("baseline")
    assert json.dumps(build_tools(a)) != json.dumps(build_tools(b)), "baseline should be volatile"
    _ = base


def test_baseline_tool_block_carries_the_enum():
    c = ctx(actions=[AvailableAction(id="next_activity", label="advance")])
    spec = next(t for t in build_tools(c) if t["function"]["name"] == CHOOSE_NEXT)
    assert spec["function"]["parameters"]["properties"]["action_id"]["enum"] == ["next_activity"]
    v = variants.get("static_schema")
    spec2 = next(t for t in v.tools_builder(c) if t["function"]["name"] == CHOOSE_NEXT)  # type: ignore[misc]
    assert "enum" not in spec2["function"]["parameters"]["properties"]["action_id"]


def test_tier_c_sends_no_tool_block():
    from bright_agent.direct import LLMConfig, build_request_body

    c = ctx(actions=[AvailableAction(id="next_activity", label="advance")])
    v = variants.get("tier_c")
    body = build_request_body(LLMConfig(), v.messages_builder(c), tools=v.tools_builder(c))  # type: ignore[misc]
    assert "tools" not in body
    assert body["thinking"] == {"type": "disabled"}


# ---------------------------------------------------------------- scoring


def _tr(action: str | None, **kw) -> Trace:
    calls = []
    if action is not None:
        calls.append({"call_id": "1", "name": CHOOSE_NEXT,
                      "arguments": {"state_version": 88, "action_id": action}})
    return Trace("x", "v", "m", tool_calls=calls, done_reason=kw.pop("done", "complete"), **kw)


def test_grading_accepts_any_defensible_choice_and_punishes_rejects():
    sc = next(s for s in all_scenarios() if s.id == "tr03_silence_calls_or_scaffolds")
    tools = build_tools(sc.ctx)
    assert graders.grade(sc, _tr("scaffold_down"), tools).selection_ok
    assert graders.grade(sc, _tr("repeat_activity"), tools).selection_ok
    assert not graders.grade(sc, _tr("next_activity"), tools).selection_ok


def test_hallucinated_action_is_flagged():
    sc = next(s for s in all_scenarios() if s.id == "lp01_only_offered_ids")
    g = graders.grade(sc, _tr("scaffold_down"), build_tools(sc.ctx))
    assert g.hallucinated and not g.ok


def test_choosing_when_nothing_is_offered_is_a_hallucination():
    sc = next(s for s in all_scenarios() if s.id == "lp03_no_actions_must_not_choose")
    g = graders.grade(sc, _tr("next_activity"), build_tools(sc.ctx))
    assert g.hallucinated
    assert any("must not" in v for v in g.violations)


def test_spiral_after_hard_failure_is_caught():
    sc = next(s for s in all_scenarios() if s.id == "rc01_choose_next_raises")
    spiral = Trace(
        "x", "v", "m", done_reason="error",
        tool_results=[{"call_id": "1", "name": CHOOSE_NEXT, "ok": False, "error": "boom"},
                      {"call_id": "2", "name": CHOOSE_NEXT, "ok": True, "error": None}],
        executor_calls=[{"name": CHOOSE_NEXT, "arguments": {}}, {"name": CHOOSE_NEXT, "arguments": {}}],
    )
    assert graders.CHECKS["no_spiral_after_failure"](sc, spiral)

    clean = Trace(
        "x", "v", "m", done_reason="error",
        tool_calls=[{"call_id": "1", "name": CHOOSE_NEXT,
                     "arguments": {"state_version": 88, "action_id": "scaffold_down"}}],
        tool_results=[{"call_id": "1", "name": CHOOSE_NEXT, "ok": False, "error": "boom"}],
        executor_calls=[{"name": CHOOSE_NEXT, "arguments": {}}],
    )
    assert graders.CHECKS["no_spiral_after_failure"](sc, clean) is None
    assert graders.grade(sc, clean, build_tools(sc.ctx)).repaired is True


def test_class_metrics_cover_every_class():
    sc = all_scenarios()
    graded = [graders.grade(s, _tr(next(iter(s.accept), None)), build_tools(s.ctx)) for s in sc]
    from evals.report import class_metrics

    ms = class_metrics(graded)
    assert [m.cls for m in ms] == list(CLASSES) + ["ALL"]
    assert ms[-1].n == len(sc)
