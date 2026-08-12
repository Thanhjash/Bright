"""`ScriptedAgent` — a deterministic `TeacherAgent`.

**This is not a language model and must never be described as one.**
It contains no inference of any kind. It is a lookup table of teacher lines
a human wrote and approved, keyed by (activity id, outcome), delivered
through the exact same constrained-action interface `DirectAgent` uses.

Why it exists (docs/5-research/2026-08-11-codex-deadline-review.md §5): the
hosted model is the single cloud dependency in the system. When it is slow
or unreachable, `AutoTurn` bounds the damage at 6 s and falls back to the
authored branch — the lesson survives, but the room watches a six-second
hole, once per graded answer, until the next 60 s health probe. That is
good availability and bad theater. This class is the insurance: the same
architecture, the same seam, the same rules, running from a data file at
zero latency.

What it demonstrates honestly:
  * that `TeacherAgent` is a real seam — core cannot tell the two apart;
  * that the constrained-action design (core offers, the agent picks one)
    is enforced on our side of the boundary regardless of what is deciding;
  * that the lesson keeps its adaptive shape with no network at all.

What it does **not** demonstrate: local intelligence, generalisation, or
any ability to respond to something the script did not anticipate. Say so
out loud before anybody asks.

Rules it obeys, identical to `DirectAgent` (docs/3-design/architecture.md §3):
  * it only ever proposes an `action_id` core offered *this turn*;
  * it sends `ctx.state_version` unchanged;
  * every proposal goes through `validation.validate_call` before the
    executor sees it — a bad script line fails exactly like a bad model turn;
  * single attempt, no repair loop;
  * exactly one `Done` per turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, AsyncIterator, Literal

from bright_contracts import TurnContext
from pydantic import BaseModel, Field

from .act import ActEmitter
from .base import AgentEvent, Done, ToolCall, ToolResult, TurnUsage
from .tools import CHOOSE_NEXT, RECORD_OBSERVATION, SAY, ToolExecutor
from .validation import Rejection, validate_call

log = logging.getLogger("bright.agent.scripted")

#: The key used for the pre-lesson greeting turn — the one turn that arrives
#: with no `last_interaction` (classroom-core `Core._greet`).
GREETING = "greeting"

#: Everything else is keyed by the graded outcome. `any` is the catch-all.
OUTCOME_KEYS = ("correct", "near", "wrong", "silence", "timeout", "any")

#: `classroom_record_observation` has no `timeout` result (validation.py).
_OBSERVATION_RESULT = {
    "correct": "correct",
    "near": "near",
    "wrong": "wrong",
    "silence": "silence",
    "timeout": "silence",
}

DEFAULT_SCRIPT_PATH = Path(__file__).resolve().parent / "data" / "demo_script.json"


# ----------------------------------------------------------------- schema


class ScriptedObservation(BaseModel):
    """One `classroom_record_observation` call, pre-authored."""

    skill: str
    #: Omit to record the turn's own outcome.
    result: Literal["correct", "near", "wrong", "silence"] | None = None
    evidence: str = ""


class ScriptedResponse(BaseModel):
    """What the teacher says and does for one (activity, outcome) pair."""

    #: One or two short sentences. May carry inline `<|ACT {...}|>` tokens,
    #: exactly as a model's `classroom_say` argument may.
    say: str = ""
    style: str | None = None
    #: Seconds to wait before speaking. Not latency padding — classroom-core
    #: speaks the authored branch narration at reflex speed (3 ms) and
    #: `speech.say` *interrupts* rather than queues, so a 0 ms teacher line
    #: would cut off the line the class is already hearing. The live model
    #: gets this spacing for free by being slow; we have to ask for it.
    say_delay_s: float | None = Field(default=None, alias="sayDelayS")
    observe: ScriptedObservation | None = None
    #: Action ids in preference order, e.g. ["goto:q_legs", "next_activity"].
    #: The first one core actually offered this turn wins. Anything not
    #: offered is skipped, never proposed.
    prefer: list[str] = Field(default_factory=list)
    #: Authoring note. Never spoken, never sent anywhere.
    note: str | None = None

    model_config = {"populate_by_name": True}


class ScriptedActivity(BaseModel):
    activity_id: str = Field(alias="activityId")
    #: Optional cross-check against `ctx.scene.kind`. A mismatch is logged,
    #: not fatal — the index is still the authority.
    scene: str | None = None
    responses: dict[str, ScriptedResponse] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class LessonScript(BaseModel):
    """A whole lesson's worth of pre-approved teacher turns.

    `activities` is positional: entry *i* is the response set for
    `activity_index == i`. That is the only key `TurnContext` actually
    carries (there is no activity id on the wire), and the ids are recorded
    alongside so the file is readable and can be checked against the
    `lesson_run` it belongs to.
    """

    v: int = 1
    name: str = "unnamed"
    lesson_id: str | None = Field(default=None, alias="lessonId")
    note: str | None = None
    #: Default `sayDelayS` for every response in this file.
    say_delay_s: float = Field(default=0.0, alias="sayDelayS")
    greeting: ScriptedResponse | None = None
    #: Outcome-keyed responses used when no activity entry matches. These must
    #: only prefer actions that always exist (`next_activity`, `say_only`).
    default: dict[str, ScriptedResponse] = Field(default_factory=dict)
    activities: list[ScriptedActivity] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    def activity_at(self, index: int) -> ScriptedActivity | None:
        if 0 <= index < len(self.activities):
            return self.activities[index]
        return None


def load_script(
    path: str | Path | None = None, *, env: dict[str, str] | None = None
) -> LessonScript:
    """Load the script from a data file. Never from code.

    Resolution order: explicit `path`, then `$BRIGHT_AGENT_SCRIPT`, then the
    packaged demo script. A lesson that wants its own lines ships its own
    file and points the variable at it.
    """
    e: Any = os.environ if env is None else env
    chosen = Path(path) if path is not None else Path(e.get("BRIGHT_AGENT_SCRIPT") or DEFAULT_SCRIPT_PATH)
    data = json.loads(chosen.read_text(encoding="utf-8"))
    script = LessonScript.model_validate(data)
    log.info(
        "[scripted] loaded %s (%s) — %d activities, lesson=%s",
        chosen,
        script.name,
        len(script.activities),
        script.lesson_id,
    )
    return script


# -------------------------------------------------------------- resolution


@dataclass(frozen=True)
class ScriptedChoice:
    """What the script decided, before anything was executed."""

    activity_id: str | None
    outcome: str
    response: ScriptedResponse | None
    action_id: str | None
    detail: str


def outcome_key(ctx: TurnContext) -> str:
    """`greeting` for the pre-lesson turn, otherwise the graded outcome."""
    if ctx.last_interaction is None:
        return GREETING
    return ctx.last_interaction.outcome or "any"


def resolve(script: LessonScript, ctx: TurnContext) -> ScriptedChoice:
    """(activity index, outcome) -> the authored response and a legal action.

    Pure. No I/O, no side effects — so a test can assert the whole decision
    without running a turn.
    """
    key = outcome_key(ctx)
    offered = [a.id for a in ctx.available_actions]

    entry: ScriptedActivity | None = None
    if script.lesson_id and script.lesson_id != ctx.lesson.lesson_id:
        # Wrong lesson: the positional index means nothing here. Fall through
        # to the outcome defaults, which only ever prefer actions that exist
        # in every lesson.
        log.warning(
            "[scripted] script %r is for lesson %s but the turn is %s — using defaults only",
            script.name,
            script.lesson_id,
            ctx.lesson.lesson_id,
        )
    else:
        entry = script.activity_at(ctx.lesson.activity_index)
        if entry and entry.scene and entry.scene != ctx.scene.kind:
            log.warning(
                "[scripted] activity %d is %r in the script but %r on the board",
                ctx.lesson.activity_index,
                entry.scene,
                ctx.scene.kind,
            )

    response: ScriptedResponse | None = None
    source = "none"
    if key == GREETING:
        response, source = script.greeting, "greeting"
    if response is None and entry is not None:
        response = entry.responses.get(key) or entry.responses.get("any")
        source = f"activity[{ctx.lesson.activity_index}]"
    if response is None:
        response = script.default.get(key) or script.default.get("any")
        source = "default"

    action_id: str | None = None
    if response is not None:
        for candidate in response.prefer:
            if candidate in offered:
                action_id = candidate
                break
        if action_id is None and "say_only" in offered and response.say:
            # Nothing authored is legal here. Speaking without moving the
            # board is always safe: core defers the authored branch rather
            # than dropping it (runner._follow), so the lesson still lands.
            action_id = "say_only"

    return ScriptedChoice(
        activity_id=entry.activity_id if entry else None,
        outcome=key,
        response=response,
        action_id=action_id,
        detail=f"{source}/{key}",
    )


def _fill(text: str, ctx: TurnContext) -> str:
    """`{student_name}` / `{memory}` substitution. Unknown braces stay put."""
    if "{" not in text:
        return text
    values = {
        "student_name": ctx.student.name if ctx.student else "everyone",
        "student_id": ctx.student.id if ctx.student else "",
        "memory": ctx.recalled[0].text if ctx.recalled else "",
        "lesson_id": ctx.lesson.lesson_id,
    }
    out = text
    for key, value in values.items():
        out = out.replace("{" + key + "}", str(value))
    return out


# ------------------------------------------------------------------ agent


class ScriptedAgent:
    """`TeacherAgent` backed by a data file. Zero network, zero tokens.

    Same constructor shape as `DirectAgent` — `executor` first, injected by
    classroom-core — so `lambda executor: ScriptedAgent(executor)` is a
    drop-in for the factory core already takes.
    """

    impl_name = "scripted"

    def __init__(
        self,
        executor: ToolExecutor,
        script: LessonScript | str | Path | None = None,
        *,
        say_delay_s: float | None = None,
        env: dict[str, str] | None = None,
    ) -> None:
        self.executor = executor
        if isinstance(script, LessonScript):
            self.script = script
        else:
            self.script = load_script(script, env=env)
        e: Any = os.environ if env is None else env
        override = e.get("BRIGHT_AGENT_SAY_DELAY_S")
        if say_delay_s is not None:
            self.say_delay_s = float(say_delay_s)
        elif override:
            self.say_delay_s = float(override)
        else:
            self.say_delay_s = self.script.say_delay_s
        #: Parity with `DirectAgent`, for the cost/latency logs and /dev/state.
        self.last_usage = TurnUsage()
        self.last_latency_s = 0.0
        #: Turn time with the deliberate speech spacing removed — the number
        #: that answers "how long did the decision take".
        self.last_decision_s = 0.0

    async def aclose(self) -> None:  # parity with DirectAgent; nothing to close
        return None

    async def __aenter__(self) -> "ScriptedAgent":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        return None

    # ---------------------------------------------------------- the turn

    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]:
        """One teaching decision, from the data file. One `Done`, always."""
        started = time.perf_counter()
        slept = 0.0
        emitter = ActEmitter()
        choice = resolve(self.script, ctx)

        try:
            if choice.response is None:
                yield self._done(ctx, "no_action", f"no scripted line for {choice.detail}",
                                 started, slept)
                return

            spoke = False

            # 1. observation — the only write into student state.
            obs = choice.response.observe
            if obs is not None and (ctx.student or ctx.lesson.current_student_id):
                call = ToolCall(
                    call_id="scripted-observe",
                    name=RECORD_OBSERVATION,
                    arguments={
                        "student_id": ctx.student.id if ctx.student else ctx.lesson.current_student_id,
                        "skill": obs.skill,
                        "result": obs.result or _OBSERVATION_RESULT.get(choice.outcome, "near"),
                        "evidence": _fill(obs.evidence or choice.detail, ctx),
                    },
                )
                async for ev in self._invoke(ctx, call, emitter):
                    yield ev
                    if isinstance(ev, Done):
                        return

            text = _fill(choice.response.say, ctx).strip()
            # `say_only` carries its own text (agent_bridge._apply publishes it).
            # Saying it twice would speak the line twice.
            say_via_tool = bool(text) and choice.action_id != "say_only"

            # 2. speak.
            if say_via_tool:
                delay = choice.response.say_delay_s
                delay = self.say_delay_s if delay is None else delay
                if delay > 0:
                    await asyncio.sleep(delay)
                    slept += delay
                args: dict[str, Any] = {"text": text}
                if choice.response.style:
                    args["style"] = choice.response.style
                call = ToolCall(call_id="scripted-say", name=SAY, arguments=args)
                async for ev in self._invoke(ctx, call, emitter):
                    yield ev
                    if isinstance(ev, Done):
                        return
                spoke = True

            # 3. act — exactly one, and only one core offered.
            if choice.action_id is not None:
                params: dict[str, Any] = {}
                if choice.action_id == "say_only":
                    params["text"] = text
                call = ToolCall(
                    call_id="scripted-choose",
                    name=CHOOSE_NEXT,
                    arguments={
                        "state_version": ctx.state_version,
                        "action_id": choice.action_id,
                        **({"params": params} if params else {}),
                    },
                )
                async for ev in self._invoke(ctx, call, emitter):
                    yield ev
                    if isinstance(ev, Done):
                        return
                act = emitter.on_done()
                if act:
                    yield act
                yield self._done(ctx, "complete", choice.detail, started, slept,
                                 chose=choice.action_id)
                return

            if spoke:
                act = emitter.on_done()
                if act:
                    yield act
                yield self._done(ctx, "complete", f"{choice.detail} (spoke only)", started, slept)
                return

            yield self._done(
                ctx,
                "no_action",
                f"{choice.detail}: none of {choice.response.prefer} was offered",
                started,
                slept,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 - never let a raise reach core
            log.exception("ScriptedAgent.turn crashed")
            yield self._done(ctx, "error", f"agent crashed: {exc!r}", started, slept)

    # ------------------------------------------------------------ helpers

    async def _invoke(
        self, ctx: TurnContext, call: ToolCall, emitter: ActEmitter
    ) -> AsyncIterator[AgentEvent]:
        """Validate, execute once, report. Any failure ends the turn.

        Identical in shape to `DirectAgent`'s inner loop: the proposal is
        checked against this turn's context *before* the executor is reached,
        and a rejection is terminal — no repair, no second attempt.
        """
        yield call
        act = emitter.on_tool_call(call.name)
        if act:
            yield act

        rejection: Rejection | None = validate_call(ctx, call.name, call.arguments)
        if rejection is not None:
            yield ToolResult(call_id=call.call_id, name=call.name, ok=False, error=str(rejection))
            yield self._done(ctx, "error", str(rejection), time.perf_counter(), 0.0)
            return

        try:
            result = await self.executor(call.name, call.arguments)
        except Exception as exc:  # noqa: BLE001 - operational, not a bug
            log.warning("tool execution failed tool=%s err=%r", call.name, exc)
            yield ToolResult(call_id=call.call_id, name=call.name, ok=False, error=repr(exc))
            yield self._done(ctx, "error", f"{call.name} failed: {exc!r}", time.perf_counter(), 0.0)
            return

        yield ToolResult(call_id=call.call_id, name=call.name, ok=True, result=result)
        act = emitter.on_tool_result(call.name, result)
        if act:
            yield act

    def _done(
        self,
        ctx: TurnContext,
        reason: str,
        detail: str | None,
        started: float,
        slept: float,
        *,
        chose: str | None = None,
    ) -> Done:
        self.last_latency_s = time.perf_counter() - started
        self.last_decision_s = max(0.0, self.last_latency_s - slept)
        # Zero tokens, zero rounds. Nothing was inferred; a table was read.
        self.last_usage = TurnUsage()
        log.info(
            "[scripted] turn done reason=%s lesson=%s activity=%s chose=%s "
            "decision=%.4fs total=%.2fs detail=%s",
            reason,
            ctx.lesson.lesson_id,
            ctx.lesson.activity_index,
            chose,
            self.last_decision_s,
            self.last_latency_s,
            detail,
        )
        return Done(reason=reason, detail=detail, usage=self.last_usage)  # type: ignore[arg-type]

    # -------------------------------------------------- non-streaming half

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """The other half of the seam, answered honestly and instantly.

        classroom-core uses `agent.complete()` for two things:

        * `make_probe` — the health probe that decides FULL/DEGRADED/OFFLINE.
          **An agent without `complete` probes as `None`, which pins the mode
          to OFFLINE, and `AutoTurn` refuses to run outside FULL.** A scripted
          agent that omitted this method would therefore never be given a
          single turn — it would be wired, and silent. So it answers, and the
          probe measures what it is really measuring: the latency of the agent
          that is actually wired. Here that is microseconds, and truthfully so.
        * `SessionSummarizer` — which needs a JSON summary. There is no model
          to write one, so this returns prose that is deliberately not JSON;
          core logs it and falls back to `deterministic_summary`, which is the
          correct behaviour and the honest one.
        """
        return {
            "id": "scripted",
            "object": "chat.completion",
            "model": f"bright-scripted/{self.script.name}",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": (
                            "[scripted agent] No language model is running. "
                            "Use the deterministic summary."
                        ),
                    },
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        }


__all__ = [
    "GREETING",
    "OUTCOME_KEYS",
    "DEFAULT_SCRIPT_PATH",
    "ScriptedObservation",
    "ScriptedResponse",
    "ScriptedActivity",
    "LessonScript",
    "ScriptedChoice",
    "load_script",
    "outcome_key",
    "resolve",
    "ScriptedAgent",
]
