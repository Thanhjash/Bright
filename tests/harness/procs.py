"""Starting and stopping the real services, on ports the demo does not use.

Everything here spawns a real process and talks to it over the network. There
are no in-process app instances and no `TestClient`: 293 unit tests already
passed against in-process objects while four bugs sat in the seams between
processes, and an in-process fixture cannot see a seam.

Ports are always allocated fresh, and `RESERVED_PORTS` in `net.py` keeps the
suite off `:3000`, `:8001` and `:8004` so a running demo is never disturbed.
Processes are killed by the PID we spawned, or by resolving the PID from the
port -- **never** with `pkill -f`, which matches the suite's own command line.
"""

from __future__ import annotations

import json
import os
import shutil
import signal
import subprocess
import sys
import time
import urllib.request
from pathlib import Path
from typing import Any

from .net import free_port, kill_by_port, wait_for_http, wait_for_port, wait_for_port_closed

TESTS_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = TESTS_DIR.parent
ARTIFACTS = TESTS_DIR / ".artifacts"
CORE_DIR = REPO_ROOT / "services" / "classroom-core"
UI_DIR = REPO_ROOT / "apps" / "classroom-ui"
TOOLS_DIR = REPO_ROOT / ".tools"

#: The core service's own venv -- it is the only interpreter guaranteed to have
#: apscheduler, fastapi, uvicorn and httpx together.
CORE_PY = CORE_DIR / ".venv" / "bin" / "python"
#: The interpreter running the suite; used for the harness's own fake servers.
HARNESS_PY = sys.executable

CHROME_PATH = Path(
    os.environ.get(
        "BRIGHT_CHROME",
        str(Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome"),
    )
)


def _log_path(name: str) -> Path:
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    return ARTIFACTS / f"{name}.log"


def _post_json(url: str, payload: Any, timeout: float = 10.0) -> Any:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url, data=data, headers={"content-type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
    return json.loads(raw) if raw else None


def _get_json(url: str, timeout: float = 10.0) -> Any:
    with urllib.request.urlopen(url, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


class Managed:
    """A spawned process with a port, a log file and an honest shutdown."""

    name = "proc"

    def __init__(self, port: int) -> None:
        self.port = port
        self.proc: subprocess.Popen[bytes] | None = None
        self.log = _log_path(self.name)

    def _spawn(self, argv: list[str], env: dict[str, str], cwd: Path) -> None:
        self.log.parent.mkdir(parents=True, exist_ok=True)
        handle = open(self.log, "ab")
        handle.write(f"\n\n===== {time.strftime('%H:%M:%S')} {' '.join(argv)} =====\n".encode())
        handle.flush()
        self.proc = subprocess.Popen(
            argv,
            cwd=str(cwd),
            env=env,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
        )

    @property
    def pid(self) -> int | None:
        return self.proc.pid if self.proc else None

    def alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def stop(self, *, hard: bool = False) -> None:
        """Stop by PID (ours) and verify the port actually freed."""
        if self.proc and self.proc.poll() is None:
            sig = signal.SIGKILL if hard else signal.SIGTERM
            try:
                os.killpg(os.getpgid(self.proc.pid), sig)
            except (ProcessLookupError, PermissionError, OSError):
                try:
                    self.proc.send_signal(sig)
                except Exception:  # noqa: BLE001
                    pass
            try:
                self.proc.wait(timeout=8)
            except subprocess.TimeoutExpired:
                try:
                    os.killpg(os.getpgid(self.proc.pid), signal.SIGKILL)
                except Exception:  # noqa: BLE001
                    pass
        if not wait_for_port_closed(self.port, timeout=8):
            kill_by_port(self.port)
        self.proc = None

    def tail(self, lines: int = 40) -> str:
        if not self.log.exists():
            return ""
        return "\n".join(self.log.read_text(errors="replace").splitlines()[-lines:])


# ------------------------------------------------------------------ fake LLM


class FakeLLM(Managed):
    """The scripted model endpoint. Killing this process *is* killing the agent."""

    name = "fake-llm"

    def __init__(self, port: int | None = None) -> None:
        super().__init__(port or free_port())

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}/v1"

    def start(self) -> "FakeLLM":
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self._spawn(
            [HARNESS_PY, str(TESTS_DIR / "harness" / "servers" / "fake_llm.py"), "--port", str(self.port)],
            env,
            TESTS_DIR,
        )
        if not wait_for_http(f"http://127.0.0.1:{self.port}/health", timeout=30):
            raise RuntimeError(f"fake-llm never became healthy\n{self.tail()}")
        return self

    def script(
        self,
        responses: list[dict[str, Any]],
        reset_requests: bool = True,
        non_stream: dict[str, Any] | None = None,
    ) -> None:
        body: dict[str, Any] = {"responses": responses, "resetRequests": reset_requests}
        if non_stream:
            body["nonStream"] = non_stream
        _post_json(f"http://127.0.0.1:{self.port}/__script", body)

    def requests(self) -> list[dict[str, Any]]:
        """Streaming (teaching-turn) requests only."""
        return _get_json(f"http://127.0.0.1:{self.port}/__requests")["requests"]

    def request_count(self) -> int:
        return _get_json(f"http://127.0.0.1:{self.port}/__requests")["count"]

    def prompts(self) -> list[str]:
        """Every streamed turn's messages, flattened to searchable text."""
        return [json.dumps(r["body"].get("messages") or []) for r in self.requests()]


# ------------------------------------------------------------------ fake TTS


class FakeTTS(Managed):
    name = "fake-tts"

    def __init__(self, port: int | None = None) -> None:
        super().__init__(port or free_port())

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self) -> "FakeTTS":
        env = dict(os.environ)
        env["PYTHONUNBUFFERED"] = "1"
        self._spawn(
            [HARNESS_PY, str(TESTS_DIR / "harness" / "servers" / "fake_tts.py"), "--port", str(self.port)],
            env,
            TESTS_DIR,
        )
        if not wait_for_http(f"http://127.0.0.1:{self.port}/health", timeout=30):
            raise RuntimeError(f"fake-tts never became healthy\n{self.tail()}")
        return self

    def spoken(self) -> list[dict[str, Any]]:
        return _get_json(f"{self.base_url}/__spoken")["spoken"]

    def spoken_text(self) -> list[str]:
        return [str(s.get("input") or "") for s in self.spoken()]

    def reset(self) -> None:
        _post_json(f"{self.base_url}/__spoken/reset", {})


# ---------------------------------------------------------------------- core


class Core(Managed):
    """`services/classroom-core`, on its own port, with its own SQLite file.

    `DATA_DIR`/`CORE_DB_PATH` are redirected into `tests/.artifacts` so the
    suite can never write to the demo's database -- which matters most for I8,
    where the whole point is that memory starts empty and is written by the
    test.
    """

    name = "core"

    def __init__(self, port: int | None = None, data_name: str = "core") -> None:
        super().__init__(port or free_port())
        self.data_dir = ARTIFACTS / f"data-{data_name}"
        self.env_extra: dict[str, str] = {}
        self.log = _log_path(f"core-{self.port}")

    @property
    def http(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def ws(self) -> str:
        return f"ws://127.0.0.1:{self.port}/ws"

    def wipe_data(self) -> None:
        if self.data_dir.exists():
            shutil.rmtree(self.data_dir, ignore_errors=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def start(
        self,
        *,
        agent: bool = False,
        llm_base_url: str | None = None,
        wipe: bool = False,
        extra_env: dict[str, str] | None = None,
        ui_origin: str | None = None,
    ) -> "Core":
        if wipe:
            self.wipe_data()
        self.data_dir.mkdir(parents=True, exist_ok=True)

        env = dict(os.environ)
        # Strip anything inherited that would point core at the live demo.
        for key in list(env):
            if key.startswith(("CORE_", "LLM_", "BRIGHT_AGENT")):
                env.pop(key, None)

        env.update(
            {
                "PYTHONUNBUFFERED": "1",
                "CORE_PORT": str(self.port),
                "CORE_DEV": "1",
                "DATA_DIR": str(self.data_dir),
                "CORE_DB_PATH": str(self.data_dir / "bright.db"),
                "CORE_AUTOSTART_LESSON": "0",
                # Effectively off. A background probe that moves the mode
                # mid-test makes every gate-sensitive assertion depend on
                # wall-clock luck; tests that care about the mode either pin it
                # or use their own core with a short interval.
                "CORE_PROBE_INTERVAL_S": "3600",
                "CORE_SUMMARY_DELAY_S": "2",
                "CORE_CORS_ORIGINS": ",".join(
                    filter(
                        None,
                        [
                            ui_origin,
                            "http://127.0.0.1:3000",
                            "http://localhost:3000",
                        ],
                    )
                ),
            }
        )
        if agent:
            env["BRIGHT_AGENT"] = "1"
            env["LLM_API_KEY"] = "test-key"
            env["LLM_MODEL"] = "fake-model"
            env["LLM_BASE_URL"] = llm_base_url or "http://127.0.0.1:1/v1"
            # Bounded, so an unreachable model cannot hold a test hostage --
            # and so I9 measures a real ceiling rather than a hang.
            env["LLM_TIMEOUT_S"] = env.get("LLM_TIMEOUT_S", "8")
            env["AGENT_TURN_TIMEOUT_S"] = env.get("AGENT_TURN_TIMEOUT_S", "5")
        env.update(self.env_extra)
        env.update(extra_env or {})

        py = str(CORE_PY) if CORE_PY.exists() else HARNESS_PY
        self._spawn([py, str(CORE_DIR / "app.py")], env, CORE_DIR)
        if not wait_for_http(f"{self.http}/health", timeout=60):
            raise RuntimeError(f"core never became healthy on :{self.port}\n{self.tail()}")
        return self

    # ---------------------------------------------------------------- dev API

    def state(self) -> dict[str, Any]:
        return _get_json(f"{self.http}/dev/state")

    def health(self) -> dict[str, Any]:
        return _get_json(f"{self.http}/health")

    def lesson(self) -> dict[str, Any]:
        return _get_json(f"{self.http}/dev/lesson")

    def start_lesson(
        self, index: int = 0, student_id: str | None = None, student_name: str | None = None
    ) -> Any:
        body: dict[str, Any] = {"index": index}
        if student_id:
            body["studentId"] = student_id
        if student_name:
            body["studentName"] = student_name
        return _post_json(f"{self.http}/dev/lesson/start", body)

    def summarize(self, session_id: str) -> Any:
        return _post_json(f"{self.http}/dev/session/summarize", {"sessionId": session_id}, timeout=45)

    def control(self, cmd: str, arg: str | None = None) -> Any:
        return _post_json(f"{self.http}/dev/lesson/control", {"cmd": cmd, "arg": arg})

    def interaction(self, type_: str, payload: dict[str, Any]) -> Any:
        return _post_json(f"{self.http}/dev/interaction", {"type": type_, "payload": payload})

    def agent_actions(self) -> dict[str, Any]:
        return _get_json(f"{self.http}/dev/agent/actions")

    def agent_turn(self, body: dict[str, Any] | None = None, timeout: float = 60.0) -> Any:
        return _post_json(f"{self.http}/dev/agent/turn", body or {}, timeout=timeout)

    def recall(self, query: str, k: int = 5) -> Any:
        import urllib.parse

        q = urllib.parse.quote(query)
        return _get_json(f"{self.http}/dev/recall?q={q}&k={k}")

    def set_mode(self, mode: str, reason: str = "test") -> Any:
        return _post_json(f"{self.http}/dev/mode", {"mode": mode, "reason": reason})


# ------------------------------------------------------------------------ UI


class Ui(Managed):
    """The Vite dev server for `apps/classroom-ui`.

    Dev, not preview: `window.__bright` (the Zustand store handle) only exists
    under `import.meta.env.DEV`, and asserting store state is the whole reason
    the browser tests are trustworthy instead of pixel-scraping.

    Vite folds `process.env.VITE_*` into `import.meta.env`, so the bus, core
    HTTP origin and speech endpoint are all repointable without touching a file
    in `apps/`.
    """

    name = "ui"

    def __init__(self, port: int | None = None) -> None:
        super().__init__(port or free_port())

    @property
    def origin(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def start(self, *, bus_url: str, core_http: str, speech_url: str) -> "Ui":
        env = dict(os.environ)
        env.update(
            {
                "VITE_BUS_URL": bus_url,
                "VITE_CORE_HTTP": core_http,
                "VITE_SPEECH_URL": speech_url,
                "VITE_MOCK": "0",
                "BROWSER": "none",
                "CI": "1",
            }
        )
        pnpm = shutil.which("pnpm") or "pnpm"
        self._spawn(
            [pnpm, "exec", "vite", "--port", str(self.port), "--strictPort", "--host", "127.0.0.1"],
            env,
            UI_DIR,
        )
        if not wait_for_port(self.port, timeout=180):
            raise RuntimeError(f"ui dev server never listened on :{self.port}\n{self.tail()}")
        if not wait_for_http(f"{self.origin}/classroom", timeout=180):
            raise RuntimeError(f"ui never served /classroom\n{self.tail()}")
        return self
