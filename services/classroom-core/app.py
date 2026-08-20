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
from typing import Any

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

import config  # noqa: F401  -- installs the bright_contracts import path
from bright_contracts import (
    CapabilityReportPayload,
    PROTOCOL_VERSION,
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
from leases import AssignmentRejected, CapabilityLeaseRegistry
from db import Database, open_database
from modes import ModeController
from mcp_server import TurnRegistry, build_mcp_router
from scheduler import AgentSeam, BackgroundJobs
from state import StateStore

log = logging.getLogger("classroom_core")

def _speech_service_up() -> bool:
    """Adult status only. A dead speaker must not invent a teacher line."""
    import urllib.error
    import urllib.request

    url = os.environ.get("SPEECH_URL", "http://127.0.0.1:8001").rstrip("/") + "/health"
    try:
        with urllib.request.urlopen(url, timeout=0.4) as resp:
            return int(getattr(resp, "status", 0) or 0) == 200
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        return False


CLIENT_EVENTS = {
    "client.hello",
    "heartbeat.ack",
    "student.speech.final",
    "speech.playback.started",
    "speech.playback.finished",
    "speech.barge_in",
    "capability.report",
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
    session_id: str | None = None
    #: Whose lesson this is. Phase 1 runs one named child at a time; the class
    #: is on the board, the student model is about the child being checked.
    student_id: str | None = None
    seam: AgentSeam = field(default_factory=AgentSeam)
    #: The live teacher agent, set only when services/agent actually wired up.
    #: ``None`` means no teacher is available and no turn can be taken.
    agent: Any = None
    conversations: ConversationCoordinator = field(default_factory=ConversationCoordinator)
    turn_registry: Any = None
    capability_leases: CapabilityLeaseRegistry | None = None
    teacher_os: Any = None

    def set_agent_seam(self, seam: AgentSeam) -> None:
        """The one place services/agent plugs in. Never imported from here."""
        self.seam = seam
        self.jobs.set_seam(seam)

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
    # There is no lesson-graph position to check the request against any more;
    # the correlation that still matters is against the registered speech turn,
    # which ``request_barge_in`` does on its own.
    reply, changed = core.conversations.request_barge_in(
        request,
        activity_id=request.activity_id,
        activity_generation=request.activity_generation,
    )
    if changed:
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
    # Stage audio lease is OS floor.
    core.capability_leases = CapabilityLeaseRegistry(core)
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


class DevMode(BaseModel):
    mode: str
    reason: str = "set via /dev/mode"


# ------------------------------------------------------------------- app


def create_app(settings: Settings | None = None, core: Core | None = None) -> FastAPI:
    settings = settings or (core.settings if core else Settings.from_env())

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.core = core or build_core(settings)
        app.state.core.jobs.start()

        # The teacher agent is opt-in. Without it Core still serves the bus,
        # the leases and the assets, but no teacher turn can be taken. A
        # failure to wire it is logged and ignored, never fatal: a missing API
        # key must not stop the service from coming up.
        agent_mode = os.environ.get("BRIGHT_AGENT", "off").strip().lower()
        if agent_mode in {"1", "true", "yes", "on"}:
            agent_mode = "hermes"  # compatibility with the original switch
        strict_ideal = settings.run_profile == "ideal_hosted"
        if strict_ideal and agent_mode != "hermes":
            raise RuntimeError(
                "ideal_hosted requires BRIGHT_AGENT=hermes"
            )
        if agent_mode not in {"", "0", "false", "no", "off", "none"}:
            try:
                if agent_mode not in {"hermes", "relay"}:
                    raise ValueError(
                        f"unknown BRIGHT_AGENT={agent_mode!r}; use hermes, relay or off"
                    )
                core_: Core = app.state.core
                if agent_mode == "relay":
                    # A person where the model goes (NS-4: the runtime is
                    # replaceable). Deliberate opt-in only, and `ideal_hosted`
                    # already refused it above -- a classroom must never find
                    # itself waiting on a human who went home.
                    from bright_agent.relay import RelayAgent

                    core_.agent = RelayAgent(executor=None)
                    log.warning(
                        "[agent] RELAY: the brain is a person, not a model. "
                        "Reading %s", os.environ.get("BRIGHT_RELAY_DIR", ".runtime/.../relay")
                    )
                else:
                    from bright_agent.hermes import HermesAgent

                    core_.agent = HermesAgent()

                # The health seam. It measures the sidecar, never the model's
                # answer quality -- a probe that spends a turn would compete
                # with the teacher for the single hosted slot.
                async def _probe_hermes() -> float | None:
                    from teacher_os import hermes_up

                    started = time.perf_counter()
                    if not await asyncio.to_thread(hermes_up):
                        return None
                    return time.perf_counter() - started

                async def _prepare_next(_context: dict) -> dict | None:
                    """The nightly period draft. NORTH-STAR §2's BEFORE box.

                    A job that fails at 03:00 and says nothing is exactly the
                    papered-over failure the doctrine calls a defect, so the
                    outcome -- good or bad -- lands on /teacher/status where the
                    adult who boots the appliance can see it.
                    """
                    from library import list_units
                    from teacher_os import prepare_period

                    units = list_units()
                    if len(units) != 1:
                        # NS-7: Core never picks a favourite lesson. With none
                        # authored there is nothing to prepare; with several, an
                        # adult chooses.
                        outcome = {"ok": False, "error": f"{len(units)} units authored"}
                    else:
                        try:
                            outcome = await prepare_period(core_, unit_id=units[0])
                        except Exception as exc:  # noqa: BLE001
                            outcome = {"ok": False, "error": repr(exc)[:200]}
                    outcome["at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    core_.last_prepare = outcome
                    log.info("[prepare] %s", outcome)
                    return outcome

                core_.set_agent_seam(
                    AgentSeam(probe=_probe_hermes, prepare_next=_prepare_next)
                )
                log.info(
                    "[agent] wired: %s (turn timeout %.1fs)",
                    type(core_.agent).__name__,
                    settings.agent_turn_timeout_s,
                )
            except Exception as exc:  # noqa: BLE001
                if strict_ideal:
                    raise RuntimeError(
                        "ideal_hosted could not wire the pinned Hermes agent"
                    ) from exc
                log.warning("[agent] not wired (%s) -- no teacher turn can be taken", exc)
        from teacher_os import teacher_heartbeat_loop

        heartbeat_task = asyncio.create_task(teacher_heartbeat_loop(app.state.core))
        log.info(
            "classroom-core ready on %s:%s (mode=%s)",
            settings.host,
            settings.port,
            app.state.core.store.mode,
        )
        try:
            yield
        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass
            current: Core = app.state.core
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

    @app.get("/teacher/status")
    async def teacher_status() -> dict[str, Any]:
        from teacher_os import teacher_status_payload

        return teacher_status_payload(get_core())

    @app.post("/teacher/session")
    async def teacher_session(body: dict[str, Any] | None = None) -> dict[str, Any]:
        from teacher_os import start_teacher_session

        payload = body or {}
        # Core does not know which lesson this appliance teaches. If the caller
        # names a unit, use it; otherwise fall back to whatever is authored on
        # disk. A hardcoded unit id here is how "nothing in code knows which
        # lesson it is" quietly stops being true.
        from library import list_units

        units = list_units()
        default_unit = units[0] if len(units) == 1 else ""
        os_ = start_teacher_session(
            get_core(),
            unit_id=str(payload.get("unitId") or default_unit),
            learner_id=str(payload.get("learnerId") or core_.settings.default_learner_id),
            learner_name=str(payload.get("learnerName") or core_.settings.default_learner_name),
        )
        result: dict[str, Any] = {"ok": True, "unitId": os_.unit_id, "learnerId": os_.learner_id}
        if payload.get("open", True):
            from teacher_os import handle_teacher_turn

            result["opening"] = await handle_teacher_turn(get_core(), "[sat_down]")
        return result

    @app.post("/teacher/turn")
    async def teacher_turn(body: dict[str, Any] | None = None) -> dict[str, Any]:
        from teacher_os import handle_teacher_turn

        text = str((body or {}).get("text") or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="text is required")
        try:
            return await handle_teacher_turn(get_core(), text)
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    @app.post("/teacher/heartbeat")
    async def teacher_heartbeat(body: dict[str, Any] | None = None) -> dict[str, Any]:
        from teacher_os import pulse_teacher

        payload = body or {}
        return await pulse_teacher(
            get_core(),
            force=bool(payload.get("force")),
            reason=str(payload.get("reason") or "poke"),
        )

    @app.post("/teacher/identify")
    async def teacher_identify(payload: dict[str, Any]) -> dict[str, Any]:
        """A frame from the room's camera. Answers only "who", never "what next".

        The Stage sends this when it has a camera and a child in front of it.
        Core keeps the answer and uses it the next time it opens a class, so a
        recognised child gets their OWN recorded evidence instead of the
        deployment's default learner.

        Deliberately NOT on the teaching path: it does not start, stop or steer
        a lesson, and it is not reachable from any tool she has. It also never
        returns the frame, a face box, or an embedding -- the id and a
        confidence are the whole contract (NORTH-STAR: "Identity is the
        system's job, not the model's").
        """
        import base64
        import binascii

        import perception

        raw = str(payload.get("image_base64") or "")
        try:
            frame = base64.b64decode(raw, validate=True) if raw else b""
        except (binascii.Error, ValueError):
            raise HTTPException(400, "image_base64 is not valid base64")

        core_ = get_core()
        seen = perception.identify(frame)
        core_.identified_learner = seen
        if seen is None:
            # "We do not know" is a real answer and the room carries on with
            # the declared learner. It is never an error.
            return {"recognised": False, "studentId": None}
        log.info("identified %s (%.2f)", seen.student_id, seen.similarity)
        return {
            "recognised": True,
            "studentId": seen.student_id,
            "displayName": seen.display_name,
            "similarity": round(seen.similarity, 4),
        }

    @app.post("/teacher/prepare")
    async def teacher_prepare() -> dict[str, Any]:
        """Draft the period now instead of waiting for the nightly job.

        The adult who sets the appliance up in the morning may not have had it
        running at 03:00 -- a highland classroom loses power. Preparation that
        can only ever happen on a schedule would silently never happen.
        """
        core_ = get_core()
        # Through BackgroundJobs, not the seam directly: that is the path the
        # 03:00 trigger takes, and a hand-run that skips it would be testing
        # something the appliance never does.
        got = await core_.jobs.prepare_next({})
        return got or {"ok": False, "error": "no prepare seam wired"}

    @app.post("/teacher/pause")
    async def teacher_pause(body: dict[str, Any] | None = None) -> dict[str, Any]:
        """The adult holds the lesson.

        NORTH-STAR §1: the facilitator is the safety authority in the room, and
        that has been a sentence with no mechanism behind it. Every button on
        /control sent a WebSocket frame that was not in CLIENT_EVENTS, so it was
        rejected before any handler -- and there was no handler to reject it to.
        """
        core_ = get_core()
        core_.paused_by_adult = {
            "reason": str((body or {}).get("reason") or "facilitator_pause"),
            "at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        }
        log.warning("[control] the adult paused the lesson")
        return {"ok": True, "paused": core_.paused_by_adult}

    @app.post("/teacher/resume")
    async def teacher_resume() -> dict[str, Any]:
        """The adult gives the room back. Also the only thing that clears an
        escalation: she called for a person, and a person answering is the
        event that ends it. A machine deciding it has waited long enough would
        be the machine taking the role back."""
        core_ = get_core()
        core_.paused_by_adult = None
        core_.escalation = None
        os_ = getattr(core_, "teacher_os", None)
        if os_ is not None:
            os_.escalated = False
        log.warning("[control] the adult resumed the lesson")
        return {"ok": True}

    def readiness() -> tuple[dict[str, Any], bool]:
        """Return the product-facing readiness snapshot and verdict."""
        core_ = get_core()
        leases = core_.capability_leases
        if leases is not None:
            leases.expire()
        checks = {
            "stageAudioOwner": bool(leases and leases.stage_owner),
            "controlInputOwner": bool(leases and leases.control_input_owner),
            "agentConfigured": os.environ.get("BRIGHT_AGENT", "off").strip().lower()
            == "hermes",
            "agentFull": core_.store.mode == "FULL",
        }
        required = ("stageAudioOwner", "controlInputOwner")
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
            media = (config.REPO_ROOT / "content" / "media" / cleaned).resolve()
            media_root = (config.REPO_ROOT / "content" / "media").resolve()
            if media.is_relative_to(media_root) and media.is_file():
                target = media
            else:
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
                        "reason": "stage_audio_owner_ready",
                    },
                )
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
            if event == "finished" and changed:
                # Relay only the sanitized terminal state after role, lease,
                # schema, turn and playback-transition validation. This lets a
                # Control browser on another machine/profile open its mic
                # without trusting or fabricating a Stage ACK.
                if getattr(core_, "teacher_os", None) is not None:
                    core_.bus.publish(
                        "speech.playback.observed",
                        {"speechTurnId": speech_turn_id, "status": status},
                    )
            return

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

            # No lesson graph grades this any more: the teacher agent hears
            # the child over its own turn. Core only closes the UI's listening
            # state and acknowledges the utterance.
            acknowledge("rejected")
            return

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

        @app.post("/dev/mode")
        async def dev_mode(body: DevMode) -> dict[str, Any]:
            core_ = get_core()
            mode = body.mode.upper()
            if mode not in ("FULL", "DEGRADED", "OFFLINE"):
                raise HTTPException(status_code=422, detail="mode must be FULL/DEGRADED/OFFLINE")
            changed = core_.modes.apply(mode, body.reason)  # type: ignore[arg-type]
            return {"ok": True, "changed": changed, "mode": core_.store.mode}

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
                "agent": (
                    type(core_.agent).__name__ if core_.agent is not None else None
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
