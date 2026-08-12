"""The SP-3 metrics.

    tool selection accuracy       policy violation rate
    argument/schema validity      lesson-state consistency
    hallucinated tool rate        repair-after-failure rate
    response latency              tokens

Two rules keep this from grading opinions:

1. **Accuracy is scored against an acceptable set.** A scenario passes if it
   chose any defensible action and avoided the ones marked `reject`.
2. **Policy checks are mechanical.** "Was that good teaching?" is not
   gradeable here; "did it emit Vietnamese on the student's first miss" is.
   Every check below is a string or structural test with no judgement in it.
"""

from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from bright_agent.tools import CHOOSE_NEXT, RECORD_OBSERVATION, SAY, TOOL_NAMES

from .scenarios import Scenario
from .runner import Trace

# --------------------------------------------------------- language checks

#: Vietnamese-specific letters. `Minh`/`Lan`/`Tuan` are unmarked, so a student
#: name never trips this.
_VI_CHARS = re.compile(
    r"[ăâêôơưđĂÂÊÔƠƯĐ]"
    r"|[àáảãạằắẳẵặầấẩẫậèéẻẽẹềếểễệìíỉĩị"
    r"òóỏõọồốổỗộờớởỡợùúủũụừứửữựỳýỷỹỵ]",
    re.IGNORECASE,
)

#: Undiacriticised Vietnamese, which is how it usually arrives from a model.
_VI_WORDS = re.compile(
    r"\b(khong|khoong|ban|minh|em oi|con|qua tao|qua chuoi|nghia la|co nghia|"
    r"tieng viet|hieu khong|dung roi|sai roi|lam tot|rat tot|chung ta|cac em|"
    r"nay la|day la|mot|hai|ba|tao|chuoi|xoai)\b",
    re.IGNORECASE,
)

#: Words above A1. Beginners in a village school do not have these.
_HARD_WORDS = re.compile(
    r"\b(excellent|deduction|precisely|indeed|furthermore|however|therefore|"
    r"consequently|nevertheless|distinguish|comprehend|articulate|utilise|utilize|"
    r"demonstrate|observation|significant|appropriate|essentially|fundamental)\b",
    re.IGNORECASE,
)

_PRAISE = re.compile(
    r"\b(great job|well done|excellent|perfect|correct|that's right|thats right|"
    r"very good|nice work|brilliant|exactly)\b",
    re.IGNORECASE,
)

_MARKUP = re.compile(r"(<[a-z/][^>]*>|\{[^}]*:[^}]*\}|font-size|style=|class=|\bdiv\b|\bspan\b)", re.IGNORECASE)


def looks_vietnamese(text: str) -> bool:
    """Is there Vietnamese in here?

    Deliberately conservative on the ASCII path: a single ambiguous token is
    not enough, because `mot`/`ba` collide with English fragments. Two hits,
    or any Vietnamese diacritic, counts.
    """
    if _VI_CHARS.search(text):
        return True
    return len(set(m.group(0).lower() for m in _VI_WORDS.finditer(text))) >= 2


def sentence_count(text: str) -> int:
    return len([s for s in re.split(r"[.!?]+", re.sub(r"<\|[^|]*\|>", " ", text)) if s.strip()])


def word_count(text: str) -> int:
    return len(re.findall(r"[A-Za-z']+", re.sub(r"<\|[^|]*\|>", " ", text)))


# ------------------------------------------------- lightweight schema check


def _type_ok(value: Any, spec: dict[str, Any]) -> bool:
    t = spec.get("type")
    if t == "string" and not isinstance(value, str):
        return False
    if t == "integer" and (isinstance(value, bool) or not isinstance(value, int)):
        return False
    if t == "object" and not isinstance(value, dict):
        return False
    if "enum" in spec and value not in spec["enum"]:
        return False
    return True


def args_valid(call: dict[str, Any], tools: list[dict[str, Any]]) -> bool:
    """Do the emitted arguments satisfy the tool's own JSON schema?

    Separate from `validation.py`, which asks a *semantic* question (is this
    action legal right now). This asks the syntactic one, which is what the
    provider's decoder is supposed to guarantee.
    """
    spec = next((t["function"] for t in tools if t["function"]["name"] == call["name"]), None)
    if spec is None:
        return False
    params = spec.get("parameters") or {}
    props = params.get("properties") or {}
    args = call["arguments"]
    if not isinstance(args, dict):
        return False
    for req in params.get("required") or []:
        if req not in args:
            return False
    if params.get("additionalProperties") is False:
        for k in args:
            if k not in props:
                return False
    return all(_type_ok(v, props[k]) for k, v in args.items() if k in props)


# ------------------------------------------------------------ policy checks

CheckFn = Callable[[Scenario, Trace], str | None]
CHECKS: dict[str, CheckFn] = {}


def check(name: str) -> Callable[[CheckFn], CheckFn]:
    def deco(fn: CheckFn) -> CheckFn:
        CHECKS[name] = fn
        return fn

    return deco


@check("no_vietnamese")
def _no_vietnamese(sc: Scenario, tr: Trace) -> str | None:
    said = tr.said
    if said and looks_vietnamese(said):
        return f"Vietnamese too early: {said[:70]!r}"
    return None


@check("say_is_english")
def _say_is_english(sc: Scenario, tr: Trace) -> str | None:
    said = tr.said
    if not said.strip():
        return "said nothing"
    if looks_vietnamese(said):
        return f"not English: {said[:70]!r}"
    return None


@check("say_is_short")
def _say_is_short(sc: Scenario, tr: Trace) -> str | None:
    said = tr.said
    if not said.strip():
        return None
    if sentence_count(said) > 3 or word_count(said) > 40:
        return f"{sentence_count(said)} sentences / {word_count(said)} words"
    return None


@check("no_hard_words")
def _no_hard_words(sc: Scenario, tr: Trace) -> str | None:
    hit = _HARD_WORDS.search(tr.said)
    return f"above A1: {hit.group(0)!r}" if hit else None


@check("no_false_praise")
def _no_false_praise(sc: Scenario, tr: Trace) -> str | None:
    outcome = sc.ctx.last_interaction.outcome if sc.ctx.last_interaction else None
    if outcome in ("wrong", "silence") and _PRAISE.search(tr.said):
        return f"praised a {outcome} answer: {_PRAISE.search(tr.said).group(0)!r}"  # type: ignore[union-attr]
    return None


@check("no_markup_in_say")
def _no_markup(sc: Scenario, tr: Trace) -> str | None:
    said = re.sub(r"<\|[^|]*\|>", "", tr.said)  # ACT tokens are legal
    hit = _MARKUP.search(said)
    return f"NS-3 violation, markup in speech: {hit.group(0)!r}" if hit else None


@check("state_version_exact")
def _state_version(sc: Scenario, tr: Trace) -> str | None:
    for c in tr.tool_calls:
        if c["name"] != CHOOSE_NEXT:
            continue
        raw = c["arguments"].get("state_version")
        try:
            if int(raw) != sc.ctx.state_version:  # type: ignore[arg-type]
                return f"state_version={raw!r}, context is {sc.ctx.state_version}"
        except (TypeError, ValueError):
            return f"state_version={raw!r} is not an integer"
    return None


@check("no_hallucinated_action")
def _no_hallucinated(sc: Scenario, tr: Trace) -> str | None:
    legal = {a.id for a in sc.ctx.available_actions}
    a = tr.chosen_action
    if a is None:
        return None
    if not legal:
        return f"chose {a!r} when no actions were offered"
    if a not in legal:
        return f"invented action_id {a!r}"
    return None


@check("no_unknown_tool")
def _no_unknown_tool(sc: Scenario, tr: Trace) -> str | None:
    bad = [c["name"] for c in tr.tool_calls if c["name"] not in TOOL_NAMES]
    return f"invented tools {bad}" if bad else None


@check("one_choose_next_only")
def _one_choose(sc: Scenario, tr: Trace) -> str | None:
    n = sum(1 for c in tr.tool_calls if c["name"] == CHOOSE_NEXT)
    return f"{n} choose_next calls in one turn" if n > 1 else None


@check("params_present_if_required")
def _params_present(sc: Scenario, tr: Trace) -> str | None:
    a = tr.chosen_action
    if a is None:
        return None
    action = next((x for x in sc.ctx.available_actions if x.id == a), None)
    if action is None or not action.params:
        return None
    call = next((c for c in tr.tool_calls if c["name"] == CHOOSE_NEXT), None)
    got = (call or {}).get("arguments", {}).get("params") or {}
    missing = [p for p in action.params if not (isinstance(got, dict) and got.get(p))]
    return f"action {a!r} missing params {missing}" if missing else None


@check("observation_if_named_student")
def _obs_if_named(sc: Scenario, tr: Trace) -> str | None:
    if sc.ctx.student and not tr.observations:
        return "a named student demonstrated something; nothing was recorded"
    return None


@check("observation_result_matches")
def _obs_matches(sc: Scenario, tr: Trace) -> str | None:
    outcome = sc.ctx.last_interaction.outcome if sc.ctx.last_interaction else None
    if outcome is None or not tr.observations:
        return None
    # `timeout` has no direct counterpart in the observation enum; silence is
    # the honest mapping.
    allowed = {"timeout": {"silence", "wrong"}}.get(outcome, {outcome})
    bad = [o.get("result") for o in tr.observations if o.get("result") not in allowed]
    return f"recorded {bad} for an outcome of {outcome!r}" if bad else None


@check("no_observation_without_student")
def _no_obs_without_student(sc: Scenario, tr: Trace) -> str | None:
    if sc.ctx.student is None and tr.observations:
        ids = [o.get("student_id") for o in tr.observations]
        return f"wrote student state for {ids} with no student in context"
    return None


@check("no_spiral_after_failure")
def _no_spiral(sc: Scenario, tr: Trace) -> str | None:
    """After a hard executor failure the turn must stop. No second attempt."""
    failed = [i for i, r in enumerate(tr.tool_results) if not r["ok"]]
    if not failed:
        return None
    first = failed[0]
    after = tr.tool_results[first + 1 :]
    if after:
        return f"{len(after)} more tool results after the failure"
    failed_name = tr.tool_results[first]["name"]
    retries = sum(1 for c in tr.executor_calls if c["name"] == failed_name) - 1
    return f"retried {failed_name} {retries}x" if retries > 0 else None


@check("single_attempt")
def _single_attempt(sc: Scenario, tr: Trace) -> str | None:
    if tr.usage.get("rounds", 1) > 2:
        return f"{tr.usage['rounds']} rounds — a repair loop in front of a class"
    return None


@check("no_repeat_identical_call")
def _no_repeat(sc: Scenario, tr: Trace) -> str | None:
    """A soft failure must not be answered by making the identical call again."""
    seen: set[str] = set()
    for c in tr.executor_calls:
        key = f"{c['name']}:{sorted((c['arguments'] or {}).items(), key=str)}"
        if key in seen:
            return f"repeated the identical call {c['name']}"
        seen.add(key)
    return None


# ---------------------------------------------------------------- scoring


@dataclass
class Graded:
    scenario: Scenario
    trace: Trace
    selection_ok: bool
    args_ok: bool
    hallucinated: bool
    violations: list[str] = field(default_factory=list)
    #: recovery only; None outside that class
    repaired: bool | None = None

    @property
    def ok(self) -> bool:
        return self.selection_ok and self.args_ok and not self.hallucinated and not self.violations


def _selection_ok(sc: Scenario, tr: Trace) -> bool:
    chosen = tr.chosen_action
    legal = {a.id for a in sc.ctx.available_actions}

    if not sc.accept and not sc.reject:
        # "no action expected" scenarios: choosing at all is the error.
        if not legal:
            return chosen is None
        return True

    if sc.expect_done == frozenset({"error"}):
        # The executor was rigged to fail. What we grade is the *proposal*,
        # which happened before the failure, not the (guaranteed) failure.
        return chosen is not None and chosen in sc.accept

    if chosen is None:
        return False
    if chosen in sc.reject:
        return False
    return chosen in sc.accept if sc.accept else chosen in legal


def grade(sc: Scenario, tr: Trace, tools: list[dict[str, Any]]) -> Graded:
    legal = {a.id for a in sc.ctx.available_actions}
    chosen = tr.chosen_action

    hallucinated = bool(
        [c for c in tr.tool_calls if c["name"] not in TOOL_NAMES]
        or (chosen is not None and (not legal or chosen not in legal))
    )

    # Tier C has no tool block; its "schema validity" is whether the JSON
    # parsed and carried the fields the contract needs.
    if tr.parse_error is not None:
        args_ok = False
    elif tools:
        args_ok = all(args_valid(c, tools) for c in tr.tool_calls) if tr.tool_calls else True
    else:
        args_ok = tr.parsed is not None

    violations: list[str] = []
    for name in sc.checks:
        fn = CHECKS.get(name)
        if fn is None:
            violations.append(f"unknown check {name!r}")
            continue
        msg = fn(sc, tr)
        if msg:
            violations.append(f"{name}: {msg}")

    if tr.done_reason not in sc.expect_done:
        violations.append(f"done={tr.done_reason} ({tr.done_detail or ''})"[:110])

    for t in sc.must_call:
        if not any(c["name"] == t for c in tr.tool_calls):
            violations.append(f"never called {t}")
    for t in sc.must_not_call:
        if any(c["name"] == t for c in tr.tool_calls):
            violations.append(f"called {t} when it must not")

    repaired: bool | None = None
    if sc.cls == "recovery":
        if sc.executor.raises:
            # Hard failure: "repair" means terminating cleanly, not retrying.
            repaired = _no_spiral(sc, tr) is None and tr.done_reason in sc.expect_done
        else:
            # Soft failure: did it still get to a legal action without looping?
            repaired = _no_repeat(sc, tr) is None and (chosen in legal if legal else True)

    return Graded(sc, tr, _selection_ok(sc, tr), args_ok, hallucinated, violations, repaired)


# ------------------------------------------------------------- aggregation


@dataclass
class ClassMetrics:
    cls: str
    n: int
    selection_accuracy: float
    arg_validity: float
    hallucinated_rate: float
    policy_violation_rate: float
    repair_rate: float | None
    latency_p50: float
    latency_p95: float
    prompt_tokens: float
    cached_tokens: float
    completion_tokens: float
    error_rate: float


def _pct(xs: list[bool]) -> float:
    return 100.0 * sum(xs) / len(xs) if xs else 0.0


def aggregate(graded: Iterable[Graded], cls: str) -> ClassMetrics:
    g = [x for x in graded if x.scenario.cls == cls] if cls != "ALL" else list(graded)
    if not g:
        return ClassMetrics(cls, 0, *([0.0] * 4), None, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0)  # type: ignore[arg-type]
    lat = sorted(t.trace.latency_s for t in g)
    reps = [x.repaired for x in g if x.repaired is not None]
    return ClassMetrics(
        cls=cls,
        n=len(g),
        selection_accuracy=_pct([x.selection_ok for x in g]),
        arg_validity=_pct([x.args_ok for x in g]),
        hallucinated_rate=_pct([x.hallucinated for x in g]),
        policy_violation_rate=_pct([bool(x.violations) for x in g]),
        repair_rate=(100.0 * sum(reps) / len(reps)) if reps else None,
        latency_p50=statistics.median(lat),
        latency_p95=lat[min(len(lat) - 1, int(0.95 * len(lat)))],
        prompt_tokens=statistics.mean([x.trace.usage.get("prompt_tokens", 0) for x in g]),
        cached_tokens=statistics.mean([x.trace.usage.get("cached_tokens", 0) for x in g]),
        completion_tokens=statistics.mean([x.trace.usage.get("completion_tokens", 0) for x in g]),
        error_rate=_pct([x.trace.done_reason == "error" and "error" not in x.scenario.expect_done for x in g]),
    )


__all__ = ["grade", "aggregate", "Graded", "ClassMetrics", "CHECKS", "looks_vietnamese", "args_valid"]
