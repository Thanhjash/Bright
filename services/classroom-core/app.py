"""classroom-core -- FastAPI app: WS event bus, assets, dev push endpoints.

    GET  /health          {status, mode, stateVersion}
    WS   /ws              the event bus (client.hello -> scene.snapshot -> stream)
    GET  /assets/{path}   files from ASSETS_DIR
    POST /dev/*           dev-only pushes so the UI can be built without an agent

classroom-core is the only writer of state and makes no LLM calls: the agent
lives behind :class:`scheduler.AgentSeam`, injected at startup.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import config  # noqa: F401  -- installs the bright_contracts import path
from bright_contracts import (
    ControlCommandPayload,
    CapabilityReportPayload,
    CaptureReadyPayload,
    CaptureStartedPayload,
    PROTOCOL_VERSION,
    LessonRun,
    LessonStartedPayload,
    LessonStartPayload,
    SceneOverlay,
    SpeechBargeInAckPayload,
    SpeechBargeInPayload,
    SpeechPlaybackFinishedPayload,
    SpeechPlaybackStartedPayload,
    StudentSpeechFinalPayload,
)
from bus import EventBus, Subscriber, to_wire
from bus import now_ms as bus_now_ms
from config import Settings
from class_session import (
    AssignmentRejected,
    CapabilityLeaseRegistry,
    ClassSessionController,
)
from db import Database, open_database
from modes import ModeController
from mcp_server import TurnRegistry, build_mcp_router
from runner import LessonRunner, interaction_kind, load_lesson_run
from scheduler import AgentSeam, BackgroundJobs
from state import StateStore

log = logging.getLogger("classroom_core")

CLIENT_EVENTS = {
    "client.hello",
    "heartbeat.ack",
    "interaction.choice",
    "interaction.point",
    "interaction.drag",
    "control.command",
    "lesson.start",
    "student.speech.final",
    "speech.playback.started",
    "speech.playback.finished",
    "speech.barge_in",
    "capability.report",
    "response.capture.ready",
    "response.capture.started",
}


def websocket_origin_allowed(origin: str | None, allowed: tuple[str, ...]) -> bool:
    """Apply the HTTP CORS allowlist to browser WebSocket handshakes.

    Native clients and test harnesses commonly omit Origin and are allowed;
    browsers always send it, so a present value must match exactly. Wildcard
    remains explicit rather than silently turning an empty list into allow-all.
    """
    if origin is None:
        return True
    return "*" in allowed or origin in allowed


@dataclass
class ConversationCoordinator:
    """Core-owned correlation for one lesson conversation.

    Provider/runtime session ids never escape into the classroom protocol.  A
    Bright conversation starts with the Core session, assigns utterance ids to
    speech input, and relates the next agent speech turn to that utterance.
    """

    conversation_id: str | None = None
    last_utterance_id: str | None = None
    _turn: int = 0
    starts: dict[str, dict[str, Any]] = field(default_factory=dict)
    playback: dict[str, str] = field(default_factory=dict)
    speech_scope: dict[str, tuple[str | None, int | None]] = field(default_factory=dict)
    barge_requests: dict[str, dict[str, Any]] = field(default_factory=dict)

    def begin(self, session_id: str) -> str:
        self.conversation_id = f"conversation-{session_id}"
        self.last_utterance_id = None
        self._turn = 0
        self.playback.clear()
        self.speech_scope.clear()
        self.barge_requests.clear()
        return self.conversation_id

    def note_utterance(self, supplied: str | None = None) -> str:
        utterance_id = supplied or f"utterance-{uuid.uuid4().hex}"
        self.last_utterance_id = utterance_id
        return utterance_id

    def next_speech_ids(self, *, prefix: str = "agent") -> tuple[str, str]:
        self._turn += 1
        speech_turn_id = f"{prefix}-{self._turn}-{uuid.uuid4().hex[:10]}"
        conversation_turn_id = self.last_utterance_id or f"turn-{uuid.uuid4().hex}"
        return speech_turn_id, conversation_turn_id

    def register_speech(
        self,
        speech_turn_id: str,
        *,
        activity_id: str | None = None,
        activity_generation: int | None = None,
    ) -> None:
        self.playback[speech_turn_id] = "produced"
        self.speech_scope[speech_turn_id] = (activity_id, activity_generation)

    def request_barge_in(
        self,
        request: SpeechBargeInPayload,
        *,
        activity_id: str | None,
        activity_generation: int | None,
    ) -> tuple[dict[str, Any], bool]:
        """Validate and reserve one exact PTT interruption.

        The boolean is true only for the first accepted request, so a retry can
        receive the same ACK without cancelling or publishing twice.
        """
        previous = self.barge_requests.get(request.request_id)
        if previous is not None:
            same_turn = previous.get("speechTurnId") == request.speech_turn_id
            if same_turn:
                return previous, False
            return {
                "requestId": request.request_id,
                "speechTurnId": request.speech_turn_id,
                "accepted": False,
                "reason": "requestId was already used for another speech turn",
            }, False

        reason: str | None = None
        state = self.playback.get(request.speech_turn_id)
        if state not in {"produced", "playing"}:
            reason = "speech turn is unknown or already terminal"
        elif self.speech_scope.get(request.speech_turn_id) != (
            request.activity_id,
            request.activity_generation,
        ):
            reason = "speech turn correlation does not match"
        elif (request.activity_id, request.activity_generation) != (
            activity_id,
            activity_generation,
        ):
            reason = "activity generation is stale"

        reply = SpeechBargeInAckPayload(
            requestId=request.request_id,
            speechTurnId=request.speech_turn_id,
            accepted=reason is None,
            reason=reason,
        ).model_dump(by_alias=True, exclude_none=True)
        self.barge_requests[request.request_id] = reply
        if reason is not None:
            return reply, False
        self.playback[request.speech_turn_id] = "cancel_requested"
        return reply, True

    def note_playback(
        self, speech_turn_id: str, *, event: str, status: str
    ) -> tuple[bool, bool, str | None]:
        """Validate a stage's physical playback state machine.

        Returns ``(accepted, changed, reason)``. Repeated identical terminal
        acknowledgements are accepted but never trigger Core twice.
        """
        current = self.playback.get(speech_turn_id)
        if current is None:
            return False, False, "unknown speechTurnId"
        if event == "started":
            if current == "produced":
                self.playback[speech_turn_id] = "playing"
                return True, True, None
            if current == "playing":
                return True, False, None
            return False, False, "speech turn is already terminal"
        terminal = f"finished:{status}"
        if current == terminal:
            return True, False, None
        if status == "completed" and current != "playing":
            return False, False, "playback.finished requires playback.started"
        if status in {"failed", "cancelled"} and current not in {"produced", "playing", "cancel_requested"}:
            return False, False, "speech turn is already terminal"
        self.playback[speech_turn_id] = terminal
        return True, True, None


# --------------------------------------------------------------- container


@dataclass
class Core:
    settings: Settings
    bus: EventBus
    store: StateStore
    db: Database
    modes: ModeController
    jobs: BackgroundJobs
    lesson: LessonRun | None = None
    runner: LessonRunner | None = None
    session_id: str | None = None
    #: Whose lesson this is. Phase 1 runs one named child at a time; the class
    #: is on the board, the student model is about the child being checked.
    student_id: str | None = None
    seam: AgentSeam = field(default_factory=AgentSeam)
    #: Set only when services/agent actually wired up. ``None`` is the NS-1
    #: path and must stay indistinguishable from the pre-agent runner.
    agent_driver: Any = None
    auto_turn: Any = None
    conversations: ConversationCoordinator = field(default_factory=ConversationCoordinator)
    turn_registry: Any = None
    session_controller: ClassSessionController | None = None
    capability_leases: CapabilityLeaseRegistry | None = None

    def set_agent_seam(self, seam: AgentSeam) -> None:
        """The one place services/agent plugs in. Never imported from here."""
        self.seam = seam
        self.jobs.set_seam(seam)

    def set_agent_driver(self, driver: Any) -> None:
        """Hand the runner its decision gate.

        Deliberately *not* done in ``build_core``: the gate has to be absent,
        not merely inert, when no agent is wired, or ``_follow`` grows an
        await that the LLM-free path never had (NS-1).
        """
        from agent_bridge import AutoTurn

        self.agent_driver = driver
        self.auto_turn = AutoTurn(self, timeout_s=self.settings.agent_turn_timeout_s)
        if self.runner is not None:
            self.runner.decide_next = self.auto_turn

    async def start_lesson(
        self,
        index: int = 0,
        student_id: str | None = None,
        student_name: str | None = None,
        roster: list[Any] | None = None,
        attendance_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if self.runner is None:
            raise HTTPException(status_code=409, detail="no lesson_run loaded")
        # Validate the complete classroom request before creating any durable
        # session/conversation state. A malformed roster must be a clean
        # rejection, not a ghost session which blocks the next start.
        if self.session_controller is not None and roster is not None:
            self.session_controller.configure_roster(roster, attendance_ids)
        if student_id:
            self.student_id = student_id
            self._upsert_student(student_id, student_name)
        if self.session_id is None:
            self.session_id = self.db.start_session(
                student_id=student_id or self.student_id,
                lesson_id=self.lesson.lesson_id if self.lesson else None,
                mode=self.store.mode,
            )
            self.runner.session_id = self.session_id
            self.conversations.begin(self.session_id)
        self.runner.student_id = self.student_id

        # Public learner-history greetings are intentionally absent. The
        # authored hook starts the shared class without exposing one child's
        # prior weakness to their peers.
        greeting = None

        if self.session_controller is not None:
            await self.session_controller.start(index)
        else:
            await self.runner.start(index)
        return {
            "ok": True,
            "sessionId": self.session_id,
            "studentId": self.student_id,
            "index": self.runner.index,
            "stateVersion": self.store.state_version,
            "conversationId": self.conversations.conversation_id,
            "greeting": greeting,
        }

    def _upsert_student(self, student_id: str, student_name: str | None) -> None:
        """Make sure the child exists before anything is recorded about them.

        Never invents a name over an existing one, and never blanks ``meta``:
        ``upsert_student`` overwrites both columns, so the current row has to
        be read first.
        """
        try:
            existing = self.db.get_student(student_id) or {}
            self.db.upsert_student(
                student_id,
                name=student_name or existing.get("name") or student_id,
                display_name=existing.get("displayName"),
                meta=existing.get("meta") or {},
            )
        except Exception:  # noqa: BLE001 - a class must not fail to start on this
            log.exception("could not upsert student %s", student_id)

    async def _greet(self, index: int) -> dict[str, Any] | None:
        """Deprecated: learner memory is never spoken to a shared room."""
        del index
        return None

    async def end_session(self) -> None:
        if self.session_id is None:
            return
        if self.session_controller is not None:
            self.session_controller.cancel_session_clock()
        self.db.end_session(self.session_id, mode=self.store.mode)
        self.jobs.schedule_session_summary(self.session_id)
        self.session_id = None

    def publish_speech(
        self,
        text: str,
        *,
        source: str = "agent",
        behavior: str = "queue",
        activity_id: str | None = None,
        activity_generation: int | None = None,
        audio_asset: str | None = None,
    ) -> str:
        """Publish one complete v2 speech turn with Core-owned correlation."""
        speech_turn_id, conversation_turn_id = self.conversations.next_speech_ids(prefix=source)
        started: dict[str, Any] = {
            "speechTurnId": speech_turn_id,
            "behavior": behavior,
            "source": source,
            "conversationTurnId": conversation_turn_id,
            "activityId": activity_id,
            "activityGeneration": activity_generation,
        }
        if audio_asset:
            started["audioAsset"] = audio_asset
        self.conversations.register_speech(
            speech_turn_id,
            activity_id=activity_id,
            activity_generation=activity_generation,
        )
        self.bus.publish("speech.turn.started", {k: v for k, v in started.items() if v is not None})
        self.bus.publish("speech.text.delta", {"speechTurnId": speech_turn_id, "delta": text})
        self.bus.publish(
            "speech.turn.ended", {"speechTurnId": speech_turn_id, "status": "completed"}
        )
        return speech_turn_id

    def cancel_speech(self, speech_turn_id: str, reason: str = "superseded") -> None:
        self.bus.publish(
            "speech.cancel", {"speechTurnId": speech_turn_id, "reason": reason}
        )

    def snapshot(self) -> dict[str, Any]:
        """One reconnect-safe aggregate, not a half-new classroom view."""
        payload = self.store.snapshot()
        controller = self.session_controller
        if controller is not None and self.session_id is not None:
            payload["session"] = controller.session_payload()
            assignment = controller.assignments.current_for_activity(
                self.session_id,
                getattr(getattr(self.runner, "current", None), "id", ""),
                getattr(self.runner, "_generation", 0),
            )
            if assignment is not None:
                payload["assignment"] = assignment.public()
                if assignment.capture_id is not None:
                    payload["capture"] = assignment.capture_request()
            payload["status"] = {
                "liveness": "live",
                "readiness": "ready"
                if controller.session_state == "RUNNING"
                else "degraded",
                "teachable": controller.session_state == "RUNNING",
                "lessonId": self.lesson.lesson_id if self.lesson else None,
                "reason": controller.pause_reason,
            }
            if controller.pause_reason:
                payload["recovery"] = {
                    "reason": controller.pause_reason,
                    "requiredAction": "resume_or_takeover",
                }
        active = next(
            (
                (turn_id, status)
                for turn_id, status in reversed(tuple(self.conversations.playback.items()))
                if status in {"produced", "playing", "cancel_requested"}
            ),
            None,
        )
        if active:
            turn_id, status = active
            payload["speech"] = {
                "speechTurnId": turn_id,
                "status": "playing" if status == "playing" else "queued",
            }
        return payload


async def handle_barge_in(
    core: Core, sub: Subscriber, payload: dict[str, Any]
) -> None:
    """Authorize one exact Control PTT interruption and send its terminal ACK."""
    try:
        request = SpeechBargeInPayload.model_validate(payload)
    except Exception as exc:  # noqa: BLE001 - malformed wire input
        core.bus.send(
            sub,
            "error",
            {"code": "invalid_barge_in", "message": str(exc)[:240]},
        )
        return
    if sub.role != "control":
        reply = SpeechBargeInAckPayload(
            requestId=request.request_id,
            speechTurnId=request.speech_turn_id,
            accepted=False,
            reason="only control may request barge-in",
        ).model_dump(by_alias=True, exclude_none=True)
        core.bus.send(sub, "speech.barge_in.ack", reply)
        return
    runner = core.runner
    current = getattr(runner, "current", None)
    reply, changed = core.conversations.request_barge_in(
        request,
        activity_id=getattr(current, "id", None),
        activity_generation=getattr(runner, "_generation", None),
    )
    if changed:
        driver = getattr(core, "agent_driver", None)
        cancelled = bool(
            driver is not None
            and driver.cancel_speech_turn(request.speech_turn_id, "control:barge_in")
        )
        if not cancelled:
            core.cancel_speech(request.speech_turn_id, "control:barge_in")
    core.bus.send(sub, "speech.barge_in.ack", reply)


def handle_client_hello(core: Core, sub: Subscriber, payload: dict[str, Any]) -> None:
    """Resnapshot without ever allowing a connection to change its role."""
    requested_role = str(payload.get("role") or "")
    if requested_role != sub.role:
        core.bus.send(
            sub,
            "error",
            {
                "code": "role_locked",
                "message": "client role is fixed for the lifetime of the connection",
            },
        )
        return
    snapshot = getattr(core, "snapshot", None)
    core.bus.send(
        sub,
        "scene.snapshot",
        snapshot() if callable(snapshot) else core.store.snapshot(),
    )


def build_core(settings: Settings | None = None) -> Core:
    settings = settings or Settings.from_env()
    from data_policy import DataPolicy

    policy = DataPolicy.parse(settings.data_policy)
    if policy == DataPolicy.SYNTHETIC_DEV and (
        not settings.dev_endpoints or not settings.synthetic_dev_confirmed
    ):
        raise RuntimeError(
            "synthetic_dev requires CORE_DEV=1 and BRIGHT_SYNTHETIC_DEV_ACK=1"
        )
    if policy == DataPolicy.HOSTED_EPHEMERAL_TRANSCRIPT and not settings.hosted_raw_confirmed:
        raise RuntimeError(
            "hosted_ephemeral_transcript requires BRIGHT_HOSTED_RAW_ACK=1"
        )
    store = StateStore(mode=settings.mode_override or "OFFLINE")  # type: ignore[arg-type]
    bus = EventBus(lambda: store.state_version, queue_maxsize=settings.queue_maxsize)
    database = open_database(settings.db_path)
    modes = ModeController(
        store,
        bus,
        full_max_latency_s=settings.full_max_latency_s,
        degraded_max_latency_s=settings.degraded_max_latency_s,
        recover_after=settings.recover_after,
        degrade_after=settings.degrade_after,
        forced_mode=settings.mode_override,  # type: ignore[arg-type]
    )
    jobs = BackgroundJobs(
        database,
        modes,
        probe_interval_s=settings.probe_interval_s,
        summary_delay_s=settings.summary_delay_s,
        prepare_next_hour=settings.prepare_next_hour,
        recheck_after_s=settings.recheck_after_s,
    )
    core = Core(settings=settings, bus=bus, store=store, db=database, modes=modes, jobs=jobs)
    core.turn_registry = TurnRegistry(
        core,
        default_ttl_s=max(settings.agent_turn_timeout_s, settings.agent_greeting_timeout_s) + 2.0,
    )

    if settings.lesson_run_path.is_file():
        try:
            core.lesson = load_lesson_run(str(settings.lesson_run_path))
            core.runner = LessonRunner(
                bus,
                store,
                core.lesson,
                db=database,
                silence_timeout_s=settings.silence_timeout_s,
                reveal_hold_s=settings.reveal_hold_s,
                speech_correct_confidence=settings.speech_correct_confidence,
                playback_ack_timeout_s=settings.playback_ack_timeout_s,
                on_finish=core.end_session,
                publish_speech=core.publish_speech,
                cancel_speech=core.cancel_speech,
            )
            core.session_controller = ClassSessionController(
                core,
                core.runner,
                capture_ready_timeout_s=settings.capture_ready_timeout_s,
            )
            core.capability_leases = CapabilityLeaseRegistry(core)
        except Exception:  # noqa: BLE001 - a bad lesson file must not stop the service
            log.exception("failed to load lesson_run at %s", settings.lesson_run_path)
    else:
        log.warning("no lesson_run at %s", settings.lesson_run_path)
    return core


# ----------------------------------------------------------- dev payloads


class DevScene(BaseModel):
    kind: str = "text"
    props: dict[str, Any] = Field(default_factory=dict)
    overlay: dict[str, Any] | None = None


class DevSay(BaseModel):
    text: str
    audio_asset: str | None = Field(default=None, alias="audioAsset")
    turn_id: str | None = Field(default=None, alias="turnId")
    act: dict[str, Any] | None = None

    model_config = {"populate_by_name": True}


class DevControl(BaseModel):
    cmd: str
    arg: str | None = None


class DevInteraction(BaseModel):
    type: str = "interaction.choice"
    payload: dict[str, Any] = Field(default_factory=dict)


class DevMode(BaseModel):
    mode: str
    reason: str = "set via /dev/mode"


class DevStart(BaseModel):
    index: int = 0
    student_id: str | None = Field(default=None, alias="studentId")
    #: Only used the first time a student is seen. There is no roster service
    #: yet, and "s01" is a poor thing to be greeted by.
    student_name: str | None = Field(default=None, alias="studentName")

    model_config = {"populate_by_name": True}


# ------------------------------------------------------------------- app


def create_app(settings: Settings | None = None, core: Core | None = None) -> FastAPI:
    settings = settings or (core.settings if core else Settings.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.core = core or build_core(settings)
        app.state.core.jobs.start()

        # The teacher agent is opt-in and entirely optional. Without it the
        # lesson still runs end to end (NS-1) -- it simply follows the authored
        # branches instead of adapting. A failure to wire it is logged and
        # ignored, never fatal: a missing API key must not stop a class.
        app.state.agent_driver = None
        agent_mode = os.environ.get("BRIGHT_AGENT", "off").strip().lower()
        if agent_mode in {"1", "true", "yes", "on"}:
            agent_mode = "direct"  # compatibility with the original switch
        strict_ideal = settings.run_profile == "ideal_hosted"
        if strict_ideal and agent_mode != "hermes":
            raise RuntimeError(
                "ideal_hosted requires BRIGHT_AGENT=hermes; authored fallback is not acceptance evidence"
            )
        if agent_mode not in {"", "0", "false", "no", "off", "none"}:
            try:
                from agent_bridge import AgentDriver, build_agent_seam

                if agent_mode == "direct":
                    from bright_agent.direct import DirectAgent

                    factory = lambda executor: DirectAgent(executor)
                elif agent_mode == "hermes":
                    from bright_agent.hermes import HermesAgent

                    factory = lambda executor: HermesAgent(executor)
                elif agent_mode == "scripted":
                    from bright_agent.scripted import ScriptedAgent

                    factory = lambda executor: ScriptedAgent(executor)
                else:
                    raise ValueError(
                        f"unknown BRIGHT_AGENT={agent_mode!r}; use hermes, scripted, direct, or off"
                    )

                core_: Core = app.state.core
                driver = AgentDriver(core_, factory)
                # Two halves, one agent: the live decision gate, and the
                # background jobs that run when nobody is watching.
                core_.set_agent_driver(driver)
                core_.set_agent_seam(build_agent_seam(core_, driver.agent))
                app.state.agent_driver = driver
                log.info(
                    "[agent] wired: %s (turn timeout %.1fs, greeting timeout %.1fs)",
                    type(driver.agent).__name__,
                    settings.agent_turn_timeout_s,
                    settings.agent_greeting_timeout_s,
                )
            except Exception as exc:  # noqa: BLE001
                if strict_ideal:
                    raise RuntimeError(
                        "ideal_hosted could not wire the pinned Hermes agent"
                    ) from exc
                log.warning("[agent] not wired (%s) -- lessons will run unadapted", exc)
        if settings.autostart_lesson and app.state.core.runner is not None:
            await app.state.core.start_lesson()
        log.info(
            "classroom-core ready on %s:%s (mode=%s, lesson=%s)",
            settings.host,
            settings.port,
            app.state.core.store.mode,
            app.state.core.lesson.lesson_id if app.state.core.lesson else "-",
        )
        try:
            yield
        finally:
            current: Core = app.state.core
            if current.session_controller is not None:
                current.session_controller.cancel_session_clock()
            if current.runner is not None:
                await current.runner.stop()
            current.jobs.shutdown()
            current.db.close()

    app = FastAPI(title="bright classroom-core", version="1.0.0", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    def get_core() -> Core:
        return app.state.core

    # Hermes discovers this as an MCP Streamable HTTP server.  The route is
    # present even when disabled so a bad deployment fails explicitly; with no
    # token every request is rejected and no tool surface is exposed.
    app.include_router(build_mcp_router(get_core, settings.mcp_token))

    # ------------------------------------------------------------- health
    @app.get("/health")
    async def health() -> dict[str, Any]:
        core_ = get_core()
        return {
            "status": "ok",
            "mode": core_.store.mode,
            "stateVersion": core_.store.state_version,
        }

    def readiness() -> tuple[dict[str, Any], bool]:
        """Return the product-facing readiness snapshot and verdict."""
        core_ = get_core()
        leases = core_.capability_leases
        if leases is not None:
            leases.expire()
        checks = {
            "lesson": core_.lesson is not None and core_.runner is not None,
            "stageAudioOwner": bool(leases and leases.stage_owner),
            "controlInputOwner": bool(leases and leases.control_input_owner),
            "agentConfigured": os.environ.get("BRIGHT_AGENT", "off").strip().lower()
            == "hermes",
            "agentFull": core_.store.mode == "FULL",
        }
        required = ("lesson", "stageAudioOwner", "controlInputOwner")
        if settings.run_profile == "ideal_hosted":
            required += ("agentConfigured", "agentFull")
        ready_now = all(checks[name] for name in required)
        return {
            "status": "ready" if ready_now else "not_ready",
            "profile": settings.run_profile,
            "mode": core_.store.mode,
            "checks": checks,
        }, ready_now

    @app.get("/ready")
    async def ready() -> JSONResponse:
        """Core-local readiness; the launcher composes Speech/Hermes health.

        This endpoint never performs a model completion.  In the strict
        ``ideal_hosted`` profile it requires both real browser capability
        owners and a healthy Hermes-derived FULL mode before declaring the
        classroom ready to start.
        """
        body, ready_now = readiness()
        return JSONResponse(body, status_code=200 if ready_now else 503)

    # ------------------------------------------------------------- assets
    @app.get("/assets/{path:path}")
    async def assets(path: str):
        core_ = get_core()
        base = core_.settings.assets_dir.resolve()
        cleaned = path.removeprefix("asset://").lstrip("/")
        if not cleaned:
            raise HTTPException(status_code=404, detail="asset not found")
        try:
            target = (base / cleaned).resolve()
        except (OSError, ValueError):
            raise HTTPException(status_code=404, detail="asset not found") from None
        if not target.is_relative_to(base) or not target.is_file():
            raise HTTPException(status_code=404, detail="asset not found")
        return FileResponse(target)

    # ------------------------------------------------------------- socket
    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        core_ = get_core()
        if not websocket_origin_allowed(ws.headers.get("origin"), settings.cors_origins):
            await ws.close(code=4403, reason="websocket origin not allowed")
            return
        await ws.accept()
        sub = core_.bus.subscribe()
        writer: asyncio.Task[None] | None = None
        heart: asyncio.Task[None] | None = None
        try:
            try:
                raw = await asyncio.wait_for(
                    ws.receive_text(), timeout=core_.settings.hello_timeout_s
                )
            except asyncio.TimeoutError:
                await ws.close(code=4408, reason="client.hello timeout")
                return
            message = _parse(raw)
            if message is None or message.get("type") != "client.hello":
                await ws.close(code=4400, reason="expected client.hello")
                return
            if message.get("v") != PROTOCOL_VERSION:
                await ws.close(code=4426, reason=f"unsupported protocol v={message.get('v')}")
                return

            payload = message.get("payload") or {}
            requested_role = str(payload.get("role") or "")
            if requested_role not in {"stage", "control"}:
                await ws.close(code=4400, reason="client.hello role must be stage or control")
                return
            sub.role = requested_role
            # Always a full snapshot: the client's stateVersion is only ever a
            # reason to *take* one, never a reason to skip it.
            core_.bus.send(sub, "scene.snapshot", core_.snapshot())
            # ...and always state the mode. `mode.changed` fires only on a
            # CHANGE, so a client that connects while we are already DEGRADED or
            # OFFLINE would otherwise never hear about it and would sit on its
            # own default. The facilitator console defaulted to FULL and showed a
            # healthy agent while the agent was in fact unreachable — the exact
            # failure the console exists to prevent.
            core_.bus.send(
                sub,
                "mode.changed",
                {"mode": core_.store.mode, "reason": "hello"},
            )
            writer = asyncio.ensure_future(_writer(ws, sub))
            heart = asyncio.ensure_future(_heartbeat(core_, sub))

            while True:
                raw = await ws.receive_text()
                message = _parse(raw)
                if message is None:
                    core_.bus.send(
                        sub,
                        "error",
                        {"code": "malformed_json", "message": "message is not valid JSON"},
                    )
                    continue
                await _handle_client_event(core_, sub, message)
        except WebSocketDisconnect:
            pass
        except RuntimeError:
            pass  # socket already closed by the writer
        finally:
            if core_.capability_leases is not None:
                core_.capability_leases.disconnect(sub)
            core_.bus.unsubscribe(sub)
            for task in (writer, heart):
                if task is not None:
                    task.cancel()
                    try:
                        await task
                    except (asyncio.CancelledError, Exception):  # noqa: BLE001
                        pass

    async def _writer(ws: WebSocket, sub: Subscriber) -> None:
        while True:
            if sub.dropped:
                await ws.close(code=1011, reason=sub.drop_reason)
                return
            try:
                frame = await asyncio.wait_for(sub.queue.get(), timeout=0.25)
            except asyncio.TimeoutError:
                continue
            await ws.send_text(json.dumps(frame, separators=(",", ":")))

    async def _heartbeat(core_: Core, sub: Subscriber) -> None:
        """Prove the link is alive, and notice when it is not (PROTOCOL §9.8).

        A closed socket is the easy failure. The dangerous one is the silent
        link: bytes stop, nothing closes, and the board freezes in front of
        thirty children while `connection.state` still says `open`. WebSocket
        ping/pong does not settle it -- it is handled below the application and
        a proxy can keep it alive over a session that is already dead -- so
        liveness is proved at the application layer, in both directions.

        The frame is sent through the subscriber's own queue, not straight to
        the socket: one writer per connection is what keeps frames ordered.

        **The drop deadline is armed by the first ack**, deliberately. A client
        that has never acked has not implemented §9.8 (the pre-§9.8 stage, a
        dev script, an integration harness), and dropping it every 15 s would
        break a working classroom to enforce a check it cannot answer. Once a
        client has acked *once* the full rule applies to it: ack, then silence,
        is exactly the dead-link signature, and it is dropped at
        ``heartbeat_dead_s``. A client that never acks is still bounded by
        §9.9 backpressure -- its queue fills and the socket closes with 1011.
        To make the rule unconditional, drop the ``speaks_heartbeat`` test.
        """
        interval = max(0.01, core_.settings.heartbeat_interval_s)
        dead_s = max(interval, core_.settings.heartbeat_dead_s)
        # Two clocks, one loop: heartbeats go out on ``interval``, the deadline
        # is checked an order of magnitude finer so "dropped at 15 s" does not
        # mean "dropped at the next 5 s tick after 15 s".
        tick = max(0.01, min(interval, dead_s) / 10.0)
        last_sent = 0.0
        while not sub.dropped:
            await asyncio.sleep(tick)
            now = time.monotonic()
            if now - last_sent >= interval:
                last_sent = now
                sub.heartbeats += 1
                core_.bus.send_oob(sub, "heartbeat", {"ts": bus_now_ms()})
            silent = sub.silent_for()
            if sub.speaks_heartbeat and silent is not None and silent > dead_s:
                log.info(
                    "[bus] dropping subscriber #%s (%s): no heartbeat.ack for %.1fs",
                    sub.id, sub.role, silent,
                )
                sub.drop(f"no heartbeat.ack for {dead_s:.0f}s")
                return

    async def _handle_client_event(core_: Core, sub: Subscriber, message: dict[str, Any]) -> None:
        if message.get("v") != PROTOCOL_VERSION:
            core_.bus.send(
                sub,
                "error",
                {
                    "code": "protocol_mismatch",
                    "message": f"unsupported protocol v={message.get('v')}",
                },
            )
            return
        type_ = str(message.get("type") or "")
        payload = message.get("payload") or {}
        if type_ not in CLIENT_EVENTS:
            core_.bus.send(
                sub,
                "error",
                {"code": "unknown_event", "message": f"unknown client event: {type_}"},
            )
            return

        if type_ == "heartbeat.ack":
            # Out-of-band in both directions: an ack proves the link, it is not
            # an event, and it must not draw a frame in reply -- an ack that
            # produced a frame that produced an ack is a busy loop.
            raw_ts = payload.get("ts")
            try:
                sent_ts = int(raw_ts) if raw_ts is not None else None
            except (TypeError, ValueError):
                sent_ts = None
            sub.note_ack(sent_ts)
            return

        if type_ == "client.hello":
            handle_client_hello(core_, sub, payload)
            return

        if type_ == "capability.report":
            try:
                report = CapabilityReportPayload.model_validate(payload)
                if core_.capability_leases is None:
                    raise AssignmentRejected("capability registry unavailable")
                lease = core_.capability_leases.report(sub, report)
            except Exception as exc:  # noqa: BLE001
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "invalid_capability_report", "message": str(exc)[:240]},
                )
                return
            if lease is not None:
                core_.bus.send(
                    sub,
                    "stage.lease.granted",
                    {
                        "leaseId": lease.lease_id,
                        "clientInstanceId": lease.client_instance_id,
                        "expiresAt": int(
                            (time.time() + max(0.0, lease.expires_at - time.monotonic()))
                            * 1000
                        ),
                    },
                )
                core_.bus.publish(
                    "classroom.status",
                    {
                        "liveness": "live",
                        "readiness": "ready",
                        "teachable": True,
                        "lessonId": core_.lesson.lesson_id if core_.lesson else None,
                        "reason": "stage_audio_owner_ready",
                    },
                )
            return

        if type_ == "control.command":
            if sub.role != "control":
                core_.bus.send(sub, "error", {"code": "forbidden", "message": "only control may send commands"})
                return
            if core_.runner is None:
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "no_lesson", "message": "no lesson_run loaded"},
                )
                return
            try:
                control = ControlCommandPayload.model_validate(payload)
            except Exception as exc:  # noqa: BLE001 - malformed wire input
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "invalid_control_command", "message": str(exc)[:240]},
                )
                return
            command = control.cmd
            if command in {"pause", "skip", "back", "takeover"}:
                driver = getattr(core_, "agent_driver", None)
                if driver is not None:
                    driver.cancel_current(f"control:{command}")
            if core_.session_controller is not None:
                await core_.session_controller.control(command, control.arg)
            else:
                await core_.runner.control(command, control.arg)
            return

        if type_ == "lesson.start":
            if sub.role != "control":
                core_.bus.send(sub, "error", {"code": "forbidden", "message": "only control may start a lesson"})
                return
            try:
                request = LessonStartPayload.model_validate(payload)
            except Exception as exc:  # noqa: BLE001 - wire rejection, not a server fault
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "invalid_lesson_start", "message": str(exc)[:240]},
                )
                return
            previous = core_.conversations.starts.get(request.request_id)
            if previous is not None:
                core_.bus.send(sub, "lesson.started", previous)
                return
            if core_.runner is None or core_.lesson is None:
                core_.bus.send(sub, "error", {"code": "no_lesson", "message": "no lesson_run loaded"})
                return
            if settings.run_profile == "ideal_hosted":
                ready_body, ready_now = readiness()
                if not ready_now:
                    missing = [
                        name for name, value in ready_body["checks"].items() if not value
                    ]
                    core_.bus.send(
                        sub,
                        "error",
                        {
                            "code": "classroom_not_ready",
                            "message": "ideal classroom is missing: " + ", ".join(missing),
                        },
                    )
                    return
            if core_.runner.running or core_.session_id is not None:
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "lesson_already_running", "message": "finish the current lesson before starting another"},
                )
                return
            if request.index >= len(core_.runner.activities):
                core_.bus.send(sub, "error", {"code": "invalid_start_index", "message": "activity index is outside this lesson"})
                return
            if core_.lesson.delivery_mode == "autonomous_class":
                if request.lesson_id not in {None, core_.lesson.lesson_id}:
                    core_.bus.send(sub, "error", {"code": "lesson_mismatch", "message": "lessonId does not match loaded lesson"})
                    return
                if request.class_id not in {None, core_.lesson.class_id}:
                    core_.bus.send(sub, "error", {"code": "class_mismatch", "message": "classId does not match loaded lesson"})
                    return
                if request.roster is None:
                    core_.bus.send(sub, "error", {"code": "roster_required", "message": "autonomous_class requires roster"})
                    return
            try:
                started = await core_.start_lesson(
                    request.index,
                    request.student_id,
                    request.student_name,
                    roster=request.roster,
                    attendance_ids=request.attendance_ids,
                )
            except ValueError as exc:
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "invalid_class_setup", "message": str(exc)[:240]},
                )
                return
            reply = LessonStartedPayload(
                requestId=request.request_id,
                sessionId=started["sessionId"],
                conversationId=started["conversationId"],
                lessonId=core_.lesson.lesson_id,
                studentId=started["studentId"],
                index=started["index"],
                stateVersion=started["stateVersion"],
            ).model_dump(by_alias=True, exclude_none=True)
            core_.conversations.starts[request.request_id] = reply
            core_.bus.publish("lesson.started", reply)
            return

        if type_ == "speech.barge_in":
            await handle_barge_in(core_, sub, payload)
            return

        if type_ in ("speech.playback.started", "speech.playback.finished"):
            if sub.role != "stage":
                core_.bus.send(sub, "error", {"code": "forbidden", "message": "only stage may acknowledge playback"})
                return
            if core_.capability_leases is None or not core_.capability_leases.owns_audio(sub):
                core_.bus.send(sub, "error", {"code": "stage_lease_required", "message": "only active Stage audio owner may acknowledge playback"})
                return
            try:
                parsed_playback = (
                    SpeechPlaybackStartedPayload.model_validate(payload)
                    if type_ == "speech.playback.started"
                    else SpeechPlaybackFinishedPayload.model_validate(payload)
                )
            except Exception as exc:  # noqa: BLE001 - malformed wire input
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "invalid_playback_ack", "message": str(exc)[:240]},
                )
                return
            speech_turn_id = parsed_playback.speech_turn_id
            status = (
                "playing"
                if type_ == "speech.playback.started"
                else parsed_playback.status
            )
            event = "started" if type_ == "speech.playback.started" else "finished"
            was_authorized_barge = (
                core_.conversations.playback.get(speech_turn_id) == "cancel_requested"
            )
            accepted, changed, reason = core_.conversations.note_playback(
                speech_turn_id, event=event, status=status
            )
            if not accepted:
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "invalid_playback_ack", "message": reason or "invalid playback transition"},
                )
                return
            if event == "started" and changed and core_.runner is not None:
                core_.runner.on_playback_started(speech_turn_id)
            if event == "finished" and changed and core_.runner is not None:
                # Relay only the sanitized terminal state after role, lease,
                # schema, turn and playback-transition validation. This lets a
                # Control browser on another machine/profile open its mic
                # without trusting or fabricating a Stage ACK.
                core_.bus.publish(
                    "speech.playback.observed",
                    {"speechTurnId": speech_turn_id, "status": status},
                )
                controller = core_.session_controller
                if controller is not None:
                    if status == "completed" and controller.note_callout_playback_finished(
                        speech_turn_id
                    ):
                        return
                    if status != "completed" and controller.note_callout_playback_failed(
                        speech_turn_id, status
                    ):
                        return
                driver = getattr(core_, "agent_driver", None)
                if driver is not None and driver.note_playback_result(speech_turn_id, status):
                    return
                if status == "completed":
                    core_.runner.on_playback_finished(speech_turn_id)
                elif status == "cancelled" and was_authorized_barge:
                    core_.runner.on_playback_interrupted(speech_turn_id, authorized=True)
                else:
                    core_.runner.on_playback_failed(speech_turn_id, status)
            return

        if type_ in {"response.capture.ready", "response.capture.started"}:
            if sub.role != "control" or core_.capability_leases is None or not core_.capability_leases.owns_input(sub):
                core_.bus.send(sub, "error", {"code": "control_input_lease_required", "message": "active Control audio-input owner required for capture"})
                return
            try:
                if core_.session_controller is None:
                    raise AssignmentRejected("no active class session")
                if type_ == "response.capture.ready":
                    parsed = CaptureReadyPayload.model_validate(payload)
                    core_.session_controller.note_capture_ready(
                        parsed.model_dump(by_alias=True, exclude_none=True)
                    )
                else:
                    parsed = CaptureStartedPayload.model_validate(payload)
                    core_.session_controller.note_capture_started(
                        parsed.model_dump(by_alias=True, exclude_none=True)
                    )
            except Exception as exc:  # noqa: BLE001
                core_.bus.send(sub, "error", {"code": "invalid_capture_state", "message": str(exc)[:240]})
            return

        # interaction.* and student.speech.final -> the reflex tier
        if type_.startswith("interaction.") or type_ == "student.speech.final":
            driver = core_.agent_driver
            if driver is not None:
                driver.cancel_current("new student response")
        if type_ == "student.speech.final":
            # Assignment identifiers are broadcast for rendering/correlation;
            # possession is not authorization to inject learner evidence.
            if (
                sub.role != "control"
                or core_.capability_leases is None
                or not core_.capability_leases.owns_input(sub)
            ):
                core_.bus.send(
                    sub,
                    "error",
                    {
                        "code": "control_input_lease_required",
                        "message": "active Control audio-input owner required for speech evidence",
                    },
                )
                return
            try:
                speech_input = StudentSpeechFinalPayload.model_validate(payload)
            except Exception as exc:  # noqa: BLE001 - malformed wire input
                core_.bus.send(
                    sub,
                    "error",
                    {"code": "invalid_student_speech", "message": str(exc)[:240]},
                )
                return
            utterance_id = core_.conversations.note_utterance(speech_input.utterance_id)

            def acknowledge(outcome: str) -> None:
                # This is the only terminal signal for the UI's listening
                # state. It contains no transcript and is safe to broadcast.
                core_.bus.publish(
                    "student.response.accepted",
                    {"utteranceId": utterance_id, "outcome": outcome},
                )

            if core_.runner is None:
                acknowledge("rejected")
                return
            current = core_.runner.current
            if current is None:
                acknowledge("rejected")
                return
            if speech_input.activity_id != current.id:
                core_.bus.send(sub, "error", {"code": "stale_utterance", "message": "speech belongs to an earlier activity"})
                acknowledge("rejected")
                return
            if speech_input.activity_generation != core_.runner._generation:
                core_.bus.send(sub, "error", {"code": "stale_utterance", "message": "speech belongs to an earlier activity generation"})
                acknowledge("rejected")
                return
            normalized = speech_input.model_dump(by_alias=True, exclude_none=True)
            assignment = None
            if core_.session_controller is not None:
                try:
                    assignment = await core_.session_controller.claim_response(normalized)
                except AssignmentRejected as exc:
                    core_.bus.send(sub, "error", {"code": "invalid_response_capability", "message": str(exc)[:240]})
                    acknowledge("rejected")
                    return
                normalized["_coreStudentId"] = assignment.target
                normalized["_responseTurnId"] = assignment.response_turn_id
                normalized["_evidencePolicy"] = assignment.evidence_policy
                capture_outcome = normalized.get("captureOutcome")
                if capture_outcome == "noise_only":
                    normalized["_coreOutcome"] = "uncertain"
                elif capture_outcome == "no_speech":
                    normalized["_coreOutcome"] = "silence"
                elif capture_outcome in {"device_lost", "asr_timeout", "asr_unavailable"}:
                    # Infrastructure failure is not evidence about the child.
                    # Route it through the lesson's explicit recovery branch;
                    # never permit Runner's default transition to advance.
                    normalized["_coreOutcome"] = "unhandled"
                    core_.session_controller.close_response(assignment, "unhandled")
                    core_.session_controller.safe_pause(str(capture_outcome))
                    acknowledge("unhandled")
                    return
            # Never put a child's transcript in Scene/TurnContext/MCP state.
            # It is graded in-memory below and then discarded.
            core_.store.set_overlay(listening=False)
            core_.bus.publish("scene.update", core_.store.scene)
            outcome = await core_.runner.handle_interaction("speech", normalized)
            if assignment is not None and outcome is not None:
                core_.session_controller.close_response(assignment, outcome)
            acknowledge(outcome or "rejected")
            return
        if core_.runner is None:
            return
        normalized = dict(payload)
        assignment = None
        if core_.session_controller is not None:
            try:
                assignment = await core_.session_controller.claim_response(normalized)
            except AssignmentRejected as exc:
                core_.bus.send(sub, "error", {"code": "invalid_response_capability", "message": str(exc)[:240]})
                return
            normalized["_coreStudentId"] = assignment.target
            normalized["_responseTurnId"] = assignment.response_turn_id
            normalized["_evidencePolicy"] = assignment.evidence_policy
        outcome = await core_.runner.handle_interaction(interaction_kind(type_), normalized)
        if assignment is not None and outcome is not None:
            core_.session_controller.close_response(assignment, outcome)

    # ---------------------------------------------------------------- dev
    if settings.dev_endpoints:

        @app.post("/dev/scene")
        async def dev_scene(body: DevScene) -> dict[str, Any]:
            """Push a Scene straight onto the board. The UI's lifeline before the agent exists."""
            core_ = get_core()
            overlay = SceneOverlay.model_validate(body.overlay) if body.overlay else None
            scene = core_.store.set_scene(body.kind, body.props, overlay)
            core_.bus.publish("scene.update", core_.store.scene)
            return {
                "ok": True,
                "stateVersion": core_.store.state_version,
                "scene": to_wire(scene),
            }

        @app.post("/dev/say")
        async def dev_say(body: DevSay) -> dict[str, Any]:
            core_ = get_core()
            turn_id = body.turn_id or f"dev:{core_.store.state_version}:{id(body) & 0xFFFF}"
            payload: dict[str, Any] = {"text": body.text, "turnId": turn_id}
            if body.audio_asset:
                payload["audioAsset"] = body.audio_asset
            core_.bus.publish("speech.say", payload)
            if body.act:
                core_.bus.publish("avatar.act", body.act)
            return {"ok": True, "turnId": turn_id, "clients": core_.bus.connection_count}

        @app.post("/dev/cancel")
        async def dev_cancel(turn_id: str = "") -> dict[str, Any]:
            core_ = get_core()
            core_.bus.publish("speech.cancel", {"turnId": turn_id})
            return {"ok": True}

        @app.post("/dev/lesson/start")
        async def dev_lesson_start(body: DevStart | None = None) -> dict[str, Any]:
            core_ = get_core()
            body = body or DevStart()
            return await core_.start_lesson(body.index, body.student_id, body.student_name)

        @app.post("/dev/lesson/control")
        async def dev_lesson_control(body: DevControl) -> dict[str, Any]:
            core_ = get_core()
            if core_.runner is None:
                raise HTTPException(status_code=409, detail="no lesson_run loaded")
            if core_.session_controller is not None:
                return await core_.session_controller.control(body.cmd, body.arg)
            return await core_.runner.control(body.cmd, body.arg)

        @app.post("/dev/interaction")
        async def dev_interaction(body: DevInteraction) -> dict[str, Any]:
            core_ = get_core()
            if core_.runner is None:
                raise HTTPException(status_code=409, detail="no lesson_run loaded")
            outcome = await core_.runner.handle_interaction(
                interaction_kind(body.type), body.payload
            )
            return {"ok": True, "outcome": outcome, "index": core_.runner.index}

        @app.post("/dev/mode")
        async def dev_mode(body: DevMode) -> dict[str, Any]:
            core_ = get_core()
            mode = body.mode.upper()
            if mode not in ("FULL", "DEGRADED", "OFFLINE"):
                raise HTTPException(status_code=422, detail="mode must be FULL/DEGRADED/OFFLINE")
            changed = core_.modes.apply(mode, body.reason)  # type: ignore[arg-type]
            return {"ok": True, "changed": changed, "mode": core_.store.mode}

        @app.get("/dev/agent/actions")
        async def dev_agent_actions() -> Any:
            """What core would offer the agent right now. No model involved."""
            from agent_bridge import available_actions, build_turn_context

            core_ = get_core()
            ctx = build_turn_context(core_)
            return {
                "stateVersion": ctx.state_version,
                "sceneKind": ctx.scene.kind,
                "availableActions": [
                    a.model_dump(by_alias=True) for a in available_actions(core_)
                ],
            }

        @app.post("/dev/agent/turn")
        async def dev_agent_turn(body: dict[str, Any] | None = None) -> Any:
            """Give the agent exactly one turn, right now.

            Turns are automatic now (the runner's decision gate), but the hand
            pull stays: it is the only way to watch one turn in isolation,
            with a chosen `lastInteraction`, without playing a whole lesson.
            """
            core_ = get_core()
            driver = core_.agent_driver
            if driver is None:
                raise HTTPException(
                    status_code=503,
                    detail="no agent wired; start core with BRIGHT_AGENT=1 and LLM_API_KEY set",
                )
            payload = body or {}
            last = None
            if payload.get("lastInteraction"):
                from bright_contracts import LastInteraction

                last = LastInteraction(**payload["lastInteraction"])
            only = payload.get("only")
            result = await driver.take_turn(
                last_interaction=last,
                student_id=payload.get("studentId") or core_.student_id,
                recall_query=payload.get("recallQuery"),
                only=tuple(only) if only else None,
            )
            return {
                **result.as_dict(),
                "indexAfter": core_.runner.index,
                "sceneAfter": core_.store.scene.kind,
            }

        @app.post("/dev/session/summarize")
        async def dev_session_summarize(body: dict[str, Any] | None = None) -> Any:
            """Run `summarize_session` now instead of 30 s after the bell.

            The job is scheduled, not synchronous, so without this there is no
            way to watch the memory loop close inside one sitting.
            """
            core_ = get_core()
            session_id = (body or {}).get("sessionId")
            if not session_id:
                raise HTTPException(status_code=422, detail="sessionId is required")
            summary = await core_.jobs.summarize_session(str(session_id))
            return {"ok": summary is not None, "summary": summary}

        @app.get("/dev/lesson")
        async def dev_lesson() -> Any:
            core_ = get_core()
            if core_.lesson is None:
                raise HTTPException(status_code=404, detail="no lesson_run loaded")
            return JSONResponse(to_wire(core_.lesson))

        @app.get("/dev/state")
        async def dev_state() -> dict[str, Any]:
            core_ = get_core()
            return {
                "mode": core_.store.mode,
                "stateVersion": core_.store.state_version,
                "clients": core_.bus.connection_count,
                # PROTOCOL §9.8: "the round trip is worth surfacing on the
                # facilitator console. A link at 400 ms is still working; a
                # link at 4 s is about to fail, and a teacher deserves that
                # warning before the room notices."
                "links": [
                    {
                        "id": s.id,
                        "role": s.role,
                        "seq": s.seq,
                        "heartbeats": s.heartbeats,
                        "acks": s.acks,
                        "rttMs": round(s.rtt_ms, 1) if s.rtt_ms is not None else None,
                        "silentForS": round(s.silent_for(), 2)
                        if s.silent_for() is not None
                        else None,
                        "speaksHeartbeat": s.speaks_heartbeat,
                    }
                    for s in core_.bus.subscribers
                ],
                "sessionId": core_.session_id,
                "studentId": core_.student_id,
                "runner": {
                    "loaded": core_.runner is not None,
                    "index": core_.runner.index if core_.runner else -1,
                    "running": core_.runner.running if core_.runner else False,
                    "paused": core_.runner.paused if core_.runner else False,
                    "lastOutcome": core_.runner.last_outcome if core_.runner else None,
                    "lastLatencyMs": round(core_.runner.last_latency_ms, 3)
                    if core_.runner
                    else None,
                    "gated": core_.runner is not None and core_.runner.decide_next is not None,
                },
                "agent": (
                    {**core_.auto_turn.stats(), "skippedBusy": core_.agent_driver.skipped}
                    if core_.auto_turn is not None
                    else None
                ),
                "jobs": core_.jobs.jobs(),
                "snapshot": to_wire(core_.store.snapshot()),
                "recentEvents": core_.bus.history[-20:],
            }

        @app.get("/dev/recall")
        async def dev_recall(q: str, k: int = 5) -> dict[str, Any]:
            core_ = get_core()
            return {"query": q, "results": to_wire(core_.db.recall(q, k))}

    return app


def _parse(raw: str) -> dict[str, Any] | None:
    try:
        value = json.loads(raw)
    except (ValueError, TypeError):
        return None
    return value if isinstance(value, dict) else None


app = create_app()


def main() -> None:  # pragma: no cover - process entrypoint
    import uvicorn

    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO)
    uvicorn.run(
        "app:app",
        host="127.0.0.1",  # loopback only, always
        port=settings.port,
        reload=False,
        log_level="info",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
