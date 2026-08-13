"""Unit contracts for the one-command Option B product smoke harness."""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "product_smoke.py"
SPEC = importlib.util.spec_from_file_location("bright_product_smoke", MODULE_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def test_smoke_fixture_is_short_complete_authored_path() -> None:
    fixture = json.loads(smoke.FIXTURE.read_text(encoding="utf-8"))
    assert fixture["lessonId"] == "product-smoke-option-b"
    assert [activity["id"] for activity in fixture["activities"]] == [
        "smoke_hook",
        "smoke_choice",
        "smoke_wrap",
    ]
    choice = fixture["activities"][1]
    assert choice["expect"] == {"kind": "choice", "correct": "sun"}
    assert {branch["on"] for branch in choice["branches"]} == {
        "correct",
        "near",
        "wrong",
        "silence",
        "timeout",
    }


def test_default_mode_is_secret_free_and_agent_off() -> None:
    args = smoke.build_parser().parse_args([])
    assert args.agent == "off"
    assert args.core_url is None
    assert args.speech_url is None
    assert args.ui_url is None
    assert args.require_agent_proposal is False
    smoke._validate_args(args)


def test_managed_hermes_refuses_missing_sidecar_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("HERMES_API_URL", raising=False)
    monkeypatch.delenv("HERMES_API_KEY", raising=False)
    args = smoke.build_parser().parse_args(["--agent", "hermes"])
    with pytest.raises(smoke.SmokeFailure, match="already-running pinned sidecar"):
        smoke._validate_args(args)


def test_managed_hermes_refuses_placeholder_credential(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HERMES_API_URL", "http://127.0.0.1:8642")
    monkeypatch.setenv("HERMES_API_KEY", "CHANGE-ME")
    args = smoke.build_parser().parse_args(["--agent", "hermes"])
    with pytest.raises(smoke.SmokeFailure, match="placeholder HERMES_API_KEY"):
        smoke._validate_args(args)


def test_artifact_runs_never_collide(tmp_path: Path) -> None:
    first = smoke._artifact_dir(tmp_path)
    second = smoke._artifact_dir(tmp_path)
    assert first != second
    assert first.is_dir() and second.is_dir()


def test_wire_client_emits_protocol_v2_and_its_declared_role() -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.frames: list[str] = []

        async def send(self, frame: str) -> None:
            self.frames.append(frame)

    async def scenario() -> dict[str, object]:
        client = smoke.WireClient("ws://unused", "stage")
        client.ws = FakeSocket()
        await client.send("client.hello", {"role": client.role})
        return json.loads(client.ws.frames[0])

    frame = asyncio.run(scenario())
    assert frame["v"] == 3
    assert frame["type"] == "client.hello"
    assert frame["payload"] == {"role": "stage"}
    assert frame["seq"] == 1


def test_result_file_is_machine_readable(tmp_path: Path) -> None:
    target = tmp_path / "result.json"
    smoke._write_result(target, {"status": "passed", "secret": False})
    assert json.loads(target.read_text(encoding="utf-8")) == {
        "secret": False,
        "status": "passed",
    }
