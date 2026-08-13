"""Contracts for the separately named real speech/browser composition probe."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "composed_smoke.py"
SPEC = importlib.util.spec_from_file_location("bright_composed_smoke", MODULE_PATH)
assert SPEC and SPEC.loader
smoke = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = smoke
SPEC.loader.exec_module(smoke)


def test_placeholder_credentials_are_never_usable() -> None:
    for value in (None, "", "CHANGE-ME", "change-me-later", "placeholder-token"):
        assert not smoke.usable_credential(value)
    assert smoke.usable_credential("real-secret-not-printed")


def test_default_command_targets_real_local_services() -> None:
    args = smoke.build_parser().parse_args([])
    assert args.speech_url == "http://127.0.0.1:8001"
    assert args.ui_url == "http://127.0.0.1:3000"
    assert args.hermes_health is False
    assert args.hermes_tool_round_trip is False


def test_browser_probe_is_explicit_about_fake_browser_mic_not_child_accuracy() -> None:
    source = (ROOT / "tests" / "node" / "composed_speech.mjs").read_text(encoding="utf-8")
    assert "getUserMedia({ audio: true })" in source
    assert "/audio/transcriptions" in source
    assert "/audio/speech" in source
    assert "not a child utterance" in source
