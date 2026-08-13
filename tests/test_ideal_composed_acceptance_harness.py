"""Static contracts for the operator-only ideal composition acceptance lane.

No Chromium or Hermes credential is required here. These tests protect the
boundary between a real composed acceptance run and useful but separate fake
wire / synthetic-browser smokes.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "tests" / "node" / "ideal_composed_acceptance.mjs"
LIB = ROOT / "tests" / "node" / "lib.mjs"
SCRIPT = ROOT / "scripts" / "ideal-composed-acceptance.sh"


def test_acceptance_lane_is_valid_node_syntax() -> None:
    completed = subprocess.run(["node", "--check", str(NODE)], capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    assert "export { chromium }" in LIB.read_text(encoding="utf-8")


def test_acceptance_lane_uses_two_real_routes_and_never_test_drives_core() -> None:
    source = NODE.read_text(encoding="utf-8")
    assert "${cfg.uiOrigin}/classroom" in source
    assert "${cfg.uiOrigin}/control" in source
    assert source.count("launchPersistentContext") == 2
    assert "launchPersistent(" not in source
    assert "/dev/" not in source
    assert "coreApi(" not in source
    assert "bus.send(" not in source
    assert "new WebSocket(" not in source


def test_only_explicit_file_mode_can_enable_fake_microphone() -> None:
    source = NODE.read_text(encoding="utf-8")
    fake_block = source.split("if (cfg.mode === 'fake-audio-file')", 1)[1].split("controlContext =", 1)[0]
    assert "--use-fake-device-for-media-stream" in fake_block
    assert "--use-file-for-fake-audio-capture=" in fake_block
    manual_block = source.split("stageContext =", 1)[1].split("if (cfg.mode === 'fake-audio-file')", 1)[0]
    assert "use-fake" not in manual_block


def test_artifact_contract_is_scrubbed_and_requires_stage_originated_ack() -> None:
    source = NODE.read_text(encoding="utf-8")
    assert "Network.webSocketFrameReceived" in source
    assert "Network.webSocketFrameSent" in source
    assert "speech.playback.finished" in source
    assert "Core did not publish a post-playback committed state transition" in source
    assert "never text, transcripts" in source
    assert "result.json" in source
    assert "rm(controlProfile" in source
    assert "rm(stageProfile" in source


def test_operator_script_uses_only_the_new_acceptance_scenario() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ideal_composed_acceptance.mjs" in source
    assert "product_smoke" not in source
    assert "composed_smoke" not in source
    assert "SELECT COUNT(*) FROM messages" in source
    assert "privacy gate failed" in source
