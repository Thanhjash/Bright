#!/usr/bin/env python3
"""Deterministic process/socket smoke for the Bright Option B Core wire path.

The default command starts isolated Core, UI, and fake-speech processes on
fresh loopback ports. It uses production Core settings (``CORE_DEV=0``), no
Hermes and no secrets. Two Python WebSocket clients act as Stage and Control,
fabricate playback acknowledgements, answer the authored question, and require
the lesson to reach DONE. Vite is route-checked, but no browser, AIRI player,
TTS audio, ASR, or microphone path executes here.

This is deliberately a process/socket test, not a FastAPI TestClient test.
Run ``./scripts/product-smoke.sh --help`` for target and optional agent modes.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CORE_DIR = ROOT / "services" / "classroom-core"
UI_DIR = ROOT / "apps" / "classroom-ui"
FIXTURE = ROOT / "tests" / "fixtures" / "product_smoke_lesson.json"
FAKE_SPEECH = ROOT / "tests" / "harness" / "servers" / "fake_tts.py"
CORE_PY = CORE_DIR / ".venv" / "bin" / "python"
PROTOCOL_VERSION = 2


class SmokeFailure(RuntimeError):
    pass


class EnvironmentBlocked(SmokeFailure):
    """The host forbids a prerequisite (usually binding loopback sockets)."""


def _free_port() -> int:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            sock.bind(("127.0.0.1", 0))
            return int(sock.getsockname()[1])
    except PermissionError as exc:
        raise EnvironmentBlocked(f"loopback socket binding is forbidden: {exc}") from exc


def _json_get(url: str, timeout: float = 3.0) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _http_status(url: str, timeout: float = 3.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as response:
            response.read(256)
            return int(response.status)
    except urllib.error.HTTPError as exc:
        return int(exc.code)


def _wait_http(url: str, timeout: float) -> float:
    started = time.perf_counter()
    deadline = started + timeout
    last_error = "not attempted"
    while time.perf_counter() < deadline:
        try:
            if _http_status(url, timeout=1.0) == 200:
                return round((time.perf_counter() - started) * 1000, 1)
        except (OSError, ValueError, urllib.error.URLError) as exc:
            last_error = str(exc)
        time.sleep(0.1)
    raise SmokeFailure(f"{url} was not healthy within {timeout:.1f}s ({last_error})")


@dataclass
class ManagedProcess:
    name: str
    argv: list[str]
    cwd: Path
    env: dict[str, str]
    log_path: Path
    process: subprocess.Popen[bytes] | None = None

    def start(self) -> None:
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        handle = self.log_path.open("ab")
        handle.write((f"\n===== {datetime.now(timezone.utc).isoformat()} {self.name} =====\n").encode())
        handle.flush()
        try:
            self.process = subprocess.Popen(
                self.argv,
                cwd=self.cwd,
                env=self.env,
                stdin=subprocess.DEVNULL,
                stdout=handle,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
        except PermissionError as exc:
            handle.close()
            raise EnvironmentBlocked(f"cannot start {self.name}: {exc}") from exc
        finally:
            handle.close()

    def stop(self) -> None:
        process = self.process
        if process is None or process.poll() is not None:
            return
        try:
            os.killpg(os.getpgid(process.pid), signal.SIGTERM)
        except (OSError, ProcessLookupError):
            process.terminate()
        try:
            process.wait(timeout=6)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
            except (OSError, ProcessLookupError):
                process.kill()
            process.wait(timeout=3)

    def tail(self, lines: int = 30) -> str:
        if not self.log_path.exists():
            return ""
        return "\n".join(self.log_path.read_text(errors="replace").splitlines()[-lines:])


@dataclass
class WireClient:
    url: str
    role: str
    ws: Any = None
    events: list[dict[str, Any]] = field(default_factory=list)
    seq: int = 0
    state_version: int = 0
    incoming_seq: int = 0
    gaps: list[tuple[int, int]] = field(default_factory=list)
    version_regressions: list[tuple[int, int]] = field(default_factory=list)
    task: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        import websockets

        self.ws = await websockets.connect(self.url, open_timeout=5, max_queue=None)
        self.task = asyncio.create_task(self._pump())
        await self.send("client.hello", {"role": self.role})
        await self.wait_for("scene.snapshot", timeout=5)

    async def close(self) -> None:
        if self.ws is not None:
            await self.ws.close()
        if self.task is not None:
            self.task.cancel()
            try:
                await self.task
            except (asyncio.CancelledError, Exception):
                pass

    async def send(self, event_type: str, payload: dict[str, Any]) -> None:
        self.seq += 1
        await self.ws.send(
            json.dumps(
                {
                    "v": PROTOCOL_VERSION,
                    "type": event_type,
                    "seq": self.seq,
                    "stateVersion": self.state_version,
                    "ts": int(time.time() * 1000),
                    "payload": payload,
                },
                separators=(",", ":"),
            )
        )

    async def _pump(self) -> None:
        async for raw in self.ws:
            event = json.loads(raw)
            if int(event.get("v", -1)) != PROTOCOL_VERSION:
                raise SmokeFailure(f"{self.role} received protocol v={event.get('v')}")
            self.events.append(event)
            if event.get("type") == "heartbeat":
                await self.send("heartbeat.ack", {"ts": (event.get("payload") or {}).get("ts")})
                continue
            incoming = int(event.get("seq") or 0)
            if self.incoming_seq and incoming != self.incoming_seq + 1:
                self.gaps.append((self.incoming_seq, incoming))
            self.incoming_seq = incoming
            version = int(event.get("stateVersion") or 0)
            if version < self.state_version:
                self.version_regressions.append((self.state_version, version))
            self.state_version = max(self.state_version, version)

    async def wait_for(
        self,
        event_type: str,
        *,
        timeout: float,
        after: int = 0,
        predicate: Any = None,
    ) -> dict[str, Any]:
        deadline = time.perf_counter() + timeout
        cursor = after
        while time.perf_counter() < deadline:
            for event in self.events[cursor:]:
                if event.get("type") == event_type and (predicate is None or predicate(event)):
                    return event
            cursor = len(self.events)
            if self.task is not None and self.task.done():
                exc = self.task.exception()
                if exc:
                    raise SmokeFailure(f"{self.role} receive loop failed: {exc}") from exc
            await asyncio.sleep(0.01)
        seen = [event.get("type") for event in self.events[-12:]]
        raise SmokeFailure(f"{self.role} did not receive {event_type} in {timeout:.1f}s; saw {seen}")


async def _exercise_bus(ws_url: str, timeout: float) -> dict[str, Any]:
    stage = WireClient(ws_url, "stage")
    control = WireClient(ws_url, "control")
    started_at = time.perf_counter()
    first_speech_at: float | None = None
    choice_at: float | None = None
    choice_advanced_at: float | None = None
    speech_turns: set[str] = set()
    acked_turns: set[str] = set()
    answer_sent = False

    await stage.connect()
    await control.connect()
    try:
        stage_cursor = len(stage.events)
        await stage.send("lesson.start", {"requestId": "forbidden-stage-start"})
        await stage.wait_for(
            "error",
            timeout=3,
            after=stage_cursor,
            predicate=lambda e: (e.get("payload") or {}).get("code") == "forbidden",
        )

        control_cursor = len(control.events)
        await control.send("speech.playback.started", {"speechTurnId": "spoofed"})
        await control.wait_for(
            "error",
            timeout=3,
            after=control_cursor,
            predicate=lambda e: (e.get("payload") or {}).get("code") == "forbidden",
        )

        request_id = f"smoke-{int(time.time() * 1000)}"
        start_sent = time.perf_counter()
        await control.send(
            "lesson.start",
            {
                "requestId": request_id,
                "index": 0,
                "studentId": "smoke-learner",
                "studentName": "Smoke Learner",
            },
        )
        started = await control.wait_for(
            "lesson.started",
            timeout=timeout,
            predicate=lambda e: (e.get("payload") or {}).get("requestId") == request_id,
        )
        start_ack_ms = round((time.perf_counter() - start_sent) * 1000, 1)
        if (started.get("payload") or {}).get("lessonId") != "product-smoke-option-b":
            raise SmokeFailure("Core started a different lesson than the smoke fixture")

        cursor = 0
        deadline = time.perf_counter() + timeout
        while time.perf_counter() < deadline:
            batch = stage.events[cursor:]
            cursor = len(stage.events)
            for event in batch:
                event_type = event.get("type")
                payload = event.get("payload") or {}
                if event_type == "speech.turn.started":
                    turn_id = str(payload.get("speechTurnId") or "")
                    if turn_id:
                        speech_turns.add(turn_id)
                        if first_speech_at is None:
                            first_speech_at = time.perf_counter()
                elif event_type == "speech.turn.ended" and payload.get("status") == "completed":
                    turn_id = str(payload.get("speechTurnId") or "")
                    if turn_id and turn_id not in acked_turns:
                        await stage.send("speech.playback.started", {"speechTurnId": turn_id})
                        await stage.send(
                            "speech.playback.finished",
                            {
                                "speechTurnId": turn_id,
                                "status": "completed",
                                "metrics": {"firstAudioMs": 1.0, "durationMs": 10.0},
                            },
                        )
                        acked_turns.add(turn_id)
                elif event_type == "scene.update":
                    if payload.get("kind") == "choice" and not answer_sent:
                        answer_sent = True
                        choice_at = time.perf_counter()
                        await stage.send("interaction.choice", {"optionId": "sun"})
                    elif answer_sent and payload.get("kind") == "text" and payload.get("props", {}).get("text") == "Finished.":
                        choice_advanced_at = choice_advanced_at or time.perf_counter()
                elif event_type == "lesson.position" and payload.get("stage") == "DONE":
                    if not answer_sent:
                        raise SmokeFailure("lesson reached DONE without exercising the authored answer")
                    for client in (stage, control):
                        if client.gaps:
                            raise SmokeFailure(f"{client.role} observed seq gaps: {client.gaps}")
                        if client.version_regressions:
                            raise SmokeFailure(
                                f"{client.role} observed stateVersion regression: {client.version_regressions}"
                            )
                    spoken = [
                        str((event.get("payload") or {}).get("delta") or "")
                        for event in stage.events
                        if event.get("type") == "speech.text.delta"
                    ]
                    return {
                        "lessonStartAckMs": start_ack_ms,
                        "firstAuthoredSpeechMs": (
                            round((first_speech_at - start_sent) * 1000, 1)
                            if first_speech_at is not None
                            else None
                        ),
                        "answerToWrapMs": (
                            round((choice_advanced_at - choice_at) * 1000, 1)
                            if choice_at is not None and choice_advanced_at is not None
                            else None
                        ),
                        "lessonCompleteMs": round((time.perf_counter() - start_sent) * 1000, 1),
                        "speechTurns": len(speech_turns),
                        "playbackAcks": len(acked_turns),
                        "authoredText": "".join(spoken),
                        "stageEvents": len(stage.events),
                        "controlEvents": len(control.events),
                        "roleGuards": "passed",
                        "protocolVersion": PROTOCOL_VERSION,
                    }
            await asyncio.sleep(0.01)
        raise SmokeFailure(
            f"lesson did not reach DONE within {timeout:.1f}s; "
            f"last events={[event.get('type') for event in stage.events[-15:]]}"
        )
    finally:
        await stage.close()
        await control.close()


def _validate_args(args: argparse.Namespace) -> None:
    if args.agent == "hermes" and not args.core_url:
        required = ("HERMES_API_URL", "HERMES_API_KEY")
        missing = [name for name in required if not os.environ.get(name)]
        if missing:
            raise SmokeFailure(
                "--agent hermes needs an already-running pinned sidecar and "
                f"{', '.join(missing)}; values are never printed"
            )
    if args.core_url and args.agent != "off":
        raise SmokeFailure("--agent only controls a managed Core; omit it when targeting a stack")


def _artifact_dir(base: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
    target = base / stamp
    target.mkdir(parents=True, exist_ok=False)
    return target


def _write_result(path: Path, result: dict[str, Any]) -> None:
    path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    _validate_args(args)
    artifacts = _artifact_dir(Path(args.artifacts).resolve())
    processes: list[ManagedProcess] = []
    result: dict[str, Any] = {
        "status": "running",
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "artifacts": str(artifacts),
        "managed": {},
        "agent": args.agent if not args.core_url else "target-owned",
    }

    try:
        core_url = args.core_url.rstrip("/") if args.core_url else ""
        ui_url = args.ui_url.rstrip("/") if args.ui_url else ""
        speech_url = args.speech_url.rstrip("/") if args.speech_url else ""

        if not speech_url:
            speech_port = _free_port()
            speech_url = f"http://127.0.0.1:{speech_port}"
            speech = ManagedProcess(
                "fake-speech",
                [sys.executable, str(FAKE_SPEECH), "--port", str(speech_port)],
                ROOT,
                {**os.environ, "PYTHONUNBUFFERED": "1"},
                artifacts / "speech.log",
            )
            speech.start()
            processes.append(speech)
            result["managed"]["speech"] = True
        result["speechStartupMs"] = _wait_http(f"{speech_url}/health", args.startup_timeout)
        speech_health = _json_get(f"{speech_url}/health")
        if speech_health.get("status") != "ok":
            raise SmokeFailure(f"speech health is not ok: {speech_health}")

        if not core_url:
            if not CORE_PY.is_file():
                raise SmokeFailure(f"Core environment missing: {CORE_PY}; install services/classroom-core")
            core_port = _free_port()
            core_url = f"http://127.0.0.1:{core_port}"
            data_dir = artifacts / "core-data"
            data_dir.mkdir()
            env = dict(os.environ)
            for key in list(env):
                if key.startswith(("CORE_", "BRIGHT_AGENT")):
                    env.pop(key, None)
            env.update(
                {
                    "PYTHONUNBUFFERED": "1",
                    "CORE_PORT": str(core_port),
                    "CORE_DEV": "0",
                    "CORE_AUTOSTART_LESSON": "0",
                    "CORE_LESSON_RUN": str(FIXTURE),
                    "CORE_DB_PATH": str(data_dir / "bright.db"),
                    "DATA_DIR": str(data_dir),
                    "CORE_MODE": "OFFLINE" if args.agent == "off" else "FULL",
                    "CORE_PROBE_INTERVAL_S": "3600",
                    "CORE_PLAYBACK_ACK_TIMEOUT_S": "2",
                    "CORE_SILENCE_TIMEOUT_S": "3",
                    "CORE_REVEAL_HOLD_S": "0.05",
                    "BRIGHT_AGENT": args.agent,
                    "CORE_CORS_ORIGINS": "*",
                }
            )
            core = ManagedProcess(
                "core",
                [str(CORE_PY), str(CORE_DIR / "app.py")],
                CORE_DIR,
                env,
                artifacts / "core.log",
            )
            core.start()
            processes.append(core)
            result["managed"]["core"] = True
        result["coreStartupMs"] = _wait_http(f"{core_url}/health", args.startup_timeout)
        health = _json_get(f"{core_url}/health")
        if health.get("status") != "ok":
            raise SmokeFailure(f"Core health is not ok: {health}")
        dev_status = _http_status(f"{core_url}/dev/state")
        if dev_status != 404:
            raise SmokeFailure(f"production gate failed: /dev/state returned HTTP {dev_status}, expected 404")

        if not ui_url:
            if not (UI_DIR / "node_modules").is_dir():
                raise SmokeFailure("UI dependencies missing; run `cd apps/classroom-ui && pnpm install`")
            pnpm = shutil.which("pnpm")
            if not pnpm:
                raise SmokeFailure("pnpm is not on PATH")
            ui_port = _free_port()
            ui_url = f"http://127.0.0.1:{ui_port}"
            ui_env = {
                **os.environ,
                "VITE_BUS_URL": core_url.replace("http://", "ws://") + "/ws",
                "VITE_CORE_HTTP": core_url,
                "VITE_SPEECH_URL": speech_url,
                "VITE_MOCK": "0",
                "BROWSER": "none",
                "CI": "1",
            }
            ui = ManagedProcess(
                "ui",
                [pnpm, "exec", "vite", "--host", "127.0.0.1", "--port", str(ui_port), "--strictPort"],
                UI_DIR,
                ui_env,
                artifacts / "ui.log",
            )
            ui.start()
            processes.append(ui)
            result["managed"]["ui"] = True
        result["uiStartupMs"] = _wait_http(f"{ui_url}/classroom", args.startup_timeout)
        if _http_status(f"{ui_url}/control") != 200:
            raise SmokeFailure("UI /control route is not available")

        ws_url = core_url.replace("http://", "ws://").replace("https://", "wss://") + "/ws"
        result["runtime"] = asyncio.run(_exercise_bus(ws_url, args.timeout))
        result.update(
            {
                "status": "passed",
                "coreDev": False,
                "hermesAbsent": args.agent == "off" and not args.core_url,
                "coreHealth": health,
                "speechHealth": speech_health,
                "uiRoutes": ["/classroom", "/control"],
                "finishedAt": datetime.now(timezone.utc).isoformat(),
            }
        )
        _write_result(artifacts / "result.json", result)
        print("PASS  Option B Core wire smoke")
        print(f"      production lesson.start -> DONE: {result['runtime']['lessonCompleteMs']} ms")
        print(f"      role guards: {result['runtime']['roleGuards']}; protocol v{PROTOCOL_VERSION}")
        print(f"      Core dev endpoints: disabled; agent: {result['agent']}")
        print(f"      diagnostics: {artifacts}")
        return 0
    except EnvironmentBlocked as exc:
        result.update({"status": "environment-blocked", "error": str(exc)})
        _write_result(artifacts / "result.json", result)
        print(f"BLOCKED  {exc}", file=sys.stderr)
        print(f"         diagnostics: {artifacts}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - command must always emit diagnostics
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}"})
        result["processTails"] = {process.name: process.tail() for process in processes}
        _write_result(artifacts / "result.json", result)
        print(f"FAIL  {type(exc).__name__}: {exc}", file=sys.stderr)
        for process in processes:
            tail = process.tail()
            if tail:
                print(f"\n--- {process.name}.log (tail) ---\n{tail}", file=sys.stderr)
        print(f"\ndiagnostics: {artifacts}", file=sys.stderr)
        return 1
    finally:
        for process in reversed(processes):
            process.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Start or target a local Bright stack and prove the production authored path."
    )
    parser.add_argument("--core-url", help="target an existing Core instead of starting one")
    parser.add_argument("--ui-url", help="target an existing UI instead of starting Vite")
    parser.add_argument("--speech-url", help="target an existing speech service instead of fake speech")
    parser.add_argument(
        "--agent",
        choices=("off", "scripted", "hermes"),
        default="off",
        help="managed Core agent mode; off is the required no-Hermes release path",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="lesson completion timeout")
    parser.add_argument("--startup-timeout", type=float, default=45.0)
    parser.add_argument(
        "--artifacts",
        default=str(ROOT / "tests" / ".artifacts" / "product-smoke"),
        help="diagnostic output directory (one timestamped child is created)",
    )
    return parser


def main() -> int:
    return run(build_parser().parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
