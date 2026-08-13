"""Bright wire contracts. Mirror of PROTOCOL.md.

TypeScript mirror: packages/contracts/src/index.ts
Change PROTOCOL.md first, then both mirrors.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field, model_validator

PROTOCOL_VERSION = 3

# --------------------------------------------------------------- envelope

EventType = Literal[
    # server -> client
    "scene.update",
    "scene.snapshot",
    "class.session.updated",
    "class.turn.assigned",
    "class.turn.closed",
    "response.capture.requested",
    "classroom.status",
    "stage.lease.granted",
    "speech.say",
    "speech.turn.started",
    "speech.text.delta",
    "speech.turn.ended",
    "speech.cancel",
    "speech.barge_in.ack",
    "speech.playback.observed",
    "avatar.act",
    "lesson.position",
    "lesson.started",
    "student.response.accepted",
    "mode.changed",
    "error",
    # §9.8 liveness: consumes no seq, never bumps state_version
    "heartbeat",
    # client -> server
    "client.hello",
    "interaction.choice",
    "interaction.point",
    "interaction.drag",
    "control.command",
    "lesson.start",
    "student.speech.final",
    "speech.playback.started",
    "speech.playback.finished",
    "speech.barge_in",
    "heartbeat.ack",
    "capability.report",
    "response.capture.ready",
    "response.capture.started",
]

Mode = Literal["FULL", "DEGRADED", "OFFLINE"]


class Event(BaseModel):
    v: Literal[3] = PROTOCOL_VERSION
    type: EventType
    seq: int
    state_version: int = Field(serialization_alias="stateVersion", validation_alias="stateVersion")
    ts: int
    payload: Any = None

    model_config = {"populate_by_name": True}


class SpeechSayPayload(BaseModel):
    """Legacy complete-speech event retained for compatibility only."""

    text: str
    audio_asset: str | None = Field(default=None, alias="audioAsset")
    turn_id: str = Field(alias="turnId")
    conversation_id: str | None = Field(default=None, alias="conversationId")
    reply_to_utterance_id: str | None = Field(default=None, alias="replyToUtteranceId")

    model_config = {"populate_by_name": True}


class ModeChangedPayload(BaseModel):
    mode: Mode
    reason: str


class ErrorPayload(BaseModel):
    code: str
    message: str


class HeartbeatPayload(BaseModel):
    ts: int


class ClientHelloPayload(BaseModel):
    role: Literal["stage", "control"]
    state_version: int | None = Field(default=None, alias="stateVersion")

    model_config = {"populate_by_name": True}


class InteractionChoicePayload(BaseModel):
    option_id: str = Field(alias="optionId")
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")

    model_config = {"populate_by_name": True}


class InteractionPointPayload(BaseModel):
    target_id: str = Field(alias="targetId")
    x: float
    y: float
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")

    model_config = {"populate_by_name": True}


class InteractionDragPayload(BaseModel):
    from_id: str = Field(alias="fromId")
    to_id: str = Field(alias="toId")
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")

    model_config = {"populate_by_name": True}


ControlCommand = Literal["pause", "resume", "skip", "repeat", "back", "takeover"]


class ControlCommandPayload(BaseModel):
    cmd: ControlCommand
    arg: str | None = None


class RosterLearner(BaseModel):
    id: str = Field(min_length=1, max_length=128)
    display_name: str = Field(alias="displayName", min_length=1, max_length=200)
    seat: str | None = Field(default=None, max_length=64)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class LessonStartPayload(BaseModel):
    """Production request to start the already-loaded lesson.

    ``request_id`` makes retries idempotent at the protocol boundary.  It is
    supplied by the control client and echoed by ``lesson.started``.
    """

    request_id: str = Field(alias="requestId", min_length=1, max_length=128)
    lesson_id: str | None = Field(default=None, alias="lessonId", max_length=200)
    class_id: str | None = Field(default=None, alias="classId", max_length=128)
    roster: list[RosterLearner] | None = Field(default=None, min_length=1, max_length=40)
    attendance_ids: list[str] | None = Field(default=None, alias="attendanceIds", max_length=40)
    index: int = Field(default=0, ge=0)
    student_id: str | None = Field(default=None, alias="studentId", max_length=128)
    student_name: str | None = Field(default=None, alias="studentName", max_length=200)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class LessonStartedPayload(BaseModel):
    request_id: str = Field(alias="requestId")
    session_id: str = Field(alias="sessionId")
    conversation_id: str = Field(alias="conversationId")
    lesson_id: str = Field(alias="lessonId")
    student_id: str | None = Field(default=None, alias="studentId")
    index: int
    state_version: int = Field(alias="stateVersion")

    model_config = {"populate_by_name": True}


class StudentSpeechFinalPayload(BaseModel):
    text: str
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    utterance_id: str = Field(alias="utteranceId", min_length=1, max_length=128)
    assignment_id: str = Field(alias="assignmentId", min_length=1, max_length=128)
    response_turn_id: str = Field(alias="responseTurnId", min_length=1, max_length=128)
    capture_id: str = Field(alias="captureId", min_length=1, max_length=128)
    capture_outcome: Literal[
        "speech", "no_speech", "noise_only", "device_lost", "asr_timeout", "asr_unavailable"
    ] = Field(alias="captureOutcome")
    activity_id: str = Field(alias="activityId", min_length=1, max_length=128)
    activity_generation: int = Field(alias="activityGeneration", ge=0)
    synthetic: Literal[True] | None = None
    synthetic_fixture_id: str | None = Field(
        default=None, alias="syntheticFixtureId", min_length=1, max_length=128
    )

    model_config = {"populate_by_name": True, "extra": "forbid"}


class StudentResponseAcceptedPayload(BaseModel):
    """Core's terminal acknowledgement for one student utterance."""

    utterance_id: str = Field(alias="utteranceId", min_length=1, max_length=128)
    outcome: Literal["correct", "near", "wrong", "silence", "timeout", "rejected"]

    model_config = {"populate_by_name": True}


SpeechBehavior = Literal["queue", "interrupt", "replace"]
SpeechSource = Literal["authored", "agent", "system"]


class SpeechTurnStartedPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    behavior: SpeechBehavior
    source: SpeechSource
    conversation_turn_id: str = Field(alias="conversationTurnId")
    activity_id: str | None = Field(default=None, alias="activityId")
    activity_generation: int | None = Field(default=None, alias="activityGeneration")
    audio_asset: str | None = Field(default=None, alias="audioAsset")

    model_config = {"populate_by_name": True}


class SpeechTextDeltaPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    delta: str

    model_config = {"populate_by_name": True}


class SpeechTurnEndedPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    status: Literal["completed", "cancelled", "error"]
    reason: str | None = None

    model_config = {"populate_by_name": True}


class SpeechCancelPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    reason: str | None = None

    model_config = {"populate_by_name": True}


class SpeechBargeInPayload(BaseModel):
    request_id: str = Field(alias="requestId", min_length=1, max_length=128)
    speech_turn_id: str = Field(alias="speechTurnId", min_length=1, max_length=128)
    activity_id: str = Field(alias="activityId", min_length=1, max_length=128)
    activity_generation: int = Field(alias="activityGeneration", ge=0)

    model_config = {"populate_by_name": True}


class SpeechBargeInAckPayload(BaseModel):
    request_id: str = Field(alias="requestId", min_length=1, max_length=128)
    speech_turn_id: str = Field(alias="speechTurnId", min_length=1, max_length=128)
    accepted: bool
    reason: str | None = None

    model_config = {"populate_by_name": True}


class SpeechPlaybackStartedPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    metrics: dict[str, float] | None = None

    model_config = {"populate_by_name": True}


class SpeechPlaybackFinishedPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    status: Literal["completed", "cancelled", "failed"]
    reason: str | None = None
    metrics: dict[str, float] | None = None

    model_config = {"populate_by_name": True}


class SpeechPlaybackObservedPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    status: Literal["completed", "cancelled", "failed"]

    model_config = {"populate_by_name": True, "extra": "forbid"}


SessionStatus = Literal[
    "PREPARING", "RUNNING", "PAUSED", "RECOVERING", "CLOSING", "COMPLETED", "ABORTED"
]
ResponseScope = Literal["selected_individual", "group", "choral", "anonymous", "uncertain"]


class ClassSessionState(BaseModel):
    session_id: str = Field(alias="sessionId")
    status: SessionStatus
    decision_revision: int = Field(alias="decisionRevision", ge=0)
    started_at: int | None = Field(default=None, alias="startedAt")
    elapsed_s: int = Field(default=0, alias="elapsedS", ge=0)
    stage: str
    current_target_id: str | None = Field(default=None, alias="currentTargetId")
    response_turn_id: str | None = Field(default=None, alias="responseTurnId")
    pause_reason: str | None = Field(default=None, alias="pauseReason")
    resume_allowed: bool | None = Field(default=None, alias="resumeAllowed")
    required_action: str | None = Field(default=None, alias="requiredAction")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class TurnAssignment(BaseModel):
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")
    session_id: str = Field(alias="sessionId")
    decision_revision: int = Field(alias="decisionRevision", ge=0)
    activity_id: str = Field(alias="activityId")
    activity_generation: int = Field(alias="activityGeneration", ge=0)
    target_id: str | None = Field(default=None, alias="targetId")
    target_display_name: str | None = Field(default=None, alias="targetDisplayName")
    response_scope: ResponseScope = Field(alias="responseScope")
    capture_scope: Literal["answer_station", "board", "none"] = Field(alias="captureScope")
    expires_at: int = Field(alias="expiresAt")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CaptureRequest(BaseModel):
    capture_id: str = Field(alias="captureId")
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")
    ready_deadline_at: int = Field(alias="readyDeadlineAt", gt=0)
    speech_onset_deadline_ms: int = Field(alias="speechOnsetDeadlineMs", gt=0)
    max_duration_ms: int = Field(alias="maxDurationMs", gt=0)
    end_silence_ms: int = Field(alias="endSilenceMs", gt=0)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class TurnClosedPayload(BaseModel):
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")
    outcome: Literal[
        "correct", "near", "wrong", "uncertain", "unhandled",
        "silence", "timeout", "rejected",
    ]

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CaptureReadyPayload(BaseModel):
    capture_id: str = Field(alias="captureId")
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")
    status: Literal["ready", "failed"]
    reason: str | None = None

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CaptureStartedPayload(BaseModel):
    capture_id: str = Field(alias="captureId")
    assignment_id: str = Field(alias="assignmentId")
    response_turn_id: str = Field(alias="responseTurnId")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CapabilityReportPayload(BaseModel):
    client_instance_id: str = Field(alias="clientInstanceId")
    connection_epoch: int = Field(alias="connectionEpoch", ge=0)
    role: Literal["stage", "control"]
    capabilities: dict[str, bool | str | int | float]
    reported_at: int = Field(alias="reportedAt")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class StageLeaseGrantedPayload(BaseModel):
    lease_id: str = Field(alias="leaseId")
    client_instance_id: str = Field(alias="clientInstanceId")
    expires_at: int = Field(alias="expiresAt")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class ClassroomStatusPayload(BaseModel):
    liveness: Literal["live", "dead"]
    readiness: Literal["ready", "degraded", "not_ready"]
    teachable: bool
    lesson_id: str | None = Field(default=None, alias="lessonId")
    reason: str | None = None
    recovery: dict[str, str] | None = None

    model_config = {"populate_by_name": True, "extra": "forbid"}


# ------------------------------------------------------------------ scene

SceneKind = Literal[
    "idle", "text", "image", "video", "vocabulary", "choice",
    "matching", "sentence_builder", "pronunciation", "roleplay", "explore",
]


class MediaItem(BaseModel):
    id: str
    text: str | None = None
    asset: str | None = None
    audio_asset: str | None = Field(default=None, alias="audioAsset")

    model_config = {"populate_by_name": True}


class SceneOverlay(BaseModel):
    subtitle: str | None = None
    student_name: str | None = Field(default=None, alias="studentName")
    listening: bool | None = None
    mode_badge: Literal["DEGRADED", "OFFLINE"] | None = Field(default=None, alias="modeBadge")

    model_config = {"populate_by_name": True}


class Scene(BaseModel):
    v: Literal[3] = PROTOCOL_VERSION
    state_version: int = Field(alias="stateVersion")
    kind: SceneKind
    props: dict[str, Any] = Field(default_factory=dict)
    overlay: SceneOverlay | None = None

    model_config = {"populate_by_name": True}


# ----------------------------------------------------------------- lesson


class LessonPosition(BaseModel):
    lesson_id: str = Field(alias="lessonId")
    class_id: str = Field(alias="classId")
    activity_index: int = Field(alias="activityIndex")
    activity_count: int = Field(alias="activityCount")
    stage: str
    activity_id: str = Field(default="", alias="activityId")
    activity_generation: int = Field(default=0, alias="activityGeneration", ge=0)
    decision_revision: int = Field(default=0, alias="decisionRevision", ge=0)
    response_turn_id: str | None = Field(default=None, alias="responseTurnId")
    assignment_id: str | None = Field(default=None, alias="assignmentId")
    current_student_id: str | None = Field(default=None, alias="currentStudentId")

    model_config = {"populate_by_name": True}


class SceneSnapshotPayload(BaseModel):
    scene: Scene
    lesson: LessonPosition
    session: ClassSessionState | None = None
    status: ClassroomStatusPayload | None = None
    assignment: TurnAssignment | None = None
    capture: CaptureRequest | None = None
    speech: dict[str, Any] | None = None
    recovery: dict[str, str] | None = None


Emotion = Literal[
    "happy", "sad", "angry", "think", "surprised",
    "awkward", "question", "curious", "neutral",
]

# Live2D motion group per emotion. Note: neutral -> "Idle", not "Neutral".
EMOTION_MOTION_GROUP: dict[str, str] = {
    "happy": "Happy", "sad": "Sad", "angry": "Angry", "think": "Think",
    "surprised": "Surprise", "awkward": "Awkward", "question": "Question",
    "curious": "Curious", "neutral": "Idle",
}


class EmotionSpec(BaseModel):
    name: Emotion
    intensity: float = 1.0


class ActPayload(BaseModel):
    emotion: Union[Emotion, EmotionSpec, None] = None
    motion: str | None = None


class Narration(BaseModel):
    text: str
    # pre-rendered at authoring time; present => skip live TTS
    audio_asset: str | None = Field(default=None, alias="audioAsset")
    act: ActPayload | None = None

    model_config = {"populate_by_name": True}


class Expect(BaseModel):
    kind: Literal["choice", "point", "drag", "speech", "none"]
    correct: Union[str, list[str], None] = None
    accept_fuzzy: list[str] | None = Field(default=None, alias="acceptFuzzy")

    model_config = {"populate_by_name": True}


class Branch(BaseModel):
    on: Literal[
        "correct", "near", "wrong", "uncertain", "unhandled", "silence", "timeout", "always"
    ]
    goto: str
    narration: list[Narration] | None = None


class Activity(BaseModel):
    id: str
    scene: SceneKind
    props: dict[str, Any] = Field(default_factory=dict)
    narration: list[Narration] | None = None
    duration_s: int | None = Field(default=None, alias="durationS")
    expect: Expect | None = None
    branches: list[Branch] | None = None
    teaching: "TeachingSpec | None" = None

    model_config = {"populate_by_name": True, "extra": "forbid"}


ParticipationMode = Literal["whole_class", "pair", "group", "selected_individual", "anonymous"]
EvidencePolicy = Literal["none", "participation", "class_aggregate", "individual"]


class RecoverySpec(BaseModel):
    easier_activity_id: str = Field(alias="easierActivityId")
    safe_default_activity_id: str = Field(alias="safeDefaultActivityId")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class TeachingSpec(BaseModel):
    stage: str
    stage_budget_s: int = Field(alias="stageBudgetS", gt=0)
    response_scope: ResponseScope = Field(alias="responseScope")
    participation_mode: ParticipationMode = Field(alias="participationMode")
    skill_ids: list[str] = Field(alias="skillIds", min_length=1)
    evidence_policy: EvidencePolicy = Field(alias="evidencePolicy")
    recovery: RecoverySpec
    checkpoint: bool = False

    model_config = {"populate_by_name": True, "extra": "forbid"}


class CurriculumObjective(BaseModel):
    id: str
    description: str
    evidence: str

    model_config = {"extra": "forbid"}


class CurriculumSpec(BaseModel):
    locale: str
    learner_wedge: str = Field(alias="learnerWedge")
    framework_refs: list[str] = Field(alias="frameworkRefs", min_length=1)
    objectives: list[CurriculumObjective] = Field(min_length=1)
    approver: str
    approval_status: Literal["draft", "approved"] = Field(alias="approvalStatus")

    model_config = {"populate_by_name": True, "extra": "forbid"}


class SessionPlan(BaseModel):
    duration_min: int = Field(alias="durationMin", ge=35, le=45)
    closure_reserve_s: int = Field(alias="closureReserveS", ge=60)
    named_turn_budget: int = Field(alias="namedTurnBudget", ge=1)
    fairness_cooldown: int = Field(alias="fairnessCooldown", ge=0)

    model_config = {"populate_by_name": True, "extra": "forbid"}


class LessonRun(BaseModel):
    v: Literal[3] = PROTOCOL_VERSION
    lesson_schema_version: Literal[1] = Field(default=1, alias="lessonSchemaVersion")
    delivery_mode: Literal["legacy_single", "autonomous_class"] = Field(
        default="legacy_single", alias="deliveryMode"
    )
    lesson_id: str = Field(alias="lessonId")
    class_id: str = Field(alias="classId")
    title: str
    focus: list[str] = Field(default_factory=list)
    review: list[str] = Field(default_factory=list)
    students_to_check: list[str] = Field(default_factory=list, alias="studentsToCheck")
    activities: list[Activity] = Field(default_factory=list)
    media_manifest: list[str] = Field(default_factory=list, alias="mediaManifest")
    curriculum: CurriculumSpec | None = None
    session_plan: SessionPlan | None = Field(default=None, alias="sessionPlan")

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def autonomous_contract_is_complete(self) -> "LessonRun":
        if self.delivery_mode != "autonomous_class":
            return self
        if self.curriculum is None or self.session_plan is None:
            raise ValueError("autonomous_class requires curriculum and sessionPlan")
        missing = [activity.id for activity in self.activities if activity.teaching is None]
        if missing:
            raise ValueError(
                "autonomous_class activities require teaching metadata: " + ", ".join(missing)
            )
        return self


# ------------------------------------------------------------ agent seam

# Retain this many trailing chars when scanning for "<|", so a tag split
# across two SSE chunks never leaks as spoken text. Do not lower.
TAG_OPEN = "<|"
TAG_CLOSE = "|>"
TAG_TAIL_RETAIN = 5


class AvailableAction(BaseModel):
    id: str
    label: str
    params: list[str] | None = None


class StudentBrief(BaseModel):
    id: str
    name: str
    skills: dict[str, float] = Field(default_factory=dict)


# What actually happened, as graded by core. Mirrors the observable subset of
# `BranchOn` -- `always` is a branch directive, not an observed outcome.
#
# `silence` and `timeout` are here because they are pedagogically the most
# important signals there are: a child who says nothing needs a different
# response from a child who answers wrongly. An earlier version of this type
# omitted them, which made it impossible to tell the agent a student had gone
# quiet -- caught the first time a silence was fed through a live turn.
Outcome = Literal["correct", "near", "wrong", "uncertain", "silence", "timeout", "unhandled"]


class LastInteraction(BaseModel):
    kind: str
    detail: str
    outcome: Outcome | None = None


class RecalledMemory(BaseModel):
    text: str
    when: str


class TurnContext(BaseModel):
    state_version: int = Field(alias="stateVersion")
    lesson: LessonPosition
    scene: Scene
    student: StudentBrief | None = None
    last_interaction: LastInteraction | None = Field(default=None, alias="lastInteraction")
    available_actions: list[AvailableAction] = Field(default_factory=list, alias="availableActions")
    recalled: list[RecalledMemory] | None = None

    model_config = {"populate_by_name": True}


__all__ = [
    "PROTOCOL_VERSION", "EventType", "Mode", "Event",
    "RosterLearner", "LessonStartPayload", "LessonStartedPayload", "StudentSpeechFinalPayload",
    "StudentResponseAcceptedPayload",
    "ClassSessionState", "TurnAssignment", "TurnClosedPayload", "CaptureRequest", "CaptureReadyPayload",
    "CaptureStartedPayload", "CapabilityReportPayload", "StageLeaseGrantedPayload",
    "ClassroomStatusPayload", "SessionStatus", "ResponseScope",
    "SpeechBehavior", "SpeechSource", "SpeechTurnStartedPayload", "SpeechTextDeltaPayload",
    "SpeechTurnEndedPayload", "SpeechCancelPayload",
    "SpeechPlaybackStartedPayload", "SpeechPlaybackFinishedPayload", "SpeechPlaybackObservedPayload",
    "SceneKind", "MediaItem", "SceneOverlay", "Scene",
    "LessonPosition", "Emotion", "EMOTION_MOTION_GROUP", "EmotionSpec", "ActPayload",
    "Narration", "Expect", "Branch", "Activity", "TeachingSpec", "RecoverySpec",
    "CurriculumSpec", "CurriculumObjective", "SessionPlan", "LessonRun",
    "TAG_OPEN", "TAG_CLOSE", "TAG_TAIL_RETAIN",
    "AvailableAction", "StudentBrief", "LastInteraction", "RecalledMemory", "TurnContext",
]
