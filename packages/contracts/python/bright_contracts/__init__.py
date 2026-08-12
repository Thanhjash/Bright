"""Bright wire contracts. Mirror of PROTOCOL.md.

TypeScript mirror: packages/contracts/src/index.ts
Change PROTOCOL.md first, then both mirrors.
"""

from __future__ import annotations

from typing import Any, Literal, Union

from pydantic import BaseModel, Field

PROTOCOL_VERSION = 2

# --------------------------------------------------------------- envelope

EventType = Literal[
    # server -> client
    "scene.update",
    "scene.snapshot",
    "speech.say",
    "speech.turn.started",
    "speech.text.delta",
    "speech.turn.ended",
    "speech.cancel",
    "speech.barge_in.ack",
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
]

Mode = Literal["FULL", "DEGRADED", "OFFLINE"]


class Event(BaseModel):
    v: Literal[2] = PROTOCOL_VERSION
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
    student_id: str | None = Field(default=None, alias="studentId")

    model_config = {"populate_by_name": True}


class InteractionPointPayload(BaseModel):
    target_id: str = Field(alias="targetId")
    x: float
    y: float

    model_config = {"populate_by_name": True}


class InteractionDragPayload(BaseModel):
    from_id: str = Field(alias="fromId")
    to_id: str = Field(alias="toId")

    model_config = {"populate_by_name": True}


ControlCommand = Literal["pause", "resume", "skip", "repeat", "back", "takeover"]


class ControlCommandPayload(BaseModel):
    cmd: ControlCommand
    arg: str | None = None


class LessonStartPayload(BaseModel):
    """Production request to start the already-loaded lesson.

    ``request_id`` makes retries idempotent at the protocol boundary.  It is
    supplied by the control client and echoed by ``lesson.started``.
    """

    request_id: str = Field(alias="requestId", min_length=1, max_length=128)
    index: int = Field(default=0, ge=0)
    student_id: str | None = Field(default=None, alias="studentId", max_length=128)
    student_name: str | None = Field(default=None, alias="studentName", max_length=200)

    model_config = {"populate_by_name": True}


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
    student_id: str | None = Field(default=None, alias="studentId")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    utterance_id: str = Field(alias="utteranceId", min_length=1, max_length=128)
    activity_id: str = Field(alias="activityId", min_length=1, max_length=128)
    activity_generation: int = Field(alias="activityGeneration", ge=0)

    model_config = {"populate_by_name": True}


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

    model_config = {"populate_by_name": True}


class SpeechPlaybackFinishedPayload(BaseModel):
    speech_turn_id: str = Field(alias="speechTurnId")
    status: Literal["completed", "cancelled", "failed"]
    reason: str | None = None
    metrics: dict[str, float] | None = None

    model_config = {"populate_by_name": True}


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
    v: Literal[2] = PROTOCOL_VERSION
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
    current_student_id: str | None = Field(default=None, alias="currentStudentId")

    model_config = {"populate_by_name": True}


class SceneSnapshotPayload(BaseModel):
    scene: Scene
    lesson: LessonPosition


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
    on: Literal["correct", "near", "wrong", "silence", "timeout", "always"]
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

    model_config = {"populate_by_name": True}


class LessonRun(BaseModel):
    v: Literal[2] = PROTOCOL_VERSION
    lesson_id: str = Field(alias="lessonId")
    class_id: str = Field(alias="classId")
    title: str
    focus: list[str] = Field(default_factory=list)
    review: list[str] = Field(default_factory=list)
    students_to_check: list[str] = Field(default_factory=list, alias="studentsToCheck")
    activities: list[Activity] = Field(default_factory=list)
    media_manifest: list[str] = Field(default_factory=list, alias="mediaManifest")

    model_config = {"populate_by_name": True}


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
Outcome = Literal["correct", "near", "wrong", "silence", "timeout"]


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
    "LessonStartPayload", "LessonStartedPayload", "StudentSpeechFinalPayload",
    "StudentResponseAcceptedPayload",
    "SpeechBehavior", "SpeechSource", "SpeechTurnStartedPayload", "SpeechTextDeltaPayload",
    "SpeechTurnEndedPayload", "SpeechCancelPayload",
    "SpeechPlaybackStartedPayload", "SpeechPlaybackFinishedPayload",
    "SceneKind", "MediaItem", "SceneOverlay", "Scene",
    "LessonPosition", "Emotion", "EMOTION_MOTION_GROUP", "EmotionSpec", "ActPayload",
    "Narration", "Expect", "Branch", "Activity", "LessonRun",
    "TAG_OPEN", "TAG_CLOSE", "TAG_TAIL_RETAIN",
    "AvailableAction", "StudentBrief", "LastInteraction", "RecalledMemory", "TurnContext",
]
