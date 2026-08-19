"""Configuration for classroom-core.

Everything is read from ``os.environ`` with defaults (never from ``.env``
directly -- the process manager is responsible for loading that file).

This module also installs the ``bright_contracts`` import shim: the contracts
package at ``packages/contracts/python`` is not a distributable (no
pyproject.toml), so it is put on ``sys.path`` here rather than copied.  Import
this module before ``bright_contracts`` anywhere in the service.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]


def _install_contracts_path() -> Path | None:
    """Put packages/contracts/python on sys.path. Idempotent."""
    candidates = []
    env_path = os.environ.get("BRIGHT_CONTRACTS_PATH")
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(REPO_ROOT / "packages" / "contracts" / "python")
    for candidate in candidates:
        candidate = candidate.resolve()
        if (candidate / "bright_contracts" / "__init__.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            return candidate
    return None


CONTRACTS_PATH = _install_contracts_path()


def _env(name: str, default: str) -> str:
    value = os.environ.get(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    try:
        return int(_env(name, str(default)))
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    try:
        return float(_env(name, str(default)))
    except ValueError:
        return default


def _env_bool(name: str, default: bool) -> bool:
    return _env(name, "1" if default else "0").strip().lower() in ("1", "true", "yes", "on")


def _resolve(raw: str, base: Path) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else (base / path).resolve()


@dataclass(slots=True)
class Settings:
    # --- network -----------------------------------------------------------
    host: str = "127.0.0.1"          # bind loopback only, always
    port: int = 8004

    # --- paths -------------------------------------------------------------
    assets_dir: Path = field(default_factory=lambda: HERE / "assets")
    # Who the room opens for when nothing else says. NS-7: the deployment
    # declares its own roster; software must not carry a child's name. This is
    # the single-learner scaffold until a real roster exists, and it is a
    # setting so a second deployment changes a declaration, not code.
    default_learner_id: str = "learner-1"
    default_learner_name: str = "Learner"
    data_dir: Path = field(default_factory=lambda: HERE / "data")
    db_path: Path = field(default_factory=lambda: HERE / "data" / "bright.db")
    lesson_run_path: Path = field(default_factory=lambda: HERE / "data" / "sample_lesson_run.json")

    # --- behaviour ---------------------------------------------------------
    dev_endpoints: bool = True
    autostart_lesson: bool = False
    hello_timeout_s: float = 10.0
    queue_maxsize: int = 512

    # --- liveness (PROTOCOL §9.8) ------------------------------------------
    #: How often the server proves the link is alive, to every subscriber,
    #: regardless of other traffic. The client's own deadline is 12 s, so this
    #: has to stay comfortably below it.
    heartbeat_interval_s: float = 5.0
    #: No `heartbeat.ack` for this long => drop the subscriber and reclaim its
    #: queue. Only armed once a client has acked at least once; see
    #: ``app._heartbeat``.
    heartbeat_dead_s: float = 15.0

    # runner
    silence_timeout_s: float = 15.0
    reveal_hold_s: float = 1.2
    #: Minimum calibrated ASR confidence for an exact transcript to be called
    #: correct. Missing/low confidence is deliberately uncertain (``near``).
    speech_correct_confidence: float = 0.75
    playback_ack_timeout_s: float = 10.0
    #: Maximum time for the answer station to become ready *and start* the
    #: exact capture requested by Core. It is deliberately separate from the
    #: speech-onset/VAD budget, which begins only after capture.started.
    capture_ready_timeout_s: float = 20.0

    # modes
    mode_override: str | None = None          # pin FULL/DEGRADED/OFFLINE for dev
    full_max_latency_s: float = 3.0
    degraded_max_latency_s: float = 10.0
    recover_after: int = 2
    #: Consecutive failed live agent turns before the mode drops, without
    #: waiting up to `probe_interval_s` for the probe to notice.
    degrade_after: int = 2
    #: After a turn-driven demotion, how soon the next probe is pulled forward.
    recheck_after_s: float = 5.0

    # agent
    #: How long the runner will wait for the agent's decision after grading,
    #: before taking the authored branch. The class is the clock here: this is
    #: a promise about how long a child may stare at a frozen board, not a
    #: budget the model is entitled to spend.
    agent_turn_timeout_s: float = 6.0
    #: The greeting runs before the first activity, so nobody is waiting on a
    #: board -- it can afford the full say-then-choose round trip.
    agent_greeting_timeout_s: float = 12.0
    #: What learner context may leave Core. ``hosted-minimal`` is the safe
    #: default for an internet provider: no real learner identity or recalled
    #: notes. ``local-trusted`` is reserved for a loopback model deployment.
    agent_context_policy: str = "hosted-minimal"
    #: Provider-bound data policy. Synthetic transcripts require an explicit
    #: two-part development guard; hosted production is semantic-only.
    data_policy: str = "hosted_semantic"
    synthetic_dev_confirmed: bool = False
    #: Explicit operator acknowledgement for sending the current adult/test
    #: transcript to a hosted teacher model. It never relaxes durable storage.
    hosted_raw_confirmed: bool = False
    #: Acceptance profile is strict: missing live capabilities are a failed
    #: product proof rather than permission to silently use authored fallback.
    run_profile: str = "resilient"
    #: Shared loopback bearer capability for the Hermes -> Core MCP hop.  An
    #: empty value disables MCP rather than exposing an unauthenticated tool
    #: surface.
    mcp_token: str = ""

    # scheduler
    probe_interval_s: int = 60
    summary_delay_s: int = 30
    prepare_next_hour: int = 3

    cors_origins: tuple[str, ...] = (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )

    @classmethod
    def from_env(cls) -> "Settings":
        data_dir = _resolve(_env("DATA_DIR", str(HERE / "data")), REPO_ROOT)
        assets_raw = os.environ.get("ASSETS_DIR") or ""
        assets_dir = _resolve(assets_raw, REPO_ROOT) if assets_raw else (HERE / "assets")
        mode_override = os.environ.get("CORE_MODE") or None
        if mode_override:
            mode_override = mode_override.strip().upper()
            if mode_override not in ("FULL", "DEGRADED", "OFFLINE"):
                mode_override = None
        origins = os.environ.get("CORE_CORS_ORIGINS")
        ui_port = _env("UI_PORT", "3000")
        default_origins = (
            f"http://localhost:{ui_port}",
            f"http://127.0.0.1:{ui_port}",
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        )
        return cls(
            host="127.0.0.1",  # deliberately not configurable: loopback only
            port=_env_int("CORE_PORT", 8004),
            assets_dir=assets_dir,
            data_dir=data_dir,
            db_path=_resolve(_env("CORE_DB_PATH", str(data_dir / "bright.db")), REPO_ROOT),
            default_learner_id=_env("CORE_DEFAULT_LEARNER_ID", "learner-1"),
            default_learner_name=_env("CORE_DEFAULT_LEARNER_NAME", "Learner"),
            lesson_run_path=_resolve(
                _env("CORE_LESSON_RUN", str(HERE / "data" / "sample_lesson_run.json")), REPO_ROOT
            ),
            dev_endpoints=_env_bool("CORE_DEV", True),
            autostart_lesson=_env_bool("CORE_AUTOSTART_LESSON", False),
            hello_timeout_s=_env_float("CORE_HELLO_TIMEOUT_S", 10.0),
            queue_maxsize=_env_int("CORE_QUEUE_MAXSIZE", 512),
            heartbeat_interval_s=_env_float("CORE_HEARTBEAT_INTERVAL_S", 5.0),
            heartbeat_dead_s=_env_float("CORE_HEARTBEAT_DEAD_S", 15.0),
            silence_timeout_s=_env_float("CORE_SILENCE_TIMEOUT_S", 15.0),
            reveal_hold_s=_env_float("CORE_REVEAL_HOLD_S", 1.2),
            speech_correct_confidence=max(
                0.0, min(1.0, _env_float("CORE_SPEECH_CORRECT_CONFIDENCE", 0.75))
            ),
            playback_ack_timeout_s=max(
                0.1, _env_float("CORE_PLAYBACK_ACK_TIMEOUT_S", 10.0)
            ),
            capture_ready_timeout_s=max(
                1.0, _env_float("CORE_CAPTURE_READY_TIMEOUT_S", 20.0)
            ),
            mode_override=mode_override,
            full_max_latency_s=_env_float("CORE_FULL_MAX_LATENCY_S", 3.0),
            degraded_max_latency_s=_env_float("CORE_DEGRADED_MAX_LATENCY_S", 10.0),
            recover_after=_env_int("CORE_RECOVER_AFTER", 2),
            degrade_after=_env_int("CORE_DEGRADE_AFTER", 2),
            recheck_after_s=_env_float("CORE_RECHECK_AFTER_S", 5.0),
            agent_turn_timeout_s=_env_float("AGENT_TURN_TIMEOUT_S", 6.0),
            agent_greeting_timeout_s=_env_float(
                "AGENT_GREETING_TIMEOUT_S", _env_float("AGENT_TURN_TIMEOUT_S", 6.0) * 2.0
            ),
            agent_context_policy=(
                "local-trusted"
                if _env("AGENT_CONTEXT_POLICY", "hosted-minimal").strip().lower()
                == "local-trusted"
                else "hosted-minimal"
            ),
            data_policy=_env("BRIGHT_DATA_POLICY", "hosted_semantic").strip().lower(),
            synthetic_dev_confirmed=_env_bool("BRIGHT_SYNTHETIC_DEV_ACK", False),
            hosted_raw_confirmed=_env_bool("BRIGHT_HOSTED_RAW_ACK", False),
            run_profile=_env("BRIGHT_RUN_PROFILE", "resilient").strip().lower(),
            mcp_token=os.environ.get("BRIGHT_MCP_TOKEN", ""),
            probe_interval_s=_env_int("CORE_PROBE_INTERVAL_S", 60),
            summary_delay_s=_env_int("CORE_SUMMARY_DELAY_S", 30),
            prepare_next_hour=_env_int("CORE_PREPARE_NEXT_HOUR", 3),
            cors_origins=tuple(o.strip() for o in origins.split(",") if o.strip())
            if origins
            else default_origins,
        )


__all__ = ["Settings", "CONTRACTS_PATH", "HERE", "REPO_ROOT"]
