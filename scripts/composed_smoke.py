#!/usr/bin/env python3
"""Opt-in proof of real local speech plus a Chromium microphone/audio path.

This is intentionally separate from ``product_smoke.py``.  The latter is a
secret-free Core wire check and may use fake speech.  This command never starts
fake speech and does not claim room acoustics, learner grading quality, AIRI
speech lifecycle acknowledgement, or a Hermes teaching turn unless an operator
selects its optional health probe.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
NODE_SCENARIO = ROOT / "tests" / "node" / "composed_speech.mjs"
TOOLS_DIR = ROOT / ".tools"
PLAYWRIGHT = TOOLS_DIR / "node_modules" / "playwright-core" / "index.mjs"
DEFAULT_CHROME = Path.home() / ".cache" / "ms-playwright" / "chromium-1228" / "chrome-linux64" / "chrome"


class Skipped(RuntimeError):
    """A required local capability is absent; this is not a product pass."""


class Failed(RuntimeError):
    pass


def usable_credential(value: str | None) -> bool:
    """Reject sample credentials before any potentially slow Hermes request."""
    lowered = (value or "").strip().lower()
    return bool(lowered) and not lowered.startswith(("change-me", "changeme", "placeholder"))


def get_json(url: str, headers: dict[str, str] | None = None, timeout: float = 5.0) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError) as exc:
        raise Skipped(f"cannot reach {url}: {exc}") from exc
    if not isinstance(body, dict):
        raise Failed(f"{url} returned non-object JSON")
    return body


def artifact_dir(base: Path) -> Path:
    target = base / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S-%fZ")
    target.mkdir(parents=True, exist_ok=False)
    return target


def parse_browser_result(stdout: str) -> dict[str, Any]:
    for line in stdout.splitlines():
        if line.startswith("@@RESULT@@"):
            value = json.loads(line.removeprefix("@@RESULT@@").strip())
            if isinstance(value, dict):
                return value
    raise Failed("browser probe emitted no machine-readable result")


def run(args: argparse.Namespace) -> int:
    artifacts = artifact_dir(Path(args.artifacts).resolve())
    result: dict[str, Any] = {
        "status": "running",
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "coverage": [
            "real-local-speech-health",
            "Chromium fake microphone -> real ASR",
            "real Piper TTS -> browser audio pipeline",
        ],
        "notCoverage": [
            "physical room acoustics or feedback",
            "child ASR/grading accuracy or zero-false-accept gate",
            "AIRI speech lifecycle acknowledgement",
            "Hermes teaching/tool execution unless --hermes-tool-round-trip is selected",
        ],
    }
    try:
        speech_url = args.speech_url.rstrip("/")
        health = get_json(f"{speech_url}/health")
        if health.get("status") != "ok":
            raise Skipped(f"speech health is not ok: {health}")
        if not health.get("voices"):
            raise Skipped("speech has no loaded Piper voice")
        if health.get("stt") is not True:
            raise Skipped("speech STT is unavailable; no ASR composition can run")
        result["speechHealth"] = {
            "voices": health.get("voices"),
            "stt": True,
            "sttModel": health.get("sttModel"),
        }

        if args.hermes_health:
            key = os.environ.get("HERMES_API_KEY")
            if not usable_credential(key):
                raise Skipped("--hermes-health needs a non-placeholder HERMES_API_KEY")
            hermes = get_json(
                f"{args.hermes_url.rstrip('/')}/health",
                {"Authorization": f"Bearer {key}"},
            )
            if hermes.get("status") != "ok":
                raise Failed(f"Hermes health is not ok: {hermes}")
            result["hermesHealth"] = "ok"

        if args.hermes_tool_round_trip:
            if not args.hermes_health:
                raise Failed("--hermes-tool-round-trip requires --hermes-health")
            rehearsal = subprocess.run(
                [
                    str(ROOT / "scripts" / "product-smoke.sh"),
                    "--core-url", args.core_url.rstrip("/"),
                    "--ui-url", args.ui_url.rstrip("/"),
                    "--speech-url", speech_url,
                    "--timeout", str(args.timeout),
                    "--require-agent-proposal",
                ],
                cwd=ROOT,
                env=os.environ.copy(),
                capture_output=True,
                text=True,
                timeout=args.timeout + 20,
            )
            (artifacts / "hermes-tool-round-trip.log").write_text(
                f"--- stdout ---\n{rehearsal.stdout}\n--- stderr ---\n{rehearsal.stderr}",
                encoding="utf-8",
            )
            if rehearsal.returncode != 0:
                raise Failed("Hermes/Core MCP proposal rehearsal failed; see hermes-tool-round-trip.log")
            result["hermesToolRoundTrip"] = "passed-with-virtual-stage-playback-acks"

        chrome = Path(os.environ.get("BRIGHT_CHROME", str(DEFAULT_CHROME)))
        if not PLAYWRIGHT.exists():
            raise Skipped(f"playwright-core is absent at {PLAYWRIGHT}")
        if not chrome.is_file():
            raise Skipped(f"Chromium is absent at {chrome}; set BRIGHT_CHROME")
        env = dict(os.environ)
        env["PLAYWRIGHT_CORE"] = PLAYWRIGHT.as_uri()
        env["CHROME_PATH"] = str(chrome)
        probe = subprocess.run(
            ["node", str(NODE_SCENARIO), json.dumps({"uiOrigin": args.ui_url.rstrip("/"), "speechUrl": speech_url})],
            cwd=TOOLS_DIR,
            env=env,
            capture_output=True,
            text=True,
            timeout=args.timeout,
        )
        (artifacts / "browser.log").write_text(
            f"--- stdout ---\n{probe.stdout}\n--- stderr ---\n{probe.stderr}", encoding="utf-8"
        )
        browser = parse_browser_result(probe.stdout)
        if probe.returncode != 0 or not browser.get("ok"):
            raise Failed(f"browser composition failed: {browser.get('error', 'unknown error')}")
        result["browser"] = browser.get("browser")
        result["status"] = "passed"
        result["finishedAt"] = datetime.now(timezone.utc).isoformat()
        (artifacts / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print("PASS  real speech + Chromium composition")
        print(f"      ASR: {result['browser']['asr']['model']}; recording: {result['browser']['recordedBytes']} bytes")
        print(f"      diagnostics: {artifacts}")
        return 0
    except Skipped as exc:
        result.update({"status": "skipped", "reason": str(exc), "finishedAt": datetime.now(timezone.utc).isoformat()})
        (artifacts / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"SKIP  {exc}", file=sys.stderr)
        print(f"      diagnostics: {artifacts}", file=sys.stderr)
        return 2
    except Exception as exc:  # noqa: BLE001 - always leave a diagnostic report
        result.update({"status": "failed", "error": f"{type(exc).__name__}: {exc}", "finishedAt": datetime.now(timezone.utc).isoformat()})
        (artifacts / "result.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        print(f"FAIL  {type(exc).__name__}: {exc}", file=sys.stderr)
        print(f"      diagnostics: {artifacts}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe real local speech and browser media composition.")
    parser.add_argument("--speech-url", default="http://127.0.0.1:8001")
    parser.add_argument("--ui-url", default="http://127.0.0.1:3000", help="running UI origin (keeps speech CORS real)")
    parser.add_argument("--hermes-health", action="store_true", help="also authenticate to the local Hermes /health endpoint")
    parser.add_argument("--hermes-url", default="http://127.0.0.1:8642")
    parser.add_argument(
        "--hermes-tool-round-trip",
        action="store_true",
        help="exercise an active target Core turn and require a Hermes MCP proposal (uses virtual playback ACKs)",
    )
    parser.add_argument("--core-url", default="http://127.0.0.1:8004", help="target Core for --hermes-tool-round-trip")
    parser.add_argument("--timeout", type=float, default=45.0)
    parser.add_argument("--artifacts", default=str(ROOT / "tests" / ".artifacts" / "composed-smoke"))
    return parser


if __name__ == "__main__":
    raise SystemExit(run(build_parser().parse_args()))
