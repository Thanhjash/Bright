"""Authoritative autonomous-classroom session coordination.

The runner renders and grades one activity.  This module owns *decisions*:
session/activity/response state, response capabilities, and every transition
between activities.  Keeping that authority here prevents a timer, a control
command and an agent proposal from becoming three independent writers.
"""

from __future__ import annotations

import asyncio
import logging
import hashlib
import re
import secrets
import time
import unicodedata
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any, Literal

log = logging.getLogger("core.class_session")


def _spoken_display_name(value: str) -> str:
    """Return a short TTS-safe roster label without AIRI/control markup."""
    normalized = unicodedata.normalize("NFKC", value)
    normalized = re.sub(r"<\|.*?\|>|<[^>]*>|@[A-Za-z0-9_-]+", " ", normalized)
    safe = "".join(
        char
        for char in normalized
        if char in {" ", "-", "'"}
        or unicodedata.category(char)[0] in {"L", "M", "N"}
    )
    return " ".join(safe.split())[:40].strip() or "Learner"


class SessionState(StrEnum):
    PREPARING = "PREPARING"
    RUNNING = "RUNNING"
    PAUSED = "PAUSED"
    RECOVERING = "RECOVERING"
    CLOSING = "CLOSING"
    COMPLETED = "COMPLETED"
    ABORTED = "ABORTED"


class ActivityState(StrEnum):
    ENTERING = "ENTERING"
    NARRATING = "NARRATING"
    ARMING = "ARMING"
    WAITING = "WAITING"
    RESOLVING = "RESOLVING"
    FEEDBACK = "FEEDBACK"
    DECIDING = "DECIDING"
    TRANSITIONING = "TRANSITIONING"
    CANCELLED = "CANCELLED"


class ResponseState(StrEnum):
    CREATED = "CREATED"
    OPEN = "OPEN"
    CLAIMED = "CLAIMED"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class AgentState(StrEnum):
    IDLE = "IDLE"
    PENDING = "PENDING"
    PROPOSED = "PROPOSED"
    COMMITTED = "COMMITTED"
    DISCARDED = "DISCARDED"
    TIMED_OUT = "TIMED_OUT"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class ParticipationRecord:
    learner_id: str
    display_name: str
    seat: str | None = None
    present: bool = True
    scheduled: int = 0
    attempted: int = 0
    responded: int = 0
    evidenced: int = 0
    skipped: int = 0


@dataclass(frozen=True, slots=True)
class TransitionIntent:
    """A request to move; never a mutation by itself."""

    cause: Literal["start", "outcome", "timer", "control", "agent", "recovery", "finish"]
    from_activity_id: str | None
    activity_generation: int
    target_index: int | None = None
    target_activity_id: str | None = None
    outcome: str | None = None
    decision_revision: int | None = None
    response_turn_id: str | None = None
    announced: bool = False


@dataclass(slots=True)
class ResponseAssignment:
    assignment_id: str
    response_turn_id: str
    capture_id: str | None
    session_id: str
    decision_revision: int
    activity_id: str
    activity_generation: int
    target: str | None
    target_display_name: str | None
    scope: str
    capture_scope: str
    skill_ids: tuple[str, ...]
    evidence_policy: str
    expires_at: float
    ready_deadline_at: int | None = None
    capture_ready: bool = False
    capture_started: bool = False
    # A selected learner is called by Core, never by an agent or browser.  The
    # response capability remains CREATED until this exact physical speech turn
    # has completed successfully.
    callout_speech_turn_id: str | None = None
    state: ResponseState = ResponseState.CREATED
    claimed_outcome: str | None = None

    def public(self) -> dict[str, Any]:
        return {
            "assignmentId": self.assignment_id,
            "responseTurnId": self.response_turn_id,
            "sessionId": self.session_id,
            "decisionRevision": self.decision_revision,
            "activityId": self.activity_id,
            "activityGeneration": self.activity_generation,
            "targetId": self.target,
            "targetDisplayName": self.target_display_name,
            "responseScope": self.scope,
            "captureScope": self.capture_scope,
            "expiresAt": int(
                (time.time() + max(0.0, self.expires_at - time.monotonic())) * 1000
            ),
        }

    def capture_request(self) -> dict[str, Any] | None:
        if self.capture_id is None:
            return None
        return {
            "captureId": self.capture_id,
            "assignmentId": self.assignment_id,
            "responseTurnId": self.response_turn_id,
            "readyDeadlineAt": self.ready_deadline_at,
            "speechOnsetDeadlineMs": 3500,
            "maxDurationMs": 10000,
            "endSilenceMs": 900,
        }


class AssignmentRejected(RuntimeError):
    """A response did not possess the current Core-issued capability."""


@dataclass(slots=True)
class StageLease:
    lease_id: str
    subscriber_id: int
    client_instance_id: str
    connection_epoch: int
    expires_at: float
    capabilities: dict[str, bool | str | int | float]


class CapabilityLeaseRegistry:
    """Server-time capabilities and the single active Stage audio owner."""

    def __init__(self, core: Any, *, ttl_s: float = 15.0) -> None:
        self.core = core
        self.ttl_s = max(2.0, float(ttl_s))
        self.reports: dict[int, StageLease] = {}
        self.stage_owner: StageLease | None = None
        self.control_input_owner: StageLease | None = None

    def report(self, sub: Any, payload: Any) -> StageLease | None:
        self.expire()
        if payload.role != sub.role:
            raise AssignmentRejected("capability role does not match immutable socket role")
        previous = self.reports.get(sub.id)
        if previous is not None and (
            previous.client_instance_id != payload.client_instance_id
            or payload.connection_epoch < previous.connection_epoch
        ):
            raise AssignmentRejected("client instance or connection epoch regressed")
        lease = StageLease(
            lease_id="stage-lease-" + secrets.token_urlsafe(16),
            subscriber_id=sub.id,
            client_instance_id=payload.client_instance_id,
            connection_epoch=payload.connection_epoch,
            expires_at=time.monotonic() + self.ttl_s,
            capabilities=dict(payload.capabilities),
        )
        self.reports[sub.id] = lease
        if sub.role == "control":
            input_ready = bool(
                lease.capabilities.get("audioCapture")
                or lease.capabilities.get("microphone")
                or lease.capabilities.get("audio_input")
            )
            if not input_ready:
                if self.control_input_owner and self.control_input_owner.subscriber_id == sub.id:
                    self.control_input_owner = None
                    self._lost_input_owner("control_audio_input_capability_lost")
                return None
            if self.control_input_owner is None or self.control_input_owner.subscriber_id == sub.id:
                self.control_input_owner = lease
            return None
        if sub.role != "stage":
            return None
        audio_ready = bool(
            lease.capabilities.get("audioPlayback")
            or lease.capabilities.get("speechPlayback")
            or lease.capabilities.get("audio_output")
        )
        if not audio_ready:
            if self.stage_owner and self.stage_owner.subscriber_id == sub.id:
                self.stage_owner = None
                self._lost_owner("stage_audio_capability_lost")
            return None
        if self.stage_owner is None or self.stage_owner.subscriber_id == sub.id:
            self.stage_owner = lease
            return lease
        return None

    def owns_audio(self, sub: Any) -> bool:
        self.expire()
        return self.stage_owner is not None and self.stage_owner.subscriber_id == sub.id

    def owns_input(self, sub: Any) -> bool:
        self.expire()
        return (
            self.control_input_owner is not None
            and self.control_input_owner.subscriber_id == sub.id
        )

    def disconnect(self, sub: Any) -> None:
        self.reports.pop(sub.id, None)
        if self.stage_owner is not None and self.stage_owner.subscriber_id == sub.id:
            self.stage_owner = None
            self._lost_owner("stage_audio_owner_disconnected")
        if self.control_input_owner is not None and self.control_input_owner.subscriber_id == sub.id:
            self.control_input_owner = None
            self._lost_input_owner("control_audio_input_owner_disconnected")

    def expire(self) -> None:
        now = time.monotonic()
        expired = [sub_id for sub_id, lease in self.reports.items() if lease.expires_at <= now]
        owner_expired = self.stage_owner is not None and self.stage_owner.expires_at <= now
        input_expired = (
            self.control_input_owner is not None
            and self.control_input_owner.expires_at <= now
        )
        for sub_id in expired:
            self.reports.pop(sub_id, None)
        if owner_expired:
            self.stage_owner = None
            self._lost_owner("stage_audio_lease_expired")
        if input_expired:
            self.control_input_owner = None
            self._lost_input_owner("control_audio_input_lease_expired")

    def _lost_owner(self, reason: str) -> None:
        runner = getattr(self.core, "runner", None)
        controller = getattr(self.core, "session_controller", None)
        if (
            runner is not None
            and controller is not None
            and (runner._pending_playback_turns or controller._callout_assignment_id)
        ):
            controller.session_state = SessionState.RECOVERING
            controller.publish_status(reason)
            controller.safe_pause(reason)

    def _lost_input_owner(self, reason: str) -> None:
        runner = getattr(self.core, "runner", None)
        controller = getattr(self.core, "session_controller", None)
        if runner is None or controller is None:
            return
        assignment = controller.assignments.current_for_activity(
            str(getattr(self.core, "session_id", None) or "unsessioned"),
            getattr(runner.current, "id", ""),
            runner._generation,
        )
        if assignment is not None and assignment.capture_id is not None:
            controller.session_state = SessionState.RECOVERING
            controller.publish_status(reason)
            controller.safe_pause(reason)


class ResponseAssignmentRegistry:
    """Exactly-once, short-lived response capabilities.

    The learner target is chosen by Core.  No method accepts ``studentId``;
    client-supplied identity therefore cannot become attribution by accident.
    """

    def __init__(self, *, default_ttl_s: float = 30.0) -> None:
        self.default_ttl_s = max(0.1, float(default_ttl_s))
        self._assignments: dict[str, ResponseAssignment] = {}
        self._response_turns: dict[str, str] = {}
        self._capture_ids: dict[str, str] = {}
        self._lock = asyncio.Lock()

    def issue(
        self,
        *,
        session_id: str,
        decision_revision: int,
        activity_id: str,
        activity_generation: int,
        target: str | None,
        target_display_name: str | None = None,
        scope: str,
        skill_ids: tuple[str, ...] = (),
        evidence_policy: str = "none",
        capture_scope: str = "none",
        capture: bool = False,
        ttl_s: float | None = None,
        ready_timeout_s: float = 20.0,
    ) -> ResponseAssignment:
        assignment_id = "assignment-" + secrets.token_urlsafe(18)
        response_turn_id = "response-" + secrets.token_urlsafe(18)
        capture_id = "capture-" + secrets.token_urlsafe(18) if capture else None
        assignment = ResponseAssignment(
            assignment_id=assignment_id,
            response_turn_id=response_turn_id,
            capture_id=capture_id,
            session_id=session_id,
            decision_revision=decision_revision,
            activity_id=activity_id,
            activity_generation=activity_generation,
            target=target,
            target_display_name=target_display_name,
            scope=scope,
            capture_scope=capture_scope,
            skill_ids=tuple(skill_ids),
            evidence_policy=evidence_policy,
            expires_at=time.monotonic() + (ttl_s or self.default_ttl_s),
            ready_deadline_at=(
                int(time.time() * 1000) + int(max(0.1, ready_timeout_s) * 1000)
                if capture
                else None
            ),
        )
        self._assignments[assignment_id] = assignment
        self._response_turns[response_turn_id] = assignment_id
        if capture_id:
            self._capture_ids[capture_id] = assignment_id
        self.prune()
        return assignment

    def arm_capture(
        self,
        assignment_id: str,
        *,
        ttl_s: float | None = None,
        ready_timeout_s: float = 20.0,
    ) -> ResponseAssignment:
        """Mint the physical-mic capability only once its callout is audible.

        A selected learner must not lose setup time while Piper/AIRI is still
        queuing the callout.  The assignment identity remains stable, but the
        opaque capture id, response expiry and Ready deadline begin here.
        """
        assignment = self._resolve(assignment_id)
        if assignment.state != ResponseState.CREATED:
            raise AssignmentRejected(f"assignment is {assignment.state.lower()}")
        if assignment.capture_id is None:
            assignment.capture_id = "capture-" + secrets.token_urlsafe(18)
            self._capture_ids[assignment.capture_id] = assignment_id
        assignment.expires_at = time.monotonic() + (ttl_s or self.default_ttl_s)
        assignment.ready_deadline_at = int(time.time() * 1000) + int(
            max(0.1, ready_timeout_s) * 1000
        )
        assignment.capture_ready = False
        assignment.capture_started = False
        return assignment

    def open(self, assignment_id: str) -> ResponseAssignment:
        assignment = self._resolve(assignment_id)
        if assignment.state == ResponseState.CREATED:
            assignment.state = ResponseState.OPEN
        elif assignment.state != ResponseState.OPEN:
            raise AssignmentRejected(f"assignment is {assignment.state.lower()}")
        return assignment

    def get(self, assignment_id: str) -> ResponseAssignment | None:
        self.prune()
        return self._assignments.get(assignment_id)

    def current_for_activity(
        self, session_id: str, activity_id: str, activity_generation: int
    ) -> ResponseAssignment | None:
        self.prune()
        for assignment in reversed(tuple(self._assignments.values())):
            if (
                assignment.session_id == session_id
                and assignment.activity_id == activity_id
                and assignment.activity_generation == activity_generation
                and assignment.state in {ResponseState.CREATED, ResponseState.OPEN}
            ):
                return assignment
        return None

    async def claim(
        self,
        *,
        assignment_id: str,
        response_turn_id: str,
        session_id: str,
        decision_revision: int,
        activity_id: str,
        activity_generation: int,
        capture_id: str | None = None,
        outcome: str | None = None,
    ) -> ResponseAssignment:
        async with self._lock:
            assignment = self._resolve(assignment_id)
            expected = (
                assignment.response_turn_id,
                assignment.session_id,
                assignment.decision_revision,
                assignment.activity_id,
                assignment.activity_generation,
            )
            supplied = (
                response_turn_id,
                session_id,
                decision_revision,
                activity_id,
                activity_generation,
            )
            if supplied != expected:
                raise AssignmentRejected("response capability scope is stale or mismatched")
            if assignment.capture_id is not None and capture_id != assignment.capture_id:
                raise AssignmentRejected("captureId does not match assignment")
            if assignment.state == ResponseState.CLAIMED:
                raise AssignmentRejected("response turn already claimed")
            if assignment.state != ResponseState.OPEN:
                raise AssignmentRejected(f"assignment is {assignment.state.lower()}")
            assignment.state = ResponseState.CLAIMED
            assignment.claimed_outcome = outcome
            return assignment

    def close(self, assignment_id: str, *, outcome: str | None = None) -> None:
        assignment = self._resolve(assignment_id)
        if assignment.state not in {ResponseState.CLAIMED, ResponseState.OPEN}:
            raise AssignmentRejected(f"assignment is {assignment.state.lower()}")
        assignment.state = ResponseState.CLOSED
        assignment.claimed_outcome = outcome or assignment.claimed_outcome

    def cancel_open(self, *, reason: str = "superseded") -> None:
        del reason  # retained for call-site diagnostics/future persistence
        for assignment in self._assignments.values():
            if assignment.state in {ResponseState.CREATED, ResponseState.OPEN}:
                assignment.state = ResponseState.CANCELLED

    def prune(self) -> None:
        now = time.monotonic()
        for assignment in self._assignments.values():
            if assignment.expires_at <= now and assignment.state in {
                ResponseState.CREATED,
                ResponseState.OPEN,
            }:
                assignment.state = ResponseState.EXPIRED

    def _resolve(self, assignment_id: str) -> ResponseAssignment:
        self.prune()
        assignment = self._assignments.get(assignment_id)
        if assignment is None:
            raise AssignmentRejected("unknown assignmentId")
        return assignment


@dataclass(slots=True)
class ClassSessionController:
    """Serializes all autonomous-classroom state transitions."""

    core: Any
    runner: Any
    assignments: ResponseAssignmentRegistry = field(default_factory=ResponseAssignmentRegistry)
    session_state: SessionState = SessionState.PREPARING
    activity_state: ActivityState = ActivityState.ENTERING
    response_state: ResponseState = ResponseState.CREATED
    agent_state: AgentState = AgentState.IDLE
    pause_reason: str | None = None
    started_at_ms: int | None = None
    roster: dict[str, ParticipationRecord] = field(default_factory=dict)
    attendance: tuple[str, ...] = ()
    target_history: list[str] = field(default_factory=list)
    named_turns_used: int = 0
    named_turn_budget: int = 8
    fairness_cooldown: int = 3
    capture_ready_timeout_s: float = 20.0
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    _capture_watchdog: asyncio.Task[None] | None = None
    _capture_watchdog_id: str | None = None
    _callout_watchdog: asyncio.Task[None] | None = None
    _callout_assignment_id: str | None = None
    _retry_target: str | None = None
    _retry_activity_id: str | None = None
    _closure_deadline_mono: float | None = None
    _closure_task: asyncio.Task[None] | None = None

    def __post_init__(self) -> None:
        self.runner.session_controller = self
        self.runner.transition_sink = self.commit_transition
        self.runner.on_response_window = self.open_response_window
        self.runner.on_activity_state = self.note_activity_state
        plan = getattr(getattr(self.core, "lesson", None), "session_plan", None)
        if plan is not None:
            self.named_turn_budget = int(getattr(plan, "named_turn_budget", 8))
            self.fairness_cooldown = int(getattr(plan, "fairness_cooldown", 3))

    def configure_roster(
        self,
        roster: list[Any],
        attendance_ids: list[str] | None,
    ) -> None:
        """Validate and persist one real classroom roster (1..40 learners)."""
        if not 1 <= len(roster) <= 40:
            raise ValueError("autonomous classroom requires 1..40 roster learners")
        records: dict[str, ParticipationRecord] = {}
        for item in roster:
            learner_id = str(getattr(item, "id", None) or item.get("id"))
            name = str(
                getattr(item, "display_name", None)
                or item.get("displayName")
                or item.get("display_name")
            )
            seat = getattr(item, "seat", None) if not isinstance(item, dict) else item.get("seat")
            if not learner_id or learner_id in records:
                raise ValueError("roster learner ids must be non-empty and unique")
            records[learner_id] = ParticipationRecord(learner_id, name, seat)
        attendance = list(attendance_ids) if attendance_ids is not None else list(records)
        if not attendance or len(attendance) > 40 or len(set(attendance)) != len(attendance):
            raise ValueError("attendanceIds must contain 1..40 unique learners")
        unknown = sorted(set(attendance) - set(records))
        if unknown:
            raise ValueError("attendanceIds not in roster: " + ", ".join(unknown))
        present = set(attendance)
        for learner_id, record in records.items():
            record.present = learner_id in present
        self.roster = records
        self.attendance = tuple(attendance)
        self.target_history.clear()
        self.named_turns_used = 0
        self._persist_roster()

    def _next_fair_target(self) -> str | None:
        if self.named_turns_used >= self.named_turn_budget or not self.attendance:
            return None
        recent = set(self.target_history[-self.fairness_cooldown :])
        candidates = [self.roster[learner_id] for learner_id in self.attendance]
        eligible = [record for record in candidates if record.learner_id not in recent] or candidates
        session_key = str(getattr(self.core, "session_id", None) or "unsessioned")
        chosen = min(
            eligible,
            key=lambda record: (
                record.scheduled,
                hashlib.sha256(
                    f"{session_key}:{record.learner_id}".encode("utf-8")
                ).hexdigest(),
            ),
        )
        chosen.scheduled += 1
        self.named_turns_used += 1
        self.target_history.append(chosen.learner_id)
        self._persist_participation(chosen, "scheduled")
        return chosen.learner_id

    @property
    def decision_revision(self) -> int:
        return int(self.core.store.decision_revision)

    async def start(self, index: int = 0) -> Any:
        self.session_state = SessionState.PREPARING
        self.started_at_ms = int(time.time() * 1000)
        plan = getattr(getattr(self.core, "lesson", None), "session_plan", None)
        if plan is not None:
            teaching_s = max(
                1.0,
                float(plan.duration_min * 60 - plan.closure_reserve_s),
            )
            self._closure_deadline_mono = time.monotonic() + teaching_s
            self._schedule_closure_deadline(teaching_s)
        # Controller.start bypasses LessonRunner.start by design, so it must
        # initialize the lifecycle flags before commit_enter tries to arm
        # playback/capture.  A false ``running`` flag rejects every physical
        # playback ACK and leaves the class permanently stalled.
        self.runner.running = True
        self.runner.finished = False
        self.runner.paused = False
        result = await self.commit_transition(
            TransitionIntent(
                cause="start",
                from_activity_id=None,
                activity_generation=self.runner._generation,
                target_index=index,
            )
        )
        if result is not None:
            self.session_state = SessionState.RUNNING
            self.publish_status("lesson_started")
        return result

    async def commit_transition(self, intent: TransitionIntent) -> Any:
        """Validate then commit exactly one transition under one decision lock."""
        async with self._lock:
            if intent.decision_revision is not None and intent.decision_revision != self.decision_revision:
                return None
            current = self.runner.current
            current_id = getattr(current, "id", None)
            if intent.from_activity_id is not None and current_id != intent.from_activity_id:
                return None
            if intent.cause not in {"start", "control", "agent"} and (
                intent.activity_generation != self.runner._generation
            ):
                return None

            self._cancel_capture_watchdog()
            self._cancel_callout_watchdog()
            self._retry_target = None
            self._retry_activity_id = None
            self.assignments.cancel_open(reason="transition")
            self.response_state = ResponseState.CANCELLED
            self.activity_state = ActivityState.TRANSITIONING
            self.core.store.advance_decision_revision()

            target = intent.target_index
            if target is None and intent.target_activity_id:
                target = self.runner.index_of(intent.target_activity_id)
            if target is None:
                target = self.runner.resolve_intent_target(intent)

            closure_index = self._closure_index()
            if (
                closure_index is not None
                and target != closure_index
                and self.runner.index != closure_index
                and intent.cause != "control"
                and self._closure_deadline_mono is not None
                and time.monotonic() >= self._closure_deadline_mono
            ):
                target = closure_index

            if target is None or target < 0 or target >= len(self.runner.activities):
                self.session_state = SessionState.CLOSING
                result = await self.runner.commit_finish()
                self.session_state = SessionState.COMPLETED
                self.activity_state = ActivityState.CANCELLED
                self.cancel_session_clock()
                self.publish_status("lesson_completed")
                return result

            result = await self.runner.commit_enter(target)
            self.activity_state = (
                ActivityState.NARRATING
                if self.runner._pending_playback_turns
                else ActivityState.WAITING
            )
            self.publish_update(intent.cause)
            self._checkpoint()
            return result

    def _closure_index(self) -> int | None:
        matches = [
            index
            for index, activity in enumerate(self.runner.activities)
            if getattr(getattr(activity, "teaching", None), "stage", None) == "CLOSURE"
        ]
        return matches[0] if len(matches) == 1 else None

    def _schedule_closure_deadline(self, delay_s: float) -> None:
        self.cancel_session_clock()
        self._closure_task = asyncio.ensure_future(self._force_closure_after(delay_s))

    async def _force_closure_after(self, delay_s: float) -> None:
        try:
            await asyncio.sleep(max(0.001, delay_s))
        except asyncio.CancelledError:
            return
        self._closure_task = None
        closure_index = self._closure_index()
        current = self.runner.current
        if (
            closure_index is None
            or self.session_state != SessionState.RUNNING
            or current is None
            or self.runner.index == closure_index
        ):
            return
        await self.commit_transition(
            TransitionIntent(
                cause="timer",
                from_activity_id=current.id,
                activity_generation=self.runner._generation,
                target_index=closure_index,
                decision_revision=self.decision_revision,
            )
        )

    def cancel_session_clock(self) -> None:
        task = self._closure_task
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
        self._closure_task = None

    def note_activity_state(self, state: str) -> None:
        try:
            self.activity_state = ActivityState(state)
        except ValueError:
            return
        self.publish_update("activity_state")

    def open_response_window(self, activity: Any, generation: int) -> ResponseAssignment | None:
        expect = getattr(activity, "expect", None)
        if expect is None or getattr(expect, "kind", "none") == "none":
            return None
        teaching = getattr(activity, "teaching", None)
        scope = str(getattr(teaching, "response_scope", None) or "selected_individual")
        participation = str(
            getattr(teaching, "participation_mode", None) or "selected_individual"
        )
        target = None
        if scope == "selected_individual" and participation == "selected_individual":
            if self._retry_activity_id == activity.id and self._retry_target in self.roster:
                target = self._retry_target
                self._retry_target = None
                self._retry_activity_id = None
            else:
                target = self._next_fair_target() if self.roster else getattr(self.core, "student_id", None)
            if target is None:
                scope = "uncertain"
        target_display_name = (
            self.roster[target].display_name
            if target is not None and target in self.roster
            else None
        )
        skill_ids = tuple(getattr(teaching, "skill_ids", None) or ())
        evidence_policy = str(getattr(teaching, "evidence_policy", None) or "none")
        capture = getattr(expect, "kind", None) == "speech"
        capture_scope = "answer_station" if capture else "board"
        assignment = self.assignments.issue(
            session_id=str(getattr(self.core, "session_id", None) or "unsessioned"),
            decision_revision=self.decision_revision,
            activity_id=activity.id,
            activity_generation=generation,
            target=target,
            target_display_name=target_display_name,
            scope=scope,
            skill_ids=skill_ids,
            evidence_policy=evidence_policy,
            capture_scope=capture_scope,
            # Named speech uses a two-phase capability.  Its physical capture
            # token and timer are minted after exact callout playback, so TTS
            # queueing cannot consume the learner's Ready window.
            capture=capture and not (target is not None and target_display_name is not None),
            ttl_s=max(float(getattr(self.runner, "playback_ack_timeout_s", 10.0)) + 1.0, 2.0)
            if capture and target is not None and target_display_name is not None
            else max(float(getattr(self.runner, "silence_timeout_s", 15.0)) + 5.0, 10.0),
            ready_timeout_s=self.capture_ready_timeout_s,
        )
        self.core.store.update_lesson(
            decision_revision=self.decision_revision,
            response_turn_id=assignment.response_turn_id,
            assignment_id=assignment.assignment_id,
            current_student_id=assignment.target,
        )
        self.runner._publish_position()
        payload = assignment.public()
        self.core.bus.publish("class.turn.assigned", payload)
        # A named oral response is a two-step physical protocol.  Fairness
        # selects the child first, then Core speaks a fixed pseudonymous
        # callout.  The mic is deliberately not requested until Stage proves
        # that *this* callout completed.  Hermes cannot bypass this gate.
        if capture and target is not None and target_display_name:
            spoken_name = _spoken_display_name(target_display_name)
            assignment.callout_speech_turn_id = self.core.publish_speech(
                f"{spoken_name}, it's your turn. Please answer now.",
                source="core",
                behavior="queue",
                activity_id=activity.id,
                activity_generation=generation,
            )
            self.response_state = ResponseState.CREATED
            self.activity_state = ActivityState.NARRATING
            self._watch_callout_playback(assignment)
            self.publish_update("callout_pending")
            return assignment

        self.assignments.open(assignment.assignment_id)
        self.response_state = ResponseState.OPEN
        if capture:
            self.core.bus.publish("response.capture.requested", assignment.capture_request())
            self._watch_capture_start(assignment)
            # The response capability is open, but physical capture is not.
            # Stage must explicitly prove readiness/start before Core arms VAD.
            self.activity_state = ActivityState.ARMING
        return assignment

    def note_callout_playback_finished(self, speech_turn_id: str) -> bool:
        """Open a selected oral turn only after its exact callout is audible.

        The caller has already validated the Stage playback state machine.  We
        still validate assignment/session/activity scope here because an old
        ACK must never arm a newer learner's microphone.
        """
        assignment = self._pending_callout(speech_turn_id)
        if assignment is None:
            return False
        if (
            self.session_state != SessionState.RUNNING
            or self.runner.current is None
            or self.runner.current.id != assignment.activity_id
            or self.runner._generation != assignment.activity_generation
            or not self.runner.running
            or self.runner.paused
        ):
            return False
        self._cancel_callout_watchdog(assignment.assignment_id)
        if assignment.capture_scope == "answer_station":
            assignment = self.assignments.arm_capture(
                assignment.assignment_id,
                ttl_s=max(float(getattr(self.runner, "silence_timeout_s", 15.0)) + 5.0, 10.0),
                ready_timeout_s=self.capture_ready_timeout_s,
            )
        self.assignments.open(assignment.assignment_id)
        self.response_state = ResponseState.OPEN
        # Refresh the browser-visible capability before capture.requested.
        # Control correctly rejects expired assignments; without this update it
        # would still see the short pre-callout expiry even though Core minted a
        # fresh physical window above.
        self.core.bus.publish("class.turn.assigned", assignment.public())
        request = assignment.capture_request()
        if request is not None:
            self.core.bus.publish("response.capture.requested", request)
            self._watch_capture_start(assignment)
        self.activity_state = ActivityState.ARMING
        self.publish_update("callout_completed")
        return True

    def note_callout_playback_failed(self, speech_turn_id: str, status: str) -> bool:
        """Fail closed if a selected learner did not hear their callout."""
        assignment = self._pending_callout(speech_turn_id)
        if assignment is None:
            return False
        self._cancel_callout_watchdog(assignment.assignment_id)
        self.safe_pause(f"callout_playback_{status}")
        return True

    def _pending_callout(self, speech_turn_id: str) -> ResponseAssignment | None:
        assignment_id = self._callout_assignment_id
        if assignment_id is None:
            return None
        assignment = self.assignments.get(assignment_id)
        if (
            assignment is None
            or assignment.state != ResponseState.CREATED
            or assignment.callout_speech_turn_id != speech_turn_id
        ):
            return None
        return assignment

    def _watch_callout_playback(self, assignment: ResponseAssignment) -> None:
        self._cancel_callout_watchdog()
        if assignment.callout_speech_turn_id is None:
            return
        self._callout_assignment_id = assignment.assignment_id
        self._callout_watchdog = asyncio.ensure_future(
            self._callout_playback_deadline(
                assignment.assignment_id, assignment.callout_speech_turn_id
            )
        )

    def _cancel_callout_watchdog(self, assignment_id: str | None = None) -> None:
        if assignment_id is not None and assignment_id != self._callout_assignment_id:
            return
        task = self._callout_watchdog
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
        self._callout_watchdog = None
        self._callout_assignment_id = None

    async def _callout_playback_deadline(
        self, assignment_id: str, speech_turn_id: str
    ) -> None:
        try:
            await asyncio.sleep(max(0.001, float(self.runner.playback_ack_timeout_s)))
        except asyncio.CancelledError:
            return
        assignment = self.assignments.get(assignment_id)
        if (
            assignment is not None
            and assignment.state == ResponseState.CREATED
            and assignment.callout_speech_turn_id == speech_turn_id
        ):
            self._callout_watchdog = None
            self._callout_assignment_id = None
            self.safe_pause("callout_playback_ack_timeout")

    def note_capture_ready(self, payload: dict[str, Any]) -> ResponseAssignment:
        assignment = self._capture_assignment(payload)
        if (
            assignment.ready_deadline_at is None
            or int(time.time() * 1000) > assignment.ready_deadline_at
        ):
            self.safe_pause("capture_ready_deadline_expired")
            raise AssignmentRejected("capture ready deadline expired")
        if payload.get("status") != "ready":
            self.safe_pause(str(payload.get("reason") or "capture_not_ready"))
            raise AssignmentRejected("capture endpoint reported not ready")
        assignment.capture_ready = True
        return assignment

    def note_capture_started(self, payload: dict[str, Any]) -> ResponseAssignment:
        assignment = self._capture_assignment(payload)
        if not assignment.capture_ready:
            raise AssignmentRejected("capture must be ready before started")
        if assignment.capture_started:
            return assignment
        assignment.capture_started = True
        self._cancel_capture_watchdog(assignment.capture_id)
        self.runner.arm_capture(assignment.activity_id, assignment.activity_generation)
        self.activity_state = ActivityState.WAITING
        return assignment

    def _capture_assignment(self, payload: dict[str, Any]) -> ResponseAssignment:
        assignment = self.assignments.get(str(payload.get("assignmentId") or ""))
        if assignment is None:
            raise AssignmentRejected("unknown assignmentId")
        if (
            assignment.response_turn_id != str(payload.get("responseTurnId") or "")
            or assignment.capture_id != str(payload.get("captureId") or "")
            or assignment.state != ResponseState.OPEN
        ):
            raise AssignmentRejected("capture capability is stale or mismatched")
        return assignment

    async def claim_response(self, payload: dict[str, Any]) -> ResponseAssignment:
        current = self.runner.current
        if current is None:
            raise AssignmentRejected("no active activity")
        pending = self.assignments.get(str(payload.get("assignmentId") or ""))
        if pending is not None and pending.capture_id is not None and not pending.capture_started:
            raise AssignmentRejected("capture has not started")
        assignment = await self.assignments.claim(
            assignment_id=str(payload.get("assignmentId") or ""),
            response_turn_id=str(payload.get("responseTurnId") or ""),
            capture_id=str(payload.get("captureId")) if payload.get("captureId") else None,
            session_id=str(getattr(self.core, "session_id", None) or "unsessioned"),
            decision_revision=self.decision_revision,
            activity_id=current.id,
            activity_generation=self.runner._generation,
        )
        self.response_state = ResponseState.CLAIMED
        self.activity_state = ActivityState.RESOLVING
        if assignment.target and assignment.target in self.roster:
            record = self.roster[assignment.target]
            record.attempted += 1
            self._persist_participation(record, "attempted")
        return assignment

    def close_response(self, assignment: ResponseAssignment, outcome: str) -> None:
        self._cancel_capture_watchdog(assignment.capture_id)
        self.assignments.close(assignment.assignment_id, outcome=outcome)
        self.response_state = ResponseState.CLOSED
        self.activity_state = ActivityState.FEEDBACK
        if assignment.target and assignment.target in self.roster:
            record = self.roster[assignment.target]
            record.responded += 1
            if outcome in {"correct", "near", "wrong"} and assignment.evidence_policy == "individual":
                record.evidenced += 1
            elif outcome in {"silence", "timeout"}:
                record.skipped += 1
            self._persist_participation(record, "closed")
        self.core.bus.publish(
            "class.turn.closed",
            {
                "assignmentId": assignment.assignment_id,
                "responseTurnId": assignment.response_turn_id,
                "outcome": outcome,
            },
        )

    def safe_pause(self, reason: str) -> None:
        current = self.runner.current
        pending = (
            self.assignments.current_for_activity(
                str(getattr(self.core, "session_id", None) or "unsessioned"),
                getattr(current, "id", ""),
                self.runner._generation,
            )
            if current is not None
            else None
        )
        # A failed callout is not a completed turn.  Keep the Core-selected
        # target across pause/resume, without incrementing the fairness budget
        # or pretending that a child was called when they were not.
        if pending is not None and pending.target and pending.state == ResponseState.CREATED:
            self._retry_target = pending.target
            self._retry_activity_id = pending.activity_id
        self._cancel_capture_watchdog()
        self._cancel_callout_watchdog()
        self.session_state = SessionState.PAUSED
        self.pause_reason = reason
        self.activity_state = ActivityState.CANCELLED
        self.response_state = ResponseState.CANCELLED
        self.assignments.cancel_open(reason=reason)
        self.runner.pause_current(takeover=reason == "facilitator_takeover")
        self.publish_status(reason)
        self.publish_update("safe_pause")
        self._checkpoint()

    async def control(self, cmd: str, arg: str | None = None) -> dict[str, Any]:
        """Apply facilitator control while keeping session state authoritative."""
        cmd = (cmd or "").lower()
        if cmd == "pause":
            self.safe_pause("facilitator_pause")
        elif cmd == "takeover":
            self.safe_pause("facilitator_takeover")
        elif cmd == "resume":
            if self.session_state != SessionState.PAUSED:
                return {"ok": False, "reason": "session is not paused"}
            self.pause_reason = None
            self.session_state = SessionState.RUNNING
            result = await self.runner.control("resume", arg)
            self.publish_status("facilitator_resumed")
            self.publish_update("resume")
            self._checkpoint()
            return result
        elif cmd in {"skip", "repeat", "back", "goto"}:
            result = await self.runner.control(cmd, arg)
            if result.get("ok"):
                self.pause_reason = None
                if self.runner.finished:
                    self.session_state = SessionState.COMPLETED
                else:
                    self.session_state = SessionState.RUNNING
                self.publish_status(f"facilitator_{cmd}")
                self.publish_update(cmd)
                self._checkpoint()
            return result
        else:
            return {"ok": False, "reason": f"unknown command: {cmd}"}
        return {
            "ok": True,
            "cmd": cmd,
            "index": self.runner.index,
            "paused": self.runner.paused,
            "running": self.runner.running,
        }

    def begin_recovery(self, reason: str) -> None:
        self.session_state = SessionState.RECOVERING
        self.pause_reason = reason
        self.publish_status(reason)
        self.publish_update("recovery")

    def _watch_capture_start(self, assignment: ResponseAssignment) -> None:
        self._cancel_capture_watchdog()
        if assignment.capture_id is None:
            return
        self._capture_watchdog_id = assignment.capture_id
        self._capture_watchdog = asyncio.ensure_future(
            self._capture_start_deadline(assignment.assignment_id, assignment.capture_id)
        )

    def _cancel_capture_watchdog(self, capture_id: str | None = None) -> None:
        if capture_id is not None and capture_id != self._capture_watchdog_id:
            return
        task = self._capture_watchdog
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
        self._capture_watchdog = None
        self._capture_watchdog_id = None

    async def _capture_start_deadline(self, assignment_id: str, capture_id: str) -> None:
        try:
            await asyncio.sleep(max(0.001, self.capture_ready_timeout_s))
        except asyncio.CancelledError:
            return
        assignment = self.assignments.get(assignment_id)
        self._capture_watchdog = None
        self._capture_watchdog_id = None
        if (
            assignment is not None
            and assignment.capture_id == capture_id
            and assignment.state == ResponseState.OPEN
            and not assignment.capture_started
        ):
            self.safe_pause("capture_start_deadline_expired")

    def publish_update(self, reason: str) -> None:
        del reason
        self.core.bus.publish("class.session.updated", self.session_payload())

    def publish_status(self, reason: str) -> None:
        payload: dict[str, Any] = {
                "liveness": "live",
                "readiness": (
                    "ready" if self.session_state == SessionState.RUNNING else "degraded"
                ),
                "teachable": self.session_state == SessionState.RUNNING,
                "lessonId": getattr(getattr(self.core, "lesson", None), "lesson_id", None),
                "reason": reason,
            }
        if self.session_state in {SessionState.PAUSED, SessionState.RECOVERING}:
            payload["recovery"] = {
                "reason": reason,
                "requiredAction": "resume_or_takeover",
            }
        self.core.bus.publish("classroom.status", payload)

    def session_payload(self) -> dict[str, Any]:
        assignment = self.assignments.current_for_activity(
            str(getattr(self.core, "session_id", None) or "unsessioned"),
            getattr(self.runner.current, "id", ""),
            self.runner._generation,
        )
        elapsed_s = (
            max(0, (int(time.time() * 1000) - self.started_at_ms) // 1000)
            if self.started_at_ms is not None
            else 0
        )
        return {
            "sessionId": str(getattr(self.core, "session_id", None) or "unsessioned"),
            "status": str(self.session_state),
            "decisionRevision": self.decision_revision,
            "startedAt": self.started_at_ms,
            "elapsedS": elapsed_s,
            "stage": str(getattr(self.core.store.lesson, "stage", "IDLE")),
            "currentTargetId": assignment.target if assignment else None,
            "responseTurnId": assignment.response_turn_id if assignment else None,
            "pauseReason": self.pause_reason,
            "resumeAllowed": self.session_state == SessionState.PAUSED,
            "requiredAction": "resume_or_takeover"
            if self.session_state == SessionState.PAUSED
            else None,
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "sessionId": getattr(self.core, "session_id", None),
            "sessionState": self.session_state,
            "activityState": self.activity_state,
            "responseState": self.response_state,
            "agentState": self.agent_state,
            "decisionRevision": self.decision_revision,
            "activityGeneration": self.runner._generation,
            "pauseReason": self.pause_reason,
            "attendanceCount": len(self.attendance),
            "namedTurnsUsed": self.named_turns_used,
            "participation": {
                learner_id: {
                    "scheduled": record.scheduled,
                    "attempted": record.attempted,
                    "responded": record.responded,
                    "evidenced": record.evidenced,
                    "skipped": record.skipped,
                }
                for learner_id, record in self.roster.items()
                if record.present
            },
        }

    def _persist_roster(self) -> None:
        session_id = getattr(self.core, "session_id", None)
        if not session_id:
            return
        try:
            self.core.db.replace_session_participants(
                session_id,
                [
                    {
                        "learner_id": record.learner_id,
                        "display_name": record.display_name,
                        "seat": record.seat,
                        "present": record.present,
                    }
                    for record in self.roster.values()
                ],
            )
        except Exception:
            log.exception("could not persist session roster")

    def _persist_participation(self, record: ParticipationRecord, event: str) -> None:
        session_id = getattr(self.core, "session_id", None)
        if not session_id:
            return
        try:
            self.core.db.update_session_participation(
                session_id=session_id,
                learner_id=record.learner_id,
                scheduled=record.scheduled,
                attempted=record.attempted,
                responded=record.responded,
                evidenced=record.evidenced,
                skipped=record.skipped,
                event=event,
            )
        except Exception:
            log.exception("could not persist participation ledger")

    def _checkpoint(self) -> None:
        session_id = getattr(self.core, "session_id", None)
        if not session_id:
            return
        try:
            self.core.db.save_session_checkpoint(
                session_id=session_id,
                decision_revision=self.decision_revision,
                activity_id=getattr(self.runner.current, "id", None),
                activity_generation=self.runner._generation,
                session_state=str(self.session_state),
                snapshot=self.snapshot(),
            )
        except Exception:  # a storage fault must not invent or stop instruction
            log.exception("session checkpoint failed")
            self.core.bus.publish(
                "classroom.status",
                {
                    "liveness": "live",
                    "readiness": "degraded",
                    "teachable": self.session_state == SessionState.RUNNING,
                    "lessonId": getattr(
                        getattr(self.core, "lesson", None), "lesson_id", None
                    ),
                    "reason": "storage_degraded",
                    "recovery": {"reason": "storage_degraded"},
                },
            )


__all__ = [
    "ActivityState",
    "AgentState",
    "AssignmentRejected",
    "CapabilityLeaseRegistry",
    "ClassSessionController",
    "ResponseAssignment",
    "ResponseAssignmentRegistry",
    "ResponseState",
    "SessionState",
    "TransitionIntent",
]
