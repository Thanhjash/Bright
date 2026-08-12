"""The lesson runner -- the reflex tier (docs/3-design/architecture.md §2, NS-1).

Plays a compiled ``LessonRun`` from start to finish **with no LLM anywhere**:
renders the Scene for each activity, speaks the authored narration, grades
interactions against ``expect`` and follows ``branches``.

Timing semantics (PROTOCOL.md §4 leaves these open; this is the reading this
service implements):

===========================  ==========================================
activity shape               on timer expiry
===========================  ==========================================
``durationS``, no ``expect`` auto-advance (``always`` branch, else next)
``durationS`` + ``expect``   outcome ``timeout``
``expect``, no ``durationS`` outcome ``silence`` after ``silence_timeout_s``
neither                      wait for a control command
===========================  ==========================================

Every ``_enter`` bumps a generation token; a timer that fires for a superseded
generation is a no-op, so an interaction and its stale auto-advance timer can
never both advance the lesson.

**The decision gate** (``decide_next``) is the one place a pedagogy-tier
component may change what happens next.  It is called *after* grading, the
reveal frame and the immediate feedback -- never before, so nothing a child
does waits on a model (NS-2) -- and it is optional: with no gate wired the
runner behaves exactly as it did before one existed (NS-1).
"""

from __future__ import annotations

import asyncio
import difflib
import logging
import re
import time
from typing import Any, Awaitable, Callable, Literal

import config  # noqa: F401  -- installs the bright_contracts import path
from bright_contracts import Activity, Branch, Expect, LessonPosition, LessonRun, Narration

log = logging.getLogger("core.runner")

Outcome = Literal["correct", "near", "wrong", "silence", "timeout"]

#: ``decide_next(activity, outcome, payload) -> action_id | None``.
#:
#: ``None`` means "I did not act": take the authored branch, exactly as if no
#: gate were wired.  A returned action id means the gate already applied it;
#: if that action moved the lesson the branch is dropped, and if it did not
#: (``say_only``) the branch is *deferred*, never cancelled.
DecideFn = Callable[[Activity, "Outcome", dict[str, Any]], Awaitable[str | None]]

_PUNCT_RE = re.compile(r"[^\w\s']+", re.UNICODE)
_WS_RE = re.compile(r"\s+")
FUZZY_RATIO = 0.82
SPEECH_CORRECT_CONFIDENCE = 0.75


# --------------------------------------------------------------- grading


def normalize_text(value: str) -> str:
    text = _PUNCT_RE.sub(" ", (value or "").strip().lower())
    return _WS_RE.sub(" ", text).strip()


def _as_list(value: str | list[str] | None) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    return list(value)


def _speech_matches(said: str, target: str, *, approximate: bool = False) -> bool:
    """Exact match. ``approximate`` additionally allows a close
    edit-distance match -- used only for ``acceptFuzzy``, never for ``correct``,
    so "I like cat" cannot be graded correct against "I like cats"."""
    said_n, target_n = normalize_text(said), normalize_text(target)
    if not said_n or not target_n:
        return False
    if said_n == target_n:
        return True
    if not approximate:
        return False
    return difflib.SequenceMatcher(None, said_n, target_n).ratio() >= FUZZY_RATIO


def interaction_kind(event_type: str) -> str:
    """``interaction.choice`` -> ``choice``; ``student.speech.final`` -> ``speech``."""
    if event_type.startswith("interaction."):
        return event_type.split(".", 1)[1]
    if event_type == "student.speech.final":
        return "speech"
    return event_type


def grade(
    expect: Expect | None,
    kind: str,
    payload: dict[str, Any],
    *,
    speech_correct_confidence: float = SPEECH_CORRECT_CONFIDENCE,
) -> Outcome | None:
    """Grade one interaction. ``None`` means "not for this activity, ignore".

    Pure and allocation-light: this is the <100 ms reflex path.
    """
    if expect is None or expect.kind == "none":
        return None
    if expect.kind != kind:
        return None

    payload = payload or {}
    correct = _as_list(expect.correct)
    fuzzy = list(expect.accept_fuzzy or [])

    if kind == "speech":
        said = str(payload.get("text", ""))
        if not said.strip():
            return "silence"
        if any(_speech_matches(said, target) for target in correct):
            try:
                confidence = float(payload.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0
            return "correct" if confidence >= speech_correct_confidence else "near"
        if any(_speech_matches(said, target, approximate=True) for target in fuzzy):
            return "near"
        return "wrong"

    if kind == "choice":
        candidates = [str(payload.get("optionId", ""))]
    elif kind == "point":
        candidates = [str(payload.get("targetId", ""))]
    elif kind == "drag":
        candidates = drag_candidates(payload)
    else:  # pragma: no cover - guarded by expect.kind check above
        return None

    candidates = [c for c in candidates if c]
    if not candidates:
        return "silence"
    if any(c in correct for c in candidates):
        return "correct"
    # acceptFuzzy generalised to id-based interactions: a "near miss" option.
    if any(c in fuzzy for c in candidates):
        return "near"
    return "wrong"


def drag_candidates(payload: dict[str, Any], *, include_from: bool = False) -> list[str]:
    """Every authored form one ``interaction.drag`` could be written as.

    PROTOCOL §9.4: "``drag`` matches either ``toId`` or the pair form
    ``fromId>toId``". The colon form is accepted as a spelling of the pair.

    ``include_from`` adds the bare ``fromId``, and is used **only** for
    ``sentence_builder``. A sentence builder has no drop-target ids to author
    against -- ``SentenceBuilderProps`` is ``{tokens, placed, target}``, so the
    only ids in the scene are token ids -- and the answer is *which token was
    dragged*. Without this, a board that reports its drop zone in ``toId``
    could not be graded at all, and no id it could invent would appear in the
    lesson. Matching, which has ids on both sides, keeps the §9.4 forms exactly.
    """
    from_id = str(payload.get("fromId") or "")
    to_id = str(payload.get("toId") or "")
    candidates: list[str] = []
    if to_id:
        candidates.append(to_id)
    if from_id and to_id:
        candidates += [f"{from_id}>{to_id}", f"{from_id}:{to_id}"]
    if include_from and from_id:
        candidates.append(from_id)
    return candidates


def grade_drag(
    expect: Expect | None,
    payload: dict[str, Any],
    done: list[str],
    *,
    ordered: bool = False,
    include_from: bool = False,
) -> tuple[Outcome | None, str | None]:
    """Grade one move of a possibly multi-move drag.

    Returns ``(outcome, matched)``:

    ``(None, "cat>meow")``  the move was right and there is more to do --
                            partial progress, nothing is graded yet
    ``(None, None)``        the move is a no-op: a pair already solved, or a
                            token already placed. Thirty children round a
                            projector re-drop things; a re-drop is not an error
    ``("correct", entry)``  that was the last required move
    ``("near"/"wrong", None)`` graded immediately, as a `choice` would be

    **A list under a `drag` ``expect.correct`` is a list of required moves**,
    not a list of alternatives -- which is what a `matching` activity with
    three pairs actually needs, and why a single drag can no longer be assumed
    final. A single-entry list (or a bare string) behaves exactly as before:
    one right move ends the activity.

    ``ordered`` makes the moves a sequence rather than a set: only the next
    unplaced entry counts, which is what a sentence is.
    """
    if expect is None or expect.kind != "drag":
        return None, None

    required = _as_list(expect.correct)
    candidates = drag_candidates(payload or {}, include_from=include_from)
    if not candidates:
        return "silence", None

    remaining = [entry for entry in required if entry not in done]
    if not remaining:  # pragma: no cover - the activity is already graded
        return None, None

    targets = remaining[:1] if ordered else remaining
    for entry in targets:
        if entry in candidates:
            return ("correct" if len(remaining) == 1 else None), entry

    # A re-drop of something already accepted is not a wrong answer.
    if any(entry in candidates for entry in done):
        return None, None

    if any(c in (expect.accept_fuzzy or []) for c in candidates):
        return "near", None
    return "wrong", None


def resolve_branch(activity: Activity, outcome: Outcome) -> Branch | None:
    """Exact match first, then ``always``. Authoring guarantees one exists
    for every activity carrying an ``expect`` (PROTOCOL §4 lesson-lint rule)."""
    branches = activity.branches or []
    for branch in branches:
        if branch.on == outcome:
            return branch
    for branch in branches:
        if branch.on == "always":
            return branch
    return None


_STAGE_BY_KIND = {
    "idle": "IDLE",
    "text": "INPUT",
    "image": "INPUT",
    "video": "INPUT",
    "vocabulary": "INPUT",
    "choice": "PRACTICE",
    "matching": "PRACTICE",
    "sentence_builder": "PRACTICE",
    "pronunciation": "PRACTICE",
    "roleplay": "PRODUCTION",
    "explore": "EXPLORE",
}


def stage_for(activity: Activity, index: int, total: int) -> str:
    """LessonRun carries no explicit stage; derive one for LessonPosition."""
    if index == 0:
        return "HOOK"
    if index == total - 1 and activity.scene in ("text", "idle"):
        return "WRAP"
    return _STAGE_BY_KIND.get(activity.scene, "PRACTICE")


# ---------------------------------------------------------------- runner


class LessonRunner:
    def __init__(
        self,
        bus: Any,
        store: Any,
        lesson: LessonRun,
        *,
        db: Any = None,
        session_id: str | None = None,
        student_id: str | None = None,
        silence_timeout_s: float = 15.0,
        reveal_hold_s: float = 1.2,
        speech_correct_confidence: float = SPEECH_CORRECT_CONFIDENCE,
        playback_ack_timeout_s: float = 10.0,
        on_outcome: Callable[[Activity, Outcome, dict[str, Any]], Awaitable[None] | None]
        | None = None,
        on_finish: Callable[[], Awaitable[None] | None] | None = None,
        decide_next: DecideFn | None = None,
        publish_speech: Callable[..., str] | None = None,
        cancel_speech: Callable[[str], None] | None = None,
    ) -> None:
        self.bus = bus
        self.store = store
        self.lesson = lesson
        self.db = db
        self.session_id = session_id
        #: Whose session this is, when the whole run is one child. Used as the
        #: fallback attribution for observations whose payload omits it --
        #: otherwise the rows land with a NULL student and recall can never
        #: find them again.
        self.student_id = student_id
        self.silence_timeout_s = silence_timeout_s
        self.reveal_hold_s = reveal_hold_s
        self.speech_correct_confidence = max(0.0, min(1.0, speech_correct_confidence))
        self.playback_ack_timeout_s = max(0.1, playback_ack_timeout_s)
        self.on_outcome = on_outcome
        self.on_finish = on_finish
        #: Left ``None`` unless something is actually wired in. Not "a hook
        #: that returns early" -- with no agent the code path below must not
        #: exist at all (NS-1).
        self.decide_next = decide_next
        self.publish_speech = publish_speech
        self.cancel_speech = cancel_speech

        self._index = -1
        self._generation = 0
        self._timer: asyncio.Task[None] | None = None
        self._awaiting_playback_turn: str | None = None
        self._pending_playback_turns: list[str] = []
        self._awaiting_timer: tuple[Activity, int] | None = None
        self._playback_watchdog: asyncio.Task[None] | None = None
        self._pending: set[asyncio.Task[None]] = set()
        self.running = False
        self.paused = False
        self.finished = False
        self.last_outcome: Outcome | None = None
        self.last_latency_ms: float = 0.0
        #: The payload of the last graded interaction, so a timer-driven
        #: outcome can still tell the gate what the child last did.
        self.last_payload: dict[str, Any] = {}
        self.answered = False
        self._turn = 0
        #: Authored ``expect.correct`` entries already satisfied on the current
        #: activity, and the raw moves that satisfied them. A `matching` board
        #: needs several pairs before there is anything to grade, so the runner
        #: keeps the canonical progress and re-publishes it -- a client's own
        #: idea of what it has solved is never read back in.
        self._drag_done: list[str] = []
        self._drag_moves: list[tuple[str, str]] = []
        #: How many times each activity has been entered. Read by the agent gate
        #: so `repeat_activity` stops being OFFERED once an activity has been
        #: repeated enough — a model that keeps choosing "say it again" would
        #: otherwise loop forever (observed: 6/6 cycles, index never moved,
        #: ~1500 prompt tokens burnt per cycle while the class sat waiting).
        #: Refusing to offer the action beats rejecting it after the fact: the
        #: model never sees a choice it should not make.
        self.entry_counts: dict[str, int] = {}

    # ------------------------------------------------------------ helpers
    @property
    def activities(self) -> list[Activity]:
        return self.lesson.activities

    @property
    def index(self) -> int:
        return self._index

    @property
    def current(self) -> Activity | None:
        if 0 <= self._index < len(self.activities):
            return self.activities[self._index]
        return None

    def index_of(self, activity_id: str) -> int:
        for i, activity in enumerate(self.activities):
            if activity.id == activity_id:
                return i
        return -1

    def _cancel_timer(self) -> None:
        if self._timer is not None and not self._timer.done():
            self._timer.cancel()
        self._timer = None

    def _cancel_playback_watchdog(self) -> None:
        if self._playback_watchdog is not None and not self._playback_watchdog.done():
            self._playback_watchdog.cancel()
        self._playback_watchdog = None

    def _spawn(self, coro: Awaitable[None]) -> asyncio.Task[None]:
        task = asyncio.ensure_future(coro)
        self._pending.add(task)
        task.add_done_callback(self._pending.discard)
        return task

    async def drain(self) -> None:
        """Await every follow-up task (branch narration, delayed jumps, DB writes).

        Deliberately does *not* await the auto-advance timer -- that is not a
        follow-up, it is the next scheduled event.
        """
        while self._pending:
            batch = tuple(self._pending)
            await asyncio.gather(*batch, return_exceptions=True)
            # Do not rely solely on add_done_callback to mutate the set. On
            # Python 3.13 the callback may be queued for the next loop turn
            # after gather has already returned; immediately gathering the
            # same completed tasks then spins forever and starves that callback.
            self._pending.difference_update(task for task in batch if task.done())

    async def stop(self) -> None:
        self.running = False
        self._generation += 1
        self._cancel_timer()
        self._cancel_playback_watchdog()
        for task in tuple(self._pending):
            task.cancel()
        if self._pending:
            await asyncio.gather(*tuple(self._pending), return_exceptions=True)
        self._pending.clear()

    # --------------------------------------------------------------- play
    async def start(self, index: int = 0) -> Activity | None:
        self.running = True
        self.finished = False
        self.paused = False
        if not self.activities:
            self._publish_position()
            return None
        return await self._enter(index)

    async def _enter(self, index: int) -> Activity | None:
        if index < 0 or index >= len(self.activities):
            await self._finish()
            return None

        self._cancel_timer()
        self._cancel_playback_watchdog()
        self._awaiting_playback_turn = None
        self._pending_playback_turns = []
        self._awaiting_timer = None
        self._generation += 1
        generation = self._generation
        self._index = index
        self.answered = False
        self._drag_done = []
        self._drag_moves = []
        activity = self.activities[index]
        self.entry_counts[activity.id] = self.entry_counts.get(activity.id, 0) + 1

        scene = self.store.set_scene(activity.scene, dict(activity.props or {}))
        self.store.update_lesson(
            lesson_id=self.lesson.lesson_id,
            class_id=self.lesson.class_id,
            activity_index=index,
            activity_count=len(self.activities),
            stage=stage_for(activity, index, len(self.activities)),
            activity_id=activity.id,
            activity_generation=generation,
        )
        self.bus.publish("scene.update", self.store.scene)
        self._publish_position()

        turn_ids = self._speak(activity.narration, activity.id)
        if turn_ids and self.publish_speech is not None:
            # Classroom time starts when the authored prompt has physically
            # finished playing, not when Core finished producing its text.
            self._awaiting_playback_turn = turn_ids[-1]
            self._pending_playback_turns = list(turn_ids)
            self._awaiting_timer = (activity, generation)
            self._watch_playback_turn(turn_ids[0])
        else:
            self._arm_activity(activity, generation)
        return activity

    def _publish_position(self) -> None:
        lesson: LessonPosition = self.store.lesson
        self.bus.publish("lesson.position", lesson)

    def _publish_epoch(self) -> None:
        """Expose every invalidation token; silent activities need it too."""
        self.store.update_lesson(activity_generation=self._generation)
        self._publish_position()

    def _watch_playback_turn(self, speech_turn_id: str) -> None:
        self._cancel_playback_watchdog()
        self._playback_watchdog = asyncio.ensure_future(
            self._release_after_playback_timeout(speech_turn_id)
        )

    def on_playback_started(self, speech_turn_id: str) -> bool:
        """Restart the timeout from physical audio, never original publish."""
        if not self._pending_playback_turns:
            return False
        if speech_turn_id != self._pending_playback_turns[0]:
            return False
        self._watch_playback_turn(speech_turn_id)
        return True

    def on_playback_finished(self, speech_turn_id: str) -> bool:
        """Arm the live activity only after its final narration is audible."""
        if not self._pending_playback_turns or self._awaiting_timer is None:
            return False
        if speech_turn_id != self._pending_playback_turns[0]:
            return False
        self._pending_playback_turns.pop(0)
        self._cancel_playback_watchdog()
        if self._pending_playback_turns:
            self._watch_playback_turn(self._pending_playback_turns[0])
            return True
        activity, generation = self._awaiting_timer
        self._awaiting_playback_turn = None
        self._pending_playback_turns = []
        self._awaiting_timer = None
        if generation != self._generation or not self.running or self.paused:
            return False
        self._arm_activity(activity, generation)
        return True

    async def _release_after_playback_timeout(self, speech_turn_id: str) -> None:
        try:
            await asyncio.sleep(self.playback_ack_timeout_s)
        except asyncio.CancelledError:
            return
        log.warning("playback ack timed out for %s; releasing lesson", speech_turn_id)
        self._playback_watchdog = None
        self.on_playback_finished(speech_turn_id)

    def _arm_activity(self, activity: Activity, generation: int) -> None:
        expects_speech = activity.expect is not None and activity.expect.kind == "speech"
        if expects_speech:
            self.store.set_overlay(listening=True)
            self.bus.publish("scene.update", self.store.scene)
        self._schedule_timer(activity, generation)

    def _speak(self, narration: list[Narration] | None, activity_id: str) -> list[str]:
        turn_ids: list[str] = []
        for i, line in enumerate(narration or []):
            if self.publish_speech is not None:
                turn_id = self.publish_speech(
                    line.text,
                    source="authored",
                    behavior="queue",
                    activity_id=activity_id,
                    activity_generation=self._generation,
                    audio_asset=line.audio_asset,
                )
            else:
                # Standalone runner tests may omit the Core coordinator.  They
                # still speak v2; only the globally unique correlation comes
                # from Core in production.
                self._turn += 1
                turn_id = f"{activity_id}:{i}:{self._turn}"
                self.bus.publish(
                    "speech.turn.started",
                    {
                        "speechTurnId": turn_id,
                        "behavior": "queue",
                        "source": "authored",
                        "conversationTurnId": turn_id,
                        "activityId": activity_id,
                        "activityGeneration": self._generation,
                        **({"audioAsset": line.audio_asset} if line.audio_asset else {}),
                    },
                )
                self.bus.publish(
                    "speech.text.delta", {"speechTurnId": turn_id, "delta": line.text}
                )
                self.bus.publish(
                    "speech.turn.ended", {"speechTurnId": turn_id, "status": "completed"}
                )
            turn_ids.append(turn_id)
            if line.act is not None:
                self.bus.publish("avatar.act", line.act)
        return turn_ids

    # -------------------------------------------------------------- timers
    def _schedule_timer(self, activity: Activity, generation: int) -> None:
        expects = activity.expect is not None and activity.expect.kind != "none"
        if activity.duration_s:
            delay = float(activity.duration_s)
            outcome: Outcome | None = "timeout" if expects else None
        elif expects:
            delay = float(self.silence_timeout_s)
            outcome = "silence"
        else:
            return  # wait for interaction / control command
        # Kept off ``_pending`` on purpose: drain() must not wait for a timer.
        self._timer = asyncio.ensure_future(self._run_timer(delay, generation, outcome))

    async def _run_timer(
        self,
        delay: float,
        generation: int,
        outcome: Outcome | None,
        gate: bool = True,
        announce: bool = True,
    ) -> None:
        try:
            await asyncio.sleep(delay)
        except asyncio.CancelledError:
            return
        if generation != self._generation or not self.running or self.paused:
            return  # superseded by an interaction / control command
        if outcome is None:
            # Auto-advance: no ``expect``, so nothing was graded and there is
            # no pedagogical decision to make. The gate is not consulted.
            await self._advance_default()
        else:
            # `silence` and `timeout` are graded outcomes like any other -- a
            # child who says nothing needs a different answer from one who
            # answers wrongly -- so they go through the same gate. No reveal
            # frame was drawn, so there is no hold to overlap.
            await self._follow(outcome, generation, 0.0, gate=gate, announce=announce)

    # --------------------------------------------------------- interaction
    async def handle_interaction(
        self, kind: str, payload: dict[str, Any] | None = None
    ) -> Outcome | None:
        """Grade an interaction and give immediate visual feedback.

        Returns as soon as the reflex work is done; the branch jump (which may
        hold the reveal on screen) continues in a background task.  Use
        ``await runner.drain()`` to wait for it.
        """
        started = time.perf_counter()
        activity = self.current
        if activity is None or not self.running:
            return None
        kind = interaction_kind(kind)
        payload = dict(payload or {})

        # ONE answer per activity. `self.answered` was being set here and never
        # read, so the last tap won and did real damage: the board re-revealed a
        # different answer, the branch taken was the later one, and the child was
        # recorded in memory as BOTH correct and wrong for the same question.
        #
        # Thirty children round a projector will produce a second tap — an excited
        # one, a disagreeing one, a stray hand during the 1.2 s reveal hold. The
        # first answer is the answer.
        if self.answered:
            log.info(
                "ignoring extra %s on '%s': already answered (%s)",
                kind, activity.id, self.last_outcome,
            )
            return None

        if kind == "drag" and activity.expect is not None and activity.expect.kind == "drag":
            outcome = self._grade_drag_move(activity, payload)
        else:
            outcome = grade(
                activity.expect,
                kind,
                payload,
                speech_correct_confidence=self.speech_correct_confidence,
            )
        if outcome is None:
            return None

        self._generation += 1           # invalidate the pending timer
        self._cancel_timer()
        self._awaiting_playback_turn = None
        self._pending_playback_turns = []
        self._awaiting_timer = None
        self._cancel_playback_watchdog()
        self._publish_epoch()
        self.answered = True
        self.last_outcome = outcome
        generation = self._generation

        self._reveal(activity, kind, payload, outcome)
        self._record(activity, kind, payload, outcome)
        self.last_payload = payload
        self.last_latency_ms = (time.perf_counter() - started) * 1000.0

        hold = self.reveal_hold_s if outcome in ("correct", "near", "wrong") else 0.0
        self._spawn(self._follow(outcome, generation, hold))
        return outcome

    # ------------------------------------------------------ multi-move drag
    def _grade_drag_move(self, activity: Activity, payload: dict[str, Any]) -> Outcome | None:
        """One move of a drag activity. ``None`` = nothing to grade yet.

        `matching` needs one move per pair and `sentence_builder` one per
        token, so treating the first drag as the answer would end a three-pair
        exercise on its first pair. Each accepted move instead lands on the
        board (`scene.update` with the new ``solved`` / ``placed``, which moves
        ``stateVersion`` for free) and re-opens the answer window; only the
        last one is graded, and only then does the activity branch.

        A wrong move is graded straight away, exactly as a wrong `choice` is:
        the authored `wrong` branch is where the help lives, and a child who
        has misunderstood the exercise should not be left dragging.
        """
        ordered = activity.scene == "sentence_builder"
        outcome, matched = grade_drag(
            activity.expect,
            payload,
            self._drag_done,
            ordered=ordered,
            include_from=ordered,
        )
        if matched is not None:
            self._drag_done.append(matched)
            self._drag_moves.append(
                (str(payload.get("fromId") or ""), str(payload.get("toId") or ""))
            )
        if outcome is None:
            if matched is None:
                log.info("ignoring no-op drag on '%s': %r", activity.id, payload)
                return None
            # Progress, not an answer: draw it and give the child their time back.
            self._publish_drag_progress(activity)
            self._cancel_timer()
            self._schedule_timer(activity, self._generation)
            log.info(
                "drag progress on '%s': %d/%d",
                activity.id, len(self._drag_done), len(_as_list(activity.expect.correct)),
            )
            return None
        return outcome

    def _drag_props(self, activity: Activity) -> dict[str, Any] | None:
        """The authored props plus the progress the runner is holding."""
        props = dict(activity.props or {})
        if activity.scene == "matching":
            props["solved"] = [[left, right] for left, right in self._drag_moves]
            return props
        if activity.scene == "sentence_builder":
            props["placed"] = [
                self._placed_token(activity, move, entry)
                for move, entry in zip(self._drag_moves, self._drag_done)
            ]
            return props
        return None

    @staticmethod
    def _placed_token(activity: Activity, move: tuple[str, str], entry: str) -> str:
        """Which id of the move names a token. The dragged one, if we can tell."""
        tokens = {
            str(t.get("id"))
            for t in (activity.props or {}).get("tokens") or []
            if isinstance(t, dict) and t.get("id")
        }
        for candidate in (move[0], move[1], entry.split(">")[0], entry):
            if candidate and candidate in tokens:
                return candidate
        return move[0] or entry

    def _publish_drag_progress(self, activity: Activity) -> None:
        props = self._drag_props(activity)
        if props is None:
            # Some other scene grading a drag: nothing to draw, but a graded
            # move still has to move the version (see ``_reveal``).
            self.store.set_overlay(**{})
        else:
            self.store.set_scene(activity.scene, props, self.store.scene.overlay)
        self.bus.publish("scene.update", self.store.scene)

    def _reveal(
        self, activity: Activity, kind: str, payload: dict[str, Any], outcome: Outcome
    ) -> None:
        """Immediate, LLM-free feedback on the board."""
        if activity.scene == "choice" and kind == "choice":
            props = dict(activity.props or {})
            correct = _as_list(activity.expect.correct if activity.expect else None)
            props["revealed"] = {
                "correctId": correct[0] if correct else "",
                "chosenId": str(payload.get("optionId", "")),
            }
            self.store.set_scene(activity.scene, props, self.store.scene.overlay)
            self.bus.publish("scene.update", self.store.scene)
        elif kind == "drag" and self._drag_props(activity) is not None:
            # The completed board, before the branch: the last pair a child
            # joined must be on screen during the reveal hold, not replaced by
            # the next activity a beat later.
            self._publish_drag_progress(activity)
        elif activity.scene == "vocabulary" and kind == "point":
            props = dict(activity.props or {})
            props["highlightId"] = str(payload.get("targetId", ""))
            self.store.set_scene(activity.scene, props, self.store.scene.overlay)
            self.bus.publish("scene.update", self.store.scene)
        else:
            # Every graded answer MUST move `state_version`, even when there is
            # nothing to draw.
            #
            # `drag` drew nothing and so bumped nothing, which left the agent's
            # `state_version` gate blind: a decision computed for answer 1 still
            # validated as current after answer 2. (`speech` escaped this only by
            # accident — its handler happens to set a subtitle overlay first.)
            #
            # A no-op overlay write is enough: the version is the contract, the
            # pixels are incidental.
            self.store.set_overlay(**{})
            self.bus.publish("scene.update", self.store.scene)

    def _record(
        self, activity: Activity, kind: str, payload: dict[str, Any], outcome: Outcome
    ) -> None:
        if self.on_outcome is not None:
            result = self.on_outcome(activity, outcome, payload)
            if asyncio.iscoroutine(result):
                self._spawn(result)
        if self.db is None:
            return
        # An observation with a NULL student is a row recall can never find
        # again. When the whole session belongs to one child, say so.
        student_id = payload.get("studentId") or self.student_id
        # Payloads may contain a child's raw ASR transcript. Durable learner
        # memory keeps only Core-owned facts: activity, response modality and
        # graded outcome. The live transcript is deliberately not persisted or
        # FTS-indexed.
        evidence = f"activity={activity.id}; response_kind={kind}; outcome={outcome}"
        skill = (self.lesson.focus or ["general"])[0]
        # This coroutine is scheduled after the reflex response has returned,
        # so it is already off the answer-to-pixels path.  Keep SQLite on the
        # event-loop thread: the connection is one Core-owned writer and a
        # default-executor hop can outlive TestClient/lifespan shutdown (and on
        # Python 3.13 has been observed to leave the loop waiting forever for
        # its worker wake-up).  The transaction is a bounded local insert.
        async def persist_observation() -> None:
            self.db.record_observation(
                student_id,
                skill,
                outcome,
                evidence,
                self.session_id,
            )

        self._spawn(persist_observation())

    async def _follow(
        self,
        outcome: Outcome,
        generation: int,
        hold: float,
        gate: bool = True,
        announce: bool = True,
    ) -> None:
        """Respond **now**, then hold the reveal, consult the gate, and branch.

        ``_respond`` is the important line and it is deliberately first.
        Measured on the running system: with the agent off, answer→board was
        1.24 s; with the agent on, 4.45 s. The reflex tier was already giving
        visual feedback in 3 ms and then the room sat in silence for four
        seconds, so the intelligence — the entire point of the product — made
        it feel broken. The four seconds have not gone away; they are now full
        of teaching, because the authored branch narration that core already
        holds is spoken immediately instead of after the model answers
        (docs/4-build/execution-plan.md §3, "two-stage response").

        The gate is started *before* the hold, so a model that thinks for a
        second thinks during a second the class was already spending looking
        at the answer. Added latency is therefore ``max(0, gate - hold)``, not
        ``gate``.

        ``gate=False`` on the second pass over a deferred outcome. One
        outcome gets one turn: without this a model that keeps choosing
        `say_only` would defer its own branch forever and the lesson would
        stand still while sounding busy.
        """
        activity = self.current
        branch = resolve_branch(activity, outcome) if activity is not None else None
        # ``announce=False`` on the deferred second pass: this outcome's line
        # was already spoken, at reflex speed, before the model was consulted.
        spoken = self._respond(activity, branch) if announce else None
        already_said = spoken is not None or not announce

        decision: asyncio.Task[str | None] | None = None
        if gate and self.decide_next is not None and activity is not None:
            decision = asyncio.ensure_future(
                self._decide(activity, outcome, dict(self.last_payload))
            )
        try:
            if hold > 0:
                await asyncio.sleep(hold)
            if decision is not None:
                applied = await decision
                if generation != self._generation or not self.running:
                    # The gate (or anything else) moved the lesson. If it went
                    # somewhere other than where the authored branch was
                    # heading, the line we are part-way through saying is now
                    # about a question the class has left: cut it rather than
                    # let the teacher contradict herself.
                    if not self._agrees_with(branch, applied):
                        self._cancel_speech(spoken)
                    return
                if applied:
                    # It acted but did not move the board -- `say_only`. The
                    # authored branch is *deferred*, not cancelled: a hint the
                    # child does not answer must still land somewhere, or the
                    # lesson stops here forever. What we already said stands;
                    # the model's line follows it, which is the order a
                    # teacher speaks in anyway.
                    self._defer(outcome, generation)
                    return
        except asyncio.CancelledError:
            if decision is not None and not decision.done():
                decision.cancel()
            return
        if generation != self._generation or not self.running:
            self._cancel_speech(spoken)
            return
        await self._apply_outcome(outcome, generation, announced=already_said)

    def _respond(self, activity: Activity | None, branch: Branch | None) -> list[str] | None:
        """Say the authored branch narration immediately. The reflex response.

        Returns the turn ids it started, or ``None`` if there was nothing
        authored to say -- which is also the signal to ``_apply_outcome`` that
        the branch narration has *not* been used up.

        Nothing here waits on anything: with no agent wired this is the same
        narration the lesson always spoke, simply at 3 ms instead of after the
        reveal hold (NS-1 behaviour, sooner).
        """
        if activity is None or branch is None or not branch.narration:
            return None
        return self._speak(branch.narration, f"{activity.id}#{branch.on}")

    def _cancel_speech(self, turn_ids: list[str] | None) -> None:
        """Retire utterances that a later decision has overtaken (§1 `speech.cancel`)."""
        for turn_id in turn_ids or []:
            if self.cancel_speech is not None:
                self.cancel_speech(turn_id)
            else:
                self.bus.publish(
                    "speech.cancel", {"speechTurnId": turn_id, "reason": "superseded"}
                )

    def _agrees_with(self, branch: Branch | None, applied: str | None) -> bool:
        """Did the gate end up where the authored branch was already going?

        If it did, the line the class is hearing is still the right line and
        must not be cut -- and the agent's own action does not re-speak it, so
        nothing is said twice either way.
        """
        if branch is None or not applied:
            return False
        # Asked of the board *after* the move, so it holds for every action the
        # gate has: `goto:x`, `next_activity` and `repeat_activity` all agree
        # exactly when the lesson has landed where the branch was going.
        activity = self.current
        return activity is not None and activity.id == branch.goto

    async def _decide(
        self, activity: Activity, outcome: Outcome, payload: dict[str, Any]
    ) -> str | None:
        """Call the gate. It is advisory, so it is never allowed to raise."""
        assert self.decide_next is not None
        try:
            return await self.decide_next(activity, outcome, payload)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 - a broken gate is just a missing gate
            log.exception("decide_next failed on %s/%s", activity.id, outcome)
            return None

    def _defer(self, outcome: Outcome, generation: int) -> None:
        """Re-arm the authored branch behind a fresh silence window.

        Same generation, so a child who answers in the meantime supersedes it
        the ordinary way.
        """
        # Re-open the question. The one-answer-per-activity guard in
        # `handle_interaction` exists to stop a stray second tap from re-grading
        # a question that is already moving on — but `say_only` is the teacher
        # saying "try once more", which is an explicit invitation to answer
        # again. Leaving `answered` set would make the hint impossible to act
        # on: she asks, the child tries, and nothing happens.
        self.answered = False
        self._timer = asyncio.ensure_future(
            self._run_timer(
                float(self.silence_timeout_s), generation, outcome, gate=False, announce=False
            )
        )

    async def _apply_outcome(
        self, outcome: Outcome, generation: int | None = None, announced: bool = False
    ) -> None:
        """Take the authored branch.

        ``announced`` means ``_respond`` already spoke this branch's narration
        at reflex speed. Saying it again here is the double-speak that the
        immediate response would otherwise introduce.
        """
        if generation is not None and generation != self._generation:
            return
        activity = self.current
        if activity is None:
            return
        self.last_outcome = outcome
        branch = resolve_branch(activity, outcome)
        if branch is None:
            await self._advance_default(announced=announced)
            return
        if not announced:
            self._speak(branch.narration, f"{activity.id}#{branch.on}")
        target = self.index_of(branch.goto)
        if target < 0:
            await self._advance_default(announced=announced)
            return
        await self._enter(target)

    async def _advance_default(self, announced: bool = False) -> None:
        activity = self.current
        if activity is not None:
            for branch in activity.branches or []:
                if branch.on == "always":
                    target = self.index_of(branch.goto)
                    if target >= 0:
                        if not announced:
                            self._speak(branch.narration, f"{activity.id}#always")
                        await self._enter(target)
                        return
                    break
        nxt = self._index + 1
        if nxt >= len(self.activities):
            await self._finish()
            return
        await self._enter(nxt)

    async def _finish(self) -> None:
        self._cancel_timer()
        self._cancel_playback_watchdog()
        self._generation += 1
        self.running = False
        self.finished = True
        self._index = len(self.activities)
        self.store.set_scene("idle", {})
        self.store.update_lesson(
            lesson_id=self.lesson.lesson_id,
            class_id=self.lesson.class_id,
            activity_index=len(self.activities),
            activity_count=len(self.activities),
            stage="DONE",
            activity_id="",
            activity_generation=self._generation,
        )
        self.bus.publish("scene.update", self.store.scene)
        self._publish_position()
        if self.on_finish is not None:
            # Closes the session and queues summarize_session. Off the hot path:
            # the board is already idle by the time this runs.
            result = self.on_finish()
            if asyncio.iscoroutine(result):
                self._spawn(result)

    # ------------------------------------------------------------ controls
    async def control(self, cmd: str, arg: str | None = None) -> dict[str, Any]:
        cmd = (cmd or "").lower()
        if cmd == "pause":
            self.paused = True
            self._generation += 1
            self._cancel_timer()
            self._awaiting_playback_turn = None
            self._pending_playback_turns = []
            self._awaiting_timer = None
            self._cancel_playback_watchdog()
            self._publish_epoch()
        elif cmd == "resume":
            if self.paused:
                self.paused = False
                activity = self.current
                if activity is not None:
                    self._generation += 1
                    self._publish_epoch()
                    self._arm_activity(activity, self._generation)
        elif cmd == "skip":
            self.paused = False
            await self._advance_default()
        elif cmd == "repeat":
            self.paused = False
            if self.current is not None:
                await self._enter(self._index)
        elif cmd == "back":
            self.paused = False
            await self._enter(max(0, self._index - 1))
        elif cmd == "takeover":
            # The facilitator drives; freeze the reflex tier until resume.
            self.paused = True
            self._generation += 1
            self._cancel_timer()
            self._awaiting_playback_turn = None
            self._pending_playback_turns = []
            self._awaiting_timer = None
            self._cancel_playback_watchdog()
            self._publish_epoch()
            self.store.set_overlay(subtitle=None, listening=False)
            self.bus.publish("scene.update", self.store.scene)
        elif cmd == "goto" and arg:
            target = self.index_of(arg)
            if target >= 0:
                await self._enter(target)
        else:
            return {"ok": False, "reason": f"unknown command: {cmd}"}
        return {
            "ok": True,
            "cmd": cmd,
            "index": self._index,
            "paused": self.paused,
            "running": self.running,
        }


def load_lesson_run(path: str) -> LessonRun:
    import json

    with open(path, "r", encoding="utf-8") as handle:
        return LessonRun.model_validate(json.load(handle))


__all__ = [
    "LessonRunner",
    "DecideFn",
    "Outcome",
    "grade",
    "grade_drag",
    "drag_candidates",
    "resolve_branch",
    "normalize_text",
    "stage_for",
    "interaction_kind",
    "load_lesson_run",
]
