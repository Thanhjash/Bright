"""The seam where the teacher agent meets the classroom.

This is the piece that turns a lesson *player* into a lesson *teacher*, and it
is deliberately thin. Core stays the source of truth; the agent only ever
proposes, and a proposal core does not like is discarded in favour of the
authored default. Nothing here can make the lesson stop.

Five responsibilities:

1. **Compute `available_actions`** — what is legal *right now*, derived from the
   lesson run and current state. This is the whole reason a 4.5B model can drive
   this system: it answers a short multiple choice, not an open-ended "compose a
   plan from 26 primitives". Core owns the option set; the model owns the pick.

2. **Build the `TurnContext`** the agent reasons over.

3. **Execute** whatever the agent chose, after validating it.

4. **`AutoTurn`** — the gate the runner calls after it has graded an
   interaction. Bounded, mode-gated, serialised, and it fails *into* the
   authored branch.

5. **`build_agent_seam`** — the background-job half: a real
   `summarize_session` and a real health probe, built over the same agent.

Design rules, all load-bearing:

* **Single attempt.** A rejected or failed proposal falls straight through to
  the authored default. We never retry in front of a class (docs/3-design/architecture.md §3).
* **`state_version` gating.** A decision made against state that has since moved
  is discarded, not applied to a board that changed underneath it.
* **The agent cannot invent actions.** `action_id` must be one core just offered.
* **Everything is optional.** Remove the agent and the lesson still runs (NS-1).
* **The agent is never in the reflex path.** Grading, the reveal frame and the
  immediate feedback all land first, at reflex latency. The agent turn runs
  after, and may then change what comes *next* (NS-2).
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import secrets
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Collection, Iterable, Mapping

from bright_contracts import (
    Activity,
    AvailableAction,
    LastInteraction,
    RecalledMemory,
    StudentBrief,
    TurnContext,
)

from scheduler import AgentSeam

log = logging.getLogger("core.agent")

#: How many times one activity may be entered before `repeat_activity` stops
#: being offered. 3 gives a child two extra chances at the same question --
#: generous by classroom standards -- while bounding the loop.
MAX_ACTIVITY_ENTRIES = int(os.environ.get("AGENT_MAX_ACTIVITY_ENTRIES", "3"))

#: How many memories the greeting turn is given. Small on purpose: the model
#: also has `classroom_recall` and can ask for more if it wants more.
RECALL_K = 3

# services/agent lives beside us and is not installed as a package.
_AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
if _AGENT_DIR.exists() and str(_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(_AGENT_DIR))


# ─────────────────────────────── available actions ──────────────────────────


def available_actions(
    core: Any,
    *,
    only: Collection[str] | None = None,
    relabel: Mapping[str, str] | None = None,
) -> list[AvailableAction]:
    """What the agent may choose from, right now.

    Derived from the lesson run, never from the model's imagination. An empty
    list is a valid answer and means "the agent has nothing to decide" — the
    caller should then not spend a turn at all.

    ``only`` narrows the set for a turn that is deliberately not a routing
    decision — the greeting, which may speak but must not move the lesson.
    It is applied here, in the *one* place that computes legality, so the
    prompt's option list and the executor's admission check can never
    disagree. (An earlier sketch filtered only the prompt; the executor then
    happily accepted an action the model was never offered.)

    ``relabel`` rewrites the *description* of an action without touching its
    id. This is the lever `bright_agent.prompt` asks callers to reach for —
    "if you need the model to know something new, ask whether an
    `available_actions` label can carry it instead" — and it is the only one
    available from this side, since the system prompt lives in
    `services/agent` and must stay byte-identical across turns to keep the
    provider's prefix cache warm. Labels cannot affect legality, so there is
    no way for a relabel to widen what the executor will admit.
    """
    runner = getattr(core, "runner", None)
    if runner is None or not runner.activities:
        return []

    current = runner.current
    actions: list[AvailableAction] = []

    if current is not None:
        # Authored branches are first-class options: the agent chooses among
        # paths the author already sanctioned.
        #
        # Deduplicated by target. Several outcomes routinely share a
        # destination — in the sample lesson `wrong`, `silence` and `timeout`
        # all go to `help_meow` — and offering the same id three times both
        # wastes prompt budget and makes the choice look more considered than
        # it is. The outcomes that lead there are merged into one label.
        by_target: dict[str, list[str]] = {}
        for branch in current.branches or []:
            if any(a.id == branch.goto for a in runner.activities):
                by_target.setdefault(branch.goto, []).append(branch.on)

        for goto, reasons in by_target.items():
            target = next(a for a in runner.activities if a.id == goto)
            actions.append(
                AvailableAction(
                    id=f"goto:{goto}",
                    label=f"go to '{goto}' ({target.scene}) — authored for {'/'.join(reasons)}",
                )
            )

        # Offer `repeat_activity` only while repeating is still reasonable.
        #
        # Uncapped, this loops: repeat → timer expires → gate fires → repeat,
        # observed 6/6 cycles with the index never moving, ~1500 prompt tokens
        # burnt each time while a class sat and waited. The facilitator's `skip`
        # was the only escape, and a teacher may not realise she needs it.
        #
        # Withholding the option beats rejecting it afterwards: the model never
        # sees a choice it should not make, and no turn is wasted being refused.
        entries = getattr(runner, "entry_counts", {}).get(current.id, 1)
        if entries < MAX_ACTIVITY_ENTRIES:
            actions.append(
                AvailableAction(
                    id="repeat_activity",
                    label=(
                        f"repeat '{current.id}' — say it again, more slowly"
                        f" (attempt {entries + 1} of {MAX_ACTIVITY_ENTRIES})"
                    ),
                )
            )

    if runner.index + 1 < len(runner.activities):
        nxt = runner.activities[runner.index + 1]
        actions.append(
            AvailableAction(
                id="next_activity",
                label=f"move on to '{nxt.id}' ({nxt.scene})",
            )
        )

    # Always available: speak without moving the board. This is the agent's
    # release valve — praise, a recast, a nudge — and it is what stops it from
    # advancing the lesson just to have something to do.
    actions.append(
        AvailableAction(
            id="say_only",
            label="say something and stay where we are",
            params=["text"],
        )
    )

    if only is not None:
        allowed = set(only)
        actions = [a for a in actions if a.id in allowed]

    if relabel:
        actions = [
            a.model_copy(update={"label": relabel[a.id]}) if a.id in relabel else a
            for a in actions
        ]

    return actions


# ────────────────────────────────── context ─────────────────────────────────


def default_recall_query(core: Any) -> str:
    """What to ask memory when nobody asked anything specific.

    The lesson's own vocabulary. `focus` entries are the same strings the
    runner writes into `observations.skill` (``animal_vocab``), so they match
    past observations exactly; the title supplies the plain-English words that
    match past *summaries*, which are model prose and never contain a
    snake_case skill key.
    """
    lesson = getattr(core, "lesson", None)
    if lesson is None:
        return ""
    parts: list[str] = [*(lesson.focus or []), *(lesson.review or []), lesson.title or ""]
    return " ".join(p for p in parts if p)[:200]


def _as_memories(hits: Iterable[Any]) -> list[RecalledMemory]:
    """Coerce whatever the store returned into contract objects.

    ``Database.recall`` already returns ``RecalledMemory``. `build_turn_context`
    used to call ``h.get("text")`` on those objects, which raised
    ``AttributeError`` on every single call — caught by its own
    never-fail-a-turn-on-memory handler, logged as "recall failed", and
    `recalled` left as ``None``. Recall had therefore never once reached a
    prompt. Keep the coercion tolerant so a store that hands back plain dicts
    still works.
    """
    out: list[RecalledMemory] = []
    for hit in hits:
        if isinstance(hit, RecalledMemory):
            out.append(hit)
        elif isinstance(hit, dict):
            out.append(RecalledMemory(text=str(hit.get("text", "")), when=str(hit.get("when", ""))))
        else:
            out.append(
                RecalledMemory(
                    text=str(getattr(hit, "text", "")), when=str(getattr(hit, "when", ""))
                )
            )
    return [m for m in out if m.text]


def _recall(core: Any, query: str, k: int, student_id: str | None) -> list[Any]:
    """The top ``k`` memories for this turn: one durable note, then episodes.

    Two rules, both learned from watching a real recall come back:

    * **This child first.** "I remember *you*" is the point; a hit about
      another student is worse than no hit. A child with no history of their
      own still sees the class's, rather than nothing.
    * **Reserve a slot for the session summary.** bm25 rewards short
      documents, so three raw observation rows -- ``{'optionId': 'six'} ->
      wrong`` -- crowd out the paragraph a teacher actually wrote about them,
      and the whole `summarize_session` job becomes decorative. Measured on
      the first live two-session run: the summary ranked 4th of 3.
    """

    if not student_id:
        return []

    def ask(**kw: Any) -> list[Any]:
        # Learner memory is never widened to the class or another child.  No
        # memory is safer than a plausible sentence about the wrong learner.
        return list(core.db.recall(query, student_id=student_id, **kw))

    hits: list[Any] = []
    if k > 1:
        try:
            hits = ask(k=1, kind="summary")
        except TypeError:  # a store without tiers; episodes only
            hits = []
    seen = {getattr(h, "text", None) for h in hits}
    hits += [h for h in ask(k=k) if getattr(h, "text", None) not in seen]
    return hits[:k]


def build_turn_context(
    core: Any,
    *,
    last_interaction: LastInteraction | None = None,
    student_id: str | None = None,
    recall_query: str | None = None,
    only: Collection[str] | None = None,
    relabel: Mapping[str, str] | None = None,
    recall_k: int = RECALL_K,
    context_policy: str = "local-trusted",
) -> TurnContext:
    """Assemble everything the agent is allowed to see."""
    student: StudentBrief | None = None
    trusted = context_policy == "local-trusted"
    if student_id:
        try:
            row = core.db.get_student(student_id)
            if row:
                student = StudentBrief(
                    id=student_id if trusted else "current_student",
                    name=(row.get("name") or student_id) if trusted else "the current student",
                    skills=row.get("skills") or {},
                )
        except Exception as exc:  # noqa: BLE001 — never fail a turn on memory
            log.warning("student lookup failed for %s: %s", student_id, exc)

    recalled: list[RecalledMemory] | None = None
    if recall_query and trusted:
        try:
            recalled = _as_memories(_recall(core, recall_query, recall_k, student_id)) or None
        except Exception as exc:  # noqa: BLE001
            log.warning("recall failed: %s", exc)

    scene = core.store.scene
    lesson = core.store.lesson
    if not trusted:
        # The overlay subtitle is a display surface, not model context.  During
        # speech activities it may contain a child's verbatim transcript; a
        # hosted provider receives only the authoritative visual scene and the
        # Core-graded LastInteraction above.
        scene = scene.model_copy(deep=True)
        if scene.overlay is not None:
            scene.overlay.subtitle = None
        # ``LessonPosition`` is also part of every hosted request and MCP state
        # read. Pseudonymising StudentBrief is insufficient if the stable
        # learner key remains here.
        lesson = lesson.model_copy(deep=True)
        lesson.current_student_id = None

    return TurnContext(
        stateVersion=core.store.state_version,
        lesson=lesson,
        scene=scene,
        student=student,
        lastInteraction=last_interaction,
        availableActions=available_actions(core, only=only, relabel=relabel),
        recalled=recalled,
    )


# ───────────────────────────────── execution ────────────────────────────────


@dataclass(frozen=True)
class TurnScope:
    """The turn-shaped arguments the executor must reproduce mid-turn.

    `classroom_get_state` rebuilds a `TurnContext`; without this it rebuilt a
    *different* one — no student, no memories, unrestricted actions — so a
    model that re-read state silently lost the child it was talking to.
    """

    student_id: str | None = None
    recall_query: str | None = None
    only: tuple[str, ...] | None = None
    relabel: tuple[tuple[str, str], ...] | None = None
    last_interaction: LastInteraction | None = None
    context_policy: str = "local-trusted"
    text_stream_voice: bool = False

    @property
    def labels(self) -> dict[str, str] | None:
        return dict(self.relabel) if self.relabel else None


@dataclass
class TurnResult:
    """What happened. Every field is for humans and for later evals."""

    chose: str | None = None
    said: list[str] = field(default_factory=list)
    rejected: str | None = None
    applied: bool = False
    observations: int = 0
    elapsed_ms: int = 0
    usage: dict[str, Any] | None = None
    operational_error: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "chose": self.chose,
            "said": self.said,
            "rejected": self.rejected,
            "applied": self.applied,
            "observations": self.observations,
            "elapsedMs": self.elapsed_ms,
            "usage": self.usage,
            "operationalError": self.operational_error,
        }


def make_tool_executor(
    core: Any,
    result: Any,
    scope: Callable[[], TurnScope] | None = None,
) -> Callable[..., Awaitable[Any]]:
    """Map the agent's five tools onto core operations.

    Nothing here trusts its input. `classroom_choose_next` in particular is
    validated against the option set core itself just produced.
    """

    def _scope() -> TurnScope:
        return scope() if scope is not None else TurnScope()

    async def execute(name: str, arguments: dict[str, Any]) -> Any:
        if name == "classroom_get_state":
            s = _scope()
            return build_turn_context(
                core,
                student_id=s.student_id,
                recall_query=s.recall_query,
                only=s.only,
                relabel=s.labels,
                context_policy=s.context_policy,
            ).model_dump(by_alias=True, mode="json")

        if name == "classroom_say":
            text = str(arguments.get("text") or "").strip()
            if not text:
                return {"ok": False, "reason": "empty text"}
            result.said.append(text)
            core.publish_speech(
                text,
                source="agent",
                behavior="queue",
                activity_id=getattr(getattr(core, "runner", None), "current", None).id
                if getattr(getattr(core, "runner", None), "current", None)
                else None,
                activity_generation=getattr(getattr(core, "runner", None), "_generation", None),
            )
            # Deliberately does NOT touch the store.
            #
            # Setting the subtitle here would bump `state_version`, and the
            # agent's own `choose_next` — sent with the version it was handed at
            # the start of the turn — would then be rejected as stale. Speaking
            # and then acting is the normal pattern, so that made the two tools
            # mutually exclusive. Observed on the very first live turn: the model
            # produced a good scaffolded hint and its action was thrown away.
            #
            # It is also redundant: PROTOCOL §9.6 already has `speech.say` fill
            # the subtitle when the overlay omits it.
            return {"ok": True}

        if name == "classroom_record_observation":
            try:
                s = _scope()
                supplied = str(arguments.get("student_id") or "")
                allowed = {s.student_id, "current_student"}
                if not s.student_id or supplied not in allowed:
                    return {"ok": False, "reason": "student scope mismatch"}
                last = s.last_interaction
                evidence = (
                    f"{last.kind} -> {last.outcome}"
                    if last is not None
                    else "agent observation (no interaction detail retained)"
                )
                core.db.record_observation(
                    # The model is required to name the student, but a turn
                    # that knows exactly one child should not lose the row to a
                    # blank argument.
                    student_id=s.student_id,
                    skill=str(arguments.get("skill") or "unspecified"),
                    result=str(arguments.get("result") or "unknown"),
                    # Never persist arbitrary model prose: it may repeat a raw
                    # transcript or invent learner facts. Core stores only the
                    # graded, structured interaction it supplied this turn.
                    evidence=evidence,
                    session_id=getattr(core, "session_id", None),
                )
                result.observations += 1
                return {"ok": True}
            except Exception as exc:  # noqa: BLE001 — memory must never stop a class
                log.warning("record_observation failed: %s", exc)
                return {"ok": False, "reason": str(exc)}

        if name == "classroom_recall":
            try:
                s = _scope()
                if s.context_policy != "local-trusted":
                    # Hosted classroom providers receive no durable learner
                    # notes, including through the MCP path. The initial
                    # TurnContext policy must not be bypassable by a tool call.
                    return {"ok": False, "reason": "recall unavailable for this context policy"}
                if not s.student_id:
                    return {"ok": False, "reason": "learner scope required"}
                hits = core.db.recall(
                    str(arguments.get("query") or ""),
                    k=int(arguments.get("k") or RECALL_K),
                    student_id=s.student_id,
                )
                return {
                    "ok": True,
                    "hits": [h.model_dump(by_alias=True) for h in _as_memories(hits)],
                }
            except Exception as exc:  # noqa: BLE001
                return {"ok": False, "reason": str(exc)}

        if name == "classroom_choose_next":
            s = _scope()
            legal = {a.id for a in available_actions(core, only=s.only)}
            action_id = str(arguments.get("action_id") or "")
            sent_version = arguments.get("state_version")

            if action_id not in legal:
                result.rejected = f"illegal action_id {action_id!r}; legal: {sorted(legal)}"
                log.warning("REJECT %s", result.rejected)
                return {"ok": False, "reason": "illegal action_id"}

            if sent_version is not None and int(sent_version) != core.store.state_version:
                result.rejected = (
                    f"stale state_version {sent_version} != {core.store.state_version}"
                )
                log.warning("REJECT %s", result.rejected)
                return {"ok": False, "reason": "stale state_version"}

            result.chose = action_id
            await _apply(
                core,
                action_id,
                arguments.get("params") or {},
                suppress_speech=s.text_stream_voice,
            )
            result.applied = True
            return {"ok": True, "applied": action_id}

        return {"ok": False, "reason": f"unknown tool {name!r}"}

    return execute


async def _apply(
    core: Any,
    action_id: str,
    params: dict[str, Any],
    *,
    suppress_speech: bool = False,
) -> None:
    runner = core.runner
    if action_id.startswith("goto:"):
        target = action_id.split(":", 1)[1]
        idx = runner.index_of(target)
        if idx >= 0:
            await runner.start(idx)
        return
    if action_id == "next_activity":
        await runner.start(runner.index + 1)
        return
    if action_id == "repeat_activity":
        await runner.start(runner.index)
        return
    if action_id == "say_only":
        text = str(params.get("text") or "").strip()
        if text and not suppress_speech:
            # Same reasoning as `classroom_say` above: no store write. Setting
            # the overlay here bumped `state_version` without publishing a
            # `scene.update`, so every connected client silently fell a version
            # behind for a line PROTOCOL §9.6 already renders from `speech.say`.
            core.publish_speech(
                text,
                source="agent",
                behavior="queue",
                activity_id=getattr(runner.current, "id", None),
                activity_generation=getattr(runner, "_generation", None),
            )
        return


# ────────────────────────────────── driver ──────────────────────────────────


class AgentDriver:
    """Gives the agent one bounded turn, and absorbs every way it can fail.

    `TeacherAgent.turn(ctx)` takes only a context — the executor is injected
    once, at construction. So the executor here is stable and reads whichever
    `TurnResult` is currently in flight. Turns are serialised (one classroom,
    one teacher, one thing happening at a time), which is what makes that safe.

    Serialisation is a **skip, not a queue**: a turn that arrives while another
    is in flight is dropped and the caller falls back to the authored branch. A
    queued turn would be answering a question the class has already moved past.
    """

    def __init__(self, core: Any, agent_factory: Callable[[Any], Any]) -> None:
        self.core = core
        self._result = TurnResult()
        self._scope = TurnScope()
        self._busy = False
        self.skipped = 0
        # The executor closes over `self`, so it always sees the live result
        # and the live scope.
        self._executor = make_tool_executor(core, _ResultProxy(self), lambda: self._scope)
        self.agent = agent_factory(self._executor)
        self._speech_turn_id: str | None = None
        self._speech_open = False
        self._active_task: asyncio.Task[Any] | None = None
        self._registry_turn_id: str | None = None
        self._turn_generation: tuple[str | None, int | None] | None = None
        self._accepted_own_transition = False

    def _open_speech(self) -> str:
        if self._speech_turn_id is not None:
            return self._speech_turn_id
        speech_turn_id, conversation_turn_id = self.core.conversations.next_speech_ids(
            prefix="agent"
        )
        runner = getattr(self.core, "runner", None)
        current = getattr(runner, "current", None)
        payload = {
            "speechTurnId": speech_turn_id,
            "behavior": "queue",
            "source": "agent",
            "conversationTurnId": conversation_turn_id,
            "activityId": getattr(current, "id", None),
            "activityGeneration": getattr(runner, "_generation", None),
        }
        self.core.conversations.register_speech(
            speech_turn_id,
            activity_id=payload["activityId"],
            activity_generation=payload["activityGeneration"],
        )
        self.core.bus.publish(
            "speech.turn.started", {key: value for key, value in payload.items() if value is not None}
        )
        self._speech_turn_id = speech_turn_id
        self._speech_open = True
        return speech_turn_id

    def _speech_delta(self, text: str) -> None:
        if not text:
            return
        speech_turn_id = self._open_speech()
        self.core.bus.publish(
            "speech.text.delta", {"speechTurnId": speech_turn_id, "delta": text}
        )

    def _close_speech(self, status: str, reason: str | None = None) -> None:
        if not self._speech_open or self._speech_turn_id is None:
            return
        payload: dict[str, Any] = {
            "speechTurnId": self._speech_turn_id,
            "status": status,
        }
        if reason:
            payload["reason"] = reason
        self.core.bus.publish("speech.turn.ended", payload)
        if status == "cancelled":
            self.core.cancel_speech(self._speech_turn_id, reason or "turn_cancelled")
        self._speech_open = False

    @property
    def busy(self) -> bool:
        return self._busy

    def cancel_current(self, reason: str = "superseded") -> bool:
        """Close the live provider stream and its exact utterance immediately."""
        task = self._active_task
        if task is None or task.done():
            return False
        # An MCP choose_next is applied on this task for direct/scripted agents;
        # cancelling it would turn the agent's own legal transition into a
        # takeover.  External control/interaction tasks still cancel promptly.
        if task is asyncio.current_task():
            return False
        self._close_speech("cancelled", reason)
        task.cancel()
        return True

    def cancel_speech_turn(self, speech_turn_id: str, reason: str = "superseded") -> bool:
        """Cancel only the provider turn that owns ``speech_turn_id``."""
        if speech_turn_id != self._speech_turn_id:
            return False
        if self._registry_turn_id is not None:
            self.core.turn_registry.retire(self._registry_turn_id)
            self._registry_turn_id = None
        return self.cancel_current(reason)

    def _generation_is_current(self) -> bool:
        if self._turn_generation is None:
            return True
        runner = getattr(self.core, "runner", None)
        return self._turn_generation == (
            getattr(getattr(runner, "current", None), "id", None),
            getattr(runner, "_generation", None),
        )

    async def take_turn(
        self,
        *,
        last_interaction: LastInteraction | None = None,
        student_id: str | None = None,
        recall_query: str | None = None,
        only: Collection[str] | None = None,
        relabel: Mapping[str, str] | None = None,
    ) -> TurnResult:
        if self._busy:
            self.skipped += 1
            log.info("[agent] turn skipped: one already in flight")
            return TurnResult(rejected="turn already in flight")

        result = TurnResult()
        self._busy = True
        self._active_task = asyncio.current_task()
        self._result = result
        self._scope = TurnScope(
            student_id=student_id,
            recall_query=recall_query,
            only=tuple(only) if only is not None else None,
            relabel=tuple(relabel.items()) if relabel else None,
            last_interaction=last_interaction,
            context_policy=getattr(self.core.settings, "agent_context_policy", "hosted-minimal"),
            text_stream_voice=bool(getattr(self.agent, "streams_text_as_voice", False)),
        )
        started = time.perf_counter()
        turn_id: str | None = None
        self._speech_turn_id = None
        self._speech_open = False
        runner = getattr(self.core, "runner", None)
        self._turn_generation = (
            getattr(getattr(runner, "current", None), "id", None),
            getattr(runner, "_generation", None),
        )
        self._accepted_own_transition = False
        terminal_status = "error"
        terminal_reason: str | None = "agent turn ended unexpectedly"

        try:
            ctx = build_turn_context(
                self.core,
                last_interaction=last_interaction,
                student_id=student_id,
                recall_query=recall_query,
                only=only,
                relabel=relabel,
                context_policy=self._scope.context_policy,
            )
            if not ctx.available_actions:
                result.rejected = "nothing to decide"
                return result

            prepare_turn = getattr(self.agent, "prepare_turn", None)
            if callable(prepare_turn):
                turn_id = "bright-" + secrets.token_urlsafe(24)
                self.core.turn_registry.register(
                    turn_id,
                    self._executor,
                    student_id=student_id,
                    ttl_s=max(
                        float(getattr(self.core.settings, "agent_turn_timeout_s", 6.0)),
                        float(getattr(self.core.settings, "agent_greeting_timeout_s", 12.0)),
                    )
                    + 2.0,
                )
                self._registry_turn_id = turn_id
                prepare_turn(turn_id)

            try:
                spoken: list[str] = []
                async for event in self.agent.turn(ctx):
                    if not self._generation_is_current():
                        result.rejected = "activity generation changed during agent turn"
                        terminal_status = "cancelled"
                        terminal_reason = "activity_generation_changed"
                        break
                    kind = getattr(event, "type", None)
                    if kind == "text_delta" and self._scope.text_stream_voice:
                        delta = str(getattr(event, "text", ""))
                        spoken.append(delta)
                        self._speech_delta(delta)
                    elif kind == "done":
                        usage = getattr(event, "usage", None)
                        result.usage = usage.model_dump() if usage else None
                        if getattr(event, "reason", None) == "error":
                            result.rejected = result.rejected or "agent reported error"
                            result.operational_error = True
                            terminal_status = "error"
                            terminal_reason = getattr(event, "detail", None) or "agent reported error"
                        else:
                            terminal_status = "completed"
                            terminal_reason = None
                if spoken:
                    # Keep one human-readable utterance in diagnostics while
                    # publishing every provider delta exactly once on the bus.
                    result.said.append("".join(spoken))
            except asyncio.CancelledError:
                terminal_status = "cancelled"
                terminal_reason = "agent timeout or superseded turn"
                raise
            except Exception as exc:  # noqa: BLE001 — an agent failure is never fatal
                log.warning("agent turn failed: %s", exc)
                result.rejected = f"agent error: {exc}"
                result.operational_error = True
                terminal_status = "error"
                terminal_reason = str(exc)

            result.elapsed_ms = int((time.perf_counter() - started) * 1000)
            return result
        finally:
            self._close_speech(terminal_status, terminal_reason)
            if turn_id is not None:
                self.core.turn_registry.retire(turn_id)
            self._registry_turn_id = None
            self._active_task = None
            self._turn_generation = None
            self._accepted_own_transition = False
            self._busy = False


class _ResultProxy:
    """Forwards attribute access to the driver's in-flight TurnResult.

    Lets a single long-lived executor record into a per-turn result without
    rebuilding the agent every turn.
    """

    def __init__(self, driver: AgentDriver) -> None:
        object.__setattr__(self, "_driver", driver)

    def __getattr__(self, item: str) -> Any:
        return getattr(object.__getattribute__(self, "_driver")._result, item)

    def __setattr__(self, item: str, value: Any) -> None:
        setattr(object.__getattribute__(self, "_driver")._result, item, value)


# ──────────────────────────────── the auto turn ─────────────────────────────


def _describe(activity: Activity, payload: dict[str, Any]) -> str:
    # The payload may contain a child's raw transcript.  The agent needs the
    # Core-graded outcome, not a durable/verbatim copy of what was said.
    kind = activity.expect.kind if activity.expect else "none"
    detail = f"activity={activity.id}; response_kind={kind}"
    # Board identifiers are authored, bounded semantic data and useful for
    # adaptation. Only free-form speech text is forbidden from model context.
    if kind == "choice" and payload.get("optionId"):
        detail += f"; option_id={payload['optionId']}"
    elif kind == "point" and payload.get("targetId"):
        detail += f"; target_id={payload['targetId']}"
    elif kind == "drag":
        detail += f"; from_id={payload.get('fromId', '')}; to_id={payload.get('toId', '')}"
    return detail


class AutoTurn:
    """The runner's decision gate: one bounded agent turn per graded outcome.

    Contract with :class:`runner.LessonRunner`:

    * called **after** grading, the reveal frame and the immediate feedback —
      never before (NS-2: nothing a child does waits on a model).
    * returns the applied ``action_id``, or ``None`` for "I did not act,
      take the authored branch".
    * never raises, never blocks past ``timeout_s``.

    Every way out that is not "the agent chose something legal in time" ends
    in the authored branch. Slow, broken, illegal, offline, busy — all the
    same answer, because that is the answer the class can survive.
    """

    def __init__(self, core: Any, *, timeout_s: float = 6.0) -> None:
        self.core = core
        self.timeout_s = timeout_s
        # Counters, for /dev/state and for the eval set.
        self.turns = 0
        self.applied = 0
        self.timeouts = 0
        self.errors = 0
        self.skipped_mode = 0
        self.last_elapsed_ms: int | None = None
        self.total_elapsed_ms = 0

    def stats(self) -> dict[str, Any]:
        return {
            "turns": self.turns,
            "applied": self.applied,
            "timeouts": self.timeouts,
            "errors": self.errors,
            "skippedNotFull": self.skipped_mode,
            "timeoutS": self.timeout_s,
            "lastElapsedMs": self.last_elapsed_ms,
            "meanElapsedMs": int(self.total_elapsed_ms / self.turns) if self.turns else None,
        }

    async def __call__(
        self, activity: Activity, outcome: str, payload: dict[str, Any]
    ) -> str | None:
        driver = getattr(self.core, "agent_driver", None)
        if driver is None:
            return None
        if self.core.store.mode != "FULL":
            # DEGRADED/OFFLINE mean "core plays lesson_run" (PROTOCOL §7).
            self.skipped_mode += 1
            return None

        kind = activity.expect.kind if activity.expect else "none"
        last = LastInteraction(
            kind=kind, detail=_describe(activity, payload), outcome=outcome  # type: ignore[arg-type]
        )

        self.turns += 1
        started = time.perf_counter()
        try:
            result = await asyncio.wait_for(
                driver.take_turn(
                    last_interaction=last, student_id=getattr(self.core, "student_id", None)
                ),
                timeout=self.timeout_s,
            )
        except asyncio.TimeoutError:
            self.timeouts += 1
            self._record_elapsed(started)
            log.info(
                "[agent] turn exceeded %.1fs on %s/%s — taking the authored branch",
                self.timeout_s,
                activity.id,
                outcome,
            )
            # Alive but too slow to teach with: DEGRADED, once it happens twice.
            self.report_health(
                False, kind="timeout", detail=f"no answer in {self.timeout_s:.0f}s"
            )
            return None
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001 — the gate cannot be a failure mode
            self.errors += 1
            self._record_elapsed(started)
            log.warning("[agent] turn raised (%r) — taking the authored branch", exc)
            self.report_health(
                False, kind="unreachable", detail=f"{type(exc).__name__}: {exc}"[:80]
            )
            return None

        elapsed_ms = self._record_elapsed(started)
        # A protocol/provider Done(error) is an operational failure even though
        # the local HTTP stream answered.  Illegal pedagogy remains healthy;
        # an unreachable Hermes sidecar must demote without waiting for probe.
        if result.operational_error:
            self.report_health(
                False,
                kind="unreachable",
                detail=(result.rejected or "agent operational error")[:80],
            )
        else:
            self.report_health(True, latency_s=elapsed_ms / 1000.0)
        if result.applied and result.chose:
            self.applied += 1
            log.info(
                "[agent] %s/%s -> %s in %dms (said %d line(s), %d observation(s))",
                activity.id,
                outcome,
                result.chose,
                elapsed_ms,
                len(result.said),
                result.observations,
            )
            return result.chose

        self.errors += 1 if result.rejected else 0
        log.info(
            "[agent] %s/%s -> no decision in %dms (%s) — taking the authored branch",
            activity.id,
            outcome,
            elapsed_ms,
            result.rejected or "agent chose nothing",
        )
        return None

    def _record_elapsed(self, started: float) -> int:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        self.last_elapsed_ms = elapsed_ms
        self.total_elapsed_ms += elapsed_ms
        return elapsed_ms

    def report_health(self, ok: bool, **detail: Any) -> None:
        """Tell the mode controller what this turn actually did.

        The 60-second probe is the slow signal; this is the fast one. Without
        it a cloud outage costs one full ``timeout_s`` hole per answered
        question until the probe next runs, which is the difference between a
        class noticing once and a class noticing ten times.

        Guarded rather than asserted: the gate is not allowed to become a new
        failure mode just because a test built a core without a controller.
        """
        modes = getattr(self.core, "modes", None)
        note = getattr(modes, "note_agent_turn", None)
        if note is None:
            return
        try:
            note(ok, **detail)
        except Exception:  # noqa: BLE001 — health accounting never breaks a class
            log.exception("could not record agent turn health")


# ─────────────────────────────── background jobs ────────────────────────────

SUMMARY_SYSTEM = """\
You are the teacher of a beginner English class in Vietnam, writing your notes \
after one session with one student.

Reply with ONE JSON object and nothing else:
{"summary": "...", "weakPoints": ["..."], "nextFocus": ["..."]}

- summary: 2-3 plain sentences naming the student and the concrete words or \
structures they got right and wrong. Another teacher must be able to read it \
next week and know where to start. No praise, no filler. Include the skill \
keys you were shown, spelled exactly as given (animal_vocab, not "animal \
vocabulary") -- that is how this note gets found again.
- weakPoints: up to 3 short phrases, the actual things they missed.
- nextFocus: up to 3 short phrases, what to teach or re-check next time."""

#: Outcomes that count as a miss when estimating a skill from observations.
_MISS = ("wrong", "silence", "timeout")


def _close_open_brackets(fragment: str) -> str | None:
    """Finish a JSON object the model stopped writing halfway through.

    Observed live against MiMo: a summary came back as a complete, valid
    object *minus its final brace*, with `finish_reason: "stop"` and 83 of 400
    completion tokens used -- so not a length cut-off, just a dropped token.
    Strict parsing threw the whole reply away and the deterministic fallback
    wrote a worse note in its place. Repairing the tail costs nothing and is
    strictly better than discarding a good summary over one character.

    Returns ``None`` when nothing was open, i.e. there is nothing to repair.
    """
    stack: list[str] = []
    in_string = escaped = False
    for ch in fragment:
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch in "{[":
            stack.append(ch)
        elif ch in "}]" and stack:
            stack.pop()
    if not stack and not in_string:
        return None
    body = fragment.rstrip()
    if not in_string:
        # A trailing comma is legal to write and illegal to parse.
        body = body.rstrip(",")
    tail = '"' if in_string else ""
    tail += "".join("}" if opener == "{" else "]" for opener in reversed(stack))
    return body + tail


def extract_json(text: str) -> dict[str, Any] | None:
    """Pull one JSON object out of a model reply.

    Tolerates code fences, surrounding prose, and a truncated tail. An empty
    object counts as nothing found: repairing ``"{"`` yields ``{}``, which is
    parseable and useless, and every caller would reject it anyway.
    """
    if not text:
        return None
    start = text.find("{")
    if start < 0:
        return None

    candidates: list[str] = []
    end = text.rfind("}")
    if end > start:
        candidates.append(text[start : end + 1])
    repaired = _close_open_brackets(text[start:])
    if repaired:
        candidates.append(repaired)

    for candidate in candidates:
        try:
            value = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(value, dict) and value:
            return value
    return None


def skill_estimates(observations: list[dict[str, Any]]) -> dict[str, float]:
    """Hit rate per skill, counted by us and never asked of the model.

    `correct` scores 2, `near` 1, a miss 0, out of 2 per observation. A
    language model asked for "a number between 0 and 1" supplies confident
    noise, and north-star §7 rules out invented precision. Counting is free
    and it is correct.
    """
    hits: dict[str, int] = {}
    total: dict[str, int] = {}
    for obs in observations:
        skill = str(obs.get("skill") or "").strip()
        if not skill:
            continue
        result = str(obs.get("result") or "")
        if result == "correct":
            score = 2
        elif result == "near":
            score = 1
        elif result in _MISS:
            score = 0
        else:
            continue  # not a graded outcome; ignore rather than dilute
        hits[skill] = hits.get(skill, 0) + score
        total[skill] = total.get(skill, 0) + 2
    return {skill: round(hits[skill] / n, 3) for skill, n in total.items() if n}


def deterministic_summary(
    observations: list[dict[str, Any]], student_name: str | None
) -> dict[str, Any]:
    """The summary we can always write, with no model involved.

    NS-1 applies to memory too: a session whose summariser was unreachable
    must still leave a usable trace, or next week's greeting has nothing to
    remember. Prose is worse than the model's; presence beats eloquence.
    """
    who = student_name or "the student"
    by_result: dict[str, list[str]] = {}
    for obs in observations:
        by_result.setdefault(str(obs.get("result") or "?"), []).append(
            str(obs.get("skill") or "?")
        )
    correct = sorted(set(by_result.get("correct", [])))
    missed = sorted({s for r in _MISS for s in by_result.get(r, [])})
    bits = [f"{who} answered {len(observations)} item(s) this session."]
    if correct:
        bits.append("Confident with: " + ", ".join(correct) + ".")
    if missed:
        bits.append("Struggled with: " + ", ".join(missed) + ".")
    return {
        "summary": " ".join(bits),
        "weakPoints": missed[:3],
        "nextFocus": missed[:3] or correct[:3],
    }


class SessionSummarizer:
    """The real `summarize_session`: observations in, a durable note out.

    Runs 30 s after a session ends (docs/4-build/phase-1-plan.md §6), off any
    hot path, over the same agent the class used — one non-streaming
    completion, not a tool loop. What it writes is what `classroom_recall`
    finds next week, which is the whole point of the exercise.
    """

    def __init__(self, core: Any, agent: Any, *, max_observations: int = 40) -> None:
        self.core = core
        self.agent = agent
        self.max_observations = max_observations
        self.calls = 0
        self.fallbacks = 0

    async def __call__(
        self, session_id: str, observations: list[dict[str, Any]]
    ) -> dict[str, Any] | None:
        if not observations:
            log.info("[agent] session %s had no observations; nothing to summarise", session_id)
            return None
        self.calls += 1

        session = self._session(session_id)
        student_id = session.get("student_id")
        student_name = self._student_name(student_id)
        provider_name = (
            student_name
            if getattr(self.core.settings, "agent_context_policy", "hosted-minimal")
            == "local-trusted"
            else "the current student"
        )

        result = await self._ask(session_id, observations, session, provider_name)
        if result is None:
            self.fallbacks += 1
            result = deterministic_summary(observations, student_name)

        result["studentId"] = student_id
        result["skills"] = skill_estimates(observations)
        return result

    # ------------------------------------------------------------- helpers
    def _session(self, session_id: str) -> dict[str, Any]:
        try:
            return self.core.db.get_session(session_id) or {}
        except Exception as exc:  # noqa: BLE001
            log.warning("session lookup failed for %s: %s", session_id, exc)
            return {}

    def _student_name(self, student_id: str | None) -> str | None:
        if not student_id:
            return None
        try:
            row = self.core.db.get_student(student_id)
        except Exception as exc:  # noqa: BLE001
            log.warning("student lookup failed for %s: %s", student_id, exc)
            return None
        return (row or {}).get("name") or student_id

    def _render(
        self,
        observations: list[dict[str, Any]],
        session: dict[str, Any],
        student_name: str | None,
    ) -> str:
        lines = [
            f"STUDENT {student_name or 'unknown'}",
            f"LESSON {session.get('lesson_id') or 'unknown'}",
            "WHAT HAPPENED, in order:",
        ]
        for obs in observations[-self.max_observations :]:
            lines.append(
                f"- {obs.get('skill')} → {obs.get('result')}: "
                f"{str(obs.get('evidence') or '')[:160]}"
            )
        return "\n".join(lines)

    async def _ask(
        self,
        session_id: str,
        observations: list[dict[str, Any]],
        session: dict[str, Any],
        student_name: str | None,
    ) -> dict[str, Any] | None:
        complete = getattr(self.agent, "complete", None)
        if complete is None:
            return None
        messages = [
            {"role": "system", "content": SUMMARY_SYSTEM},
            {"role": "user", "content": self._render(observations, session, student_name)},
        ]
        try:
            payload = await complete(messages, max_tokens=400)
        except Exception as exc:  # noqa: BLE001 — a summary is never worth a crash
            log.warning("[agent] summarize_session LLM call failed for %s: %r", session_id, exc)
            return None

        try:
            text = payload["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError, TypeError):
            log.warning("[agent] summarize_session got an unreadable reply for %s", session_id)
            return None

        data = extract_json(text)
        if not data or not str(data.get("summary") or "").strip():
            # Log the reply, not just the fact of it: the fallback hides this
            # failure completely, so without the text nobody would ever know
            # *why* every summary in the DB is the deterministic one.
            log.warning(
                "[agent] summarize_session reply had no usable JSON for %s: %.300r",
                session_id,
                text,
            )
            return None
        return {
            "summary": str(data["summary"]).strip(),
            "weakPoints": [str(x) for x in (data.get("weakPoints") or [])][:3],
            "nextFocus": [str(x) for x in (data.get("nextFocus") or [])][:3],
        }


def make_probe(agent: Any, *, max_tokens: int = 1) -> Callable[[], Awaitable[float | None]]:
    """The `health_probe` seam: measure the agent, cheaply.

    One completion with a one-token budget. `ModeController` turns the number
    into FULL / DEGRADED / OFFLINE; ``None`` means unreachable. Without this
    the mode never leaves OFFLINE unless `CORE_MODE` pins it, and an unpinned
    deployment would never take an automatic turn at all.
    """

    async def probe() -> float | None:
        complete = getattr(agent, "complete", None)
        if complete is None:
            return None
        started = time.perf_counter()
        try:
            await complete([{"role": "user", "content": "ping"}], max_tokens=max_tokens)
        except Exception as exc:  # noqa: BLE001 — unreachable is a measurement
            log.info("[agent] health probe failed: %r", exc)
            return None
        return time.perf_counter() - started

    return probe


def build_agent_seam(core: Any, agent: Any) -> AgentSeam:
    """The background-job half of the seam, over an already-built agent.

    classroom-core still makes no LLM call of its own: everything model-shaped
    is behind the `agent` object that `services/agent` supplied.
    """
    return AgentSeam(
        summarize_session=SessionSummarizer(core, agent),
        probe=make_probe(agent),
    )


__all__ = [
    "available_actions",
    "build_turn_context",
    "default_recall_query",
    "make_tool_executor",
    "AgentDriver",
    "AutoTurn",
    "TurnResult",
    "TurnScope",
    "SessionSummarizer",
    "SUMMARY_SYSTEM",
    "build_agent_seam",
    "deterministic_summary",
    "extract_json",
    "make_probe",
    "skill_estimates",
]
