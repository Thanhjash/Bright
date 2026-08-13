"""Static contracts for the operator-only ideal composition acceptance lane.

No Chromium or Hermes credential is required here. These tests protect the
boundary between a real composed acceptance run and useful but separate fake
wire / synthetic-browser smokes.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
NODE = ROOT / "tests" / "node" / "ideal_composed_acceptance.mjs"
LIB = ROOT / "tests" / "node" / "lib.mjs"
SCRIPT = ROOT / "scripts" / "ideal-composed-acceptance.sh"
THREE_TURN_FIXTURE = ROOT / "tests" / "fixtures" / "ideal_composed_three_turn.run.json"


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
    assert "artifactVersion: 2" in source
    assert "uiOrigin: cfg.uiOrigin" not in source
    assert "inputFixture" not in source
    assert "row.reason" not in source
    assert "row.code" not in source
    assert "row.lessonId" not in source


def test_per_attempt_proof_uses_capability_and_utterance_slots_not_nth_events() -> None:
    source = NODE.read_text(encoding="utf-8")

    assert "slot('assignment', payload.assignmentId)" in source
    assert "slot('capture', payload.captureId)" in source
    assert "slot('utterance', payload.utteranceId)" in source
    assert "correlatedCorrectCycles" in source
    assert "sameCapture" in source
    assert "calloutFinished" in source
    assert "captureRequestedOrder" in source
    assert "captureReadyOrder" in source
    assert "captureStartedOrder" in source
    assert "responseAcceptedOrder" in source
    assert "piperOrder" in source
    assert "playbackStartedOrder" in source
    assert "playbackFinishedOrder" in source
    assert "commitOrder" in source


def test_acceptance_lane_keeps_one_turn_default_and_proves_each_requested_attempt() -> None:
    source = NODE.read_text(encoding="utf-8")

    assert "raw.attempts ?? 1" in source
    assert "expectedAttempts: cfg.attempts" in source
    assert "for (let attempt = 0; attempt < cfg.attempts; attempt += 1)" in source
    assert "assertAttempt(ledger.rows, cycle, attempt)" in source
    assert "expected exactly ${attempts} correlated agent speech turns" in source
    assert "asrOrder" in source
    assert "piperOrder" in source
    assert "playbackFinishedOrder" in source
    assert "commitOrder" in source
    assert "if (cfg.attempts === 1) out.commit = out.attempts[0]" in source


def test_v3_fixture_is_three_identical_speech_cycles_not_market_curriculum() -> None:
    lesson = json.loads(THREE_TURN_FIXTURE.read_text(encoding="utf-8"))

    assert lesson["lessonId"] == "ideal-composed-three-turn"
    assert lesson["curriculum"]["approver"] == "TEST FIXTURE — not classroom curriculum"
    stations = lesson["activities"][:3]
    assert [station["id"] for station in stations] == [
        "voice_station_1", "voice_station_2", "voice_station_3"
    ]
    assert {station["expect"]["kind"] for station in stations} == {"speech"}
    assert len({station["expect"]["correct"] for station in stations}) == 1
    assert [station["branches"][0]["goto"] for station in stations] == [
        "voice_station_2", "voice_station_3", "closure"
    ]


def test_operator_script_uses_only_the_new_acceptance_scenario() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "ideal_composed_acceptance.mjs" in source
    assert "product_smoke" not in source
    assert "composed_smoke" not in source
    assert "SELECT COUNT(*) FROM messages" in source
    assert "privacy gate failed" in source
    assert "--attempts must be 1 or 3" in source
    assert "node_exit=$?" in source
    assert "privacy_exit=$?" in source
    assert "if (( node_exit != 0 )); then" in source
