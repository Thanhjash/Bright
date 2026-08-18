"""Teacher path can own Stage audio without a cassette lesson_run."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import create_app
from config import Settings
from test_app import HELLO, handshake, receive_until

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def teacher_client(tmp_path: Path):
    settings = Settings(
        assets_dir=ROOT / "assets",
        data_dir=tmp_path,
        db_path=tmp_path / "app.db",
        dev_endpoints=True,
        probe_interval_s=3600,
    )
    with TestClient(create_app(settings)) as client:
        yield client


def test_there_is_exactly_one_room_page() -> None:
    """One page, one loudspeaker.

    `/learn` was a second route that opened a class merely by being loaded, and
    a second WebSocket -- therefore a second potential loudspeaker. It was
    deleted on 2026-08-18. This test exists so it cannot come back quietly.
    """
    ui = ROOT.parents[1] / "apps" / "classroom-ui" / "src"
    assert not (ui / "routes" / "learn").exists(), "/learn is back"
    app_tsx = (ui / "App.tsx").read_text(encoding="utf-8")
    assert "/learn" not in app_tsx
    # Only the room may touch the loudspeaker. `bus/wiring.ts` drives it and
    # `ClassroomRoute` arms the audio unlock; anything else importing it is a
    # second speaker waiting to happen.
    allowed = {"ClassroomRoute.tsx"}
    drivers = sorted(
        path.name
        for path in ui.rglob("*.tsx")
        if "speakingDriver" in path.read_text(encoding="utf-8")
    )
    assert set(drivers) <= allowed, f"unexpected speakingDriver importers: {drivers}"


def test_leases_exist_without_lesson(teacher_client: TestClient):
    core = teacher_client.app.state.core
    assert core.capability_leases is not None
    status = teacher_client.get("/teacher/status").json()
    assert status["stageAudioOwner"] is False
    assert "speechUp" in status
    assert status["phase"] == "asleep"
    assert status["sessionOpen"] is False
    assert "hermesUp" in status
    assert "readyToStart" in status
    pulse = teacher_client.post("/teacher/heartbeat", json={"reason": "test"}).json()
    assert pulse["action"] == "asleep"


def test_stage_gets_lease_and_hears_publish_without_runner(teacher_client: TestClient):
    core = teacher_client.app.state.core
    with teacher_client.websocket_connect("/ws") as stage:
        stage.send_text(json.dumps(HELLO))
        handshake(stage)
        stage.send_text(
            json.dumps(
                {
                    "v": 3,
                    "type": "capability.report",
                    "payload": {
                        "clientInstanceId": "stage-teacher-voice",
                        "connectionEpoch": 1,
                        "role": "stage",
                        "capabilities": {"audio_output": True},
                        "reportedAt": 1,
                    },
                }
            )
        )
        lease = receive_until(stage, "stage.lease.granted")
        assert lease["payload"]["clientInstanceId"] == "stage-teacher-voice"
        turn_id = core.publish_speech("Hello class", source="agent")
        started = receive_until(stage, "speech.turn.started")
        assert started["payload"]["speechTurnId"] == turn_id
        assert started["payload"]["source"] == "agent"
        receive_until(stage, "speech.text.delta")
        receive_until(stage, "speech.turn.ended")
        assert teacher_client.get("/teacher/status").json()["stageAudioOwner"] is True


def test_teacher_playback_ack_relays_without_runner(teacher_client: TestClient):
    core = teacher_client.app.state.core
    core.teacher_os = object()
    with teacher_client.websocket_connect("/ws") as stage:
        stage.send_text(json.dumps(HELLO))
        handshake(stage)
        stage.send_text(
            json.dumps(
                {
                    "v": 3,
                    "type": "capability.report",
                    "payload": {
                        "clientInstanceId": "stage-teacher-ack",
                        "connectionEpoch": 1,
                        "role": "stage",
                        "capabilities": {"audioPlayback": True},
                        "reportedAt": 1,
                    },
                }
            )
        )
        receive_until(stage, "stage.lease.granted")
        turn_id = core.publish_speech("Hello", source="agent")
        receive_until(stage, "speech.turn.ended")
        stage.send_text(
            json.dumps(
                {
                    "v": 3,
                    "type": "speech.playback.started",
                    "payload": {"speechTurnId": turn_id},
                }
            )
        )
        stage.send_text(
            json.dumps(
                {
                    "v": 3,
                    "type": "speech.playback.finished",
                    "payload": {"speechTurnId": turn_id, "status": "completed"},
                }
            )
        )
        observed = receive_until(stage, "speech.playback.observed")
        assert observed["payload"] == {"speechTurnId": turn_id, "status": "completed"}
