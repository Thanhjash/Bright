from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import (
    ConversationCoordinator,
    create_app,
    handle_barge_in,
    handle_client_hello,
    websocket_origin_allowed,
)
from bright_contracts import SpeechBargeInPayload
from bus import EventBus
from config import Settings

ROOT = Path(__file__).resolve().parents[1]

HELLO = {"v": 3, "type": "client.hello", "payload": {"role": "stage"}}


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        assets_dir=ROOT / "assets",
        data_dir=tmp_path,
        db_path=tmp_path / "app.db",
        lesson_run_path=ROOT / "data" / "sample_lesson_run.json",
        dev_endpoints=True,
        silence_timeout_s=0.05,
        reveal_hold_s=0.0,
        probe_interval_s=3600,
    )


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as test_client:
        yield test_client


def test_health(client: TestClient):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["mode"] in ("FULL", "DEGRADED", "OFFLINE")
    assert isinstance(body["stateVersion"], int)


def test_ready_is_not_a_false_positive_without_browser_capability_owners(client: TestClient):
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["checks"]["lesson"] is True
    assert body["checks"]["stageAudioOwner"] is False
    assert body["checks"]["controlInputOwner"] is False


def test_playback_ack_state_machine_allows_pre_audio_failure_once():
    coordinator = ConversationCoordinator()
    coordinator.register_speech("turn-1")
    assert coordinator.note_playback(
        "turn-1", event="finished", status="failed"
    ) == (True, True, None)
    assert coordinator.note_playback(
        "turn-1", event="finished", status="failed"
    ) == (True, False, None)
    assert coordinator.note_playback(
        "unknown", event="started", status="playing"
    )[0] is False


def test_websocket_origin_uses_cors_allowlist_but_native_clients_may_omit_it():
    allowed = ("http://localhost:3000", "http://127.0.0.1:5173")
    assert websocket_origin_allowed(None, allowed)
    assert websocket_origin_allowed("http://localhost:3000", allowed)
    assert not websocket_origin_allowed("https://attacker.example", allowed)
    assert not websocket_origin_allowed("null", allowed)
    assert websocket_origin_allowed("https://any.example", ("*",))


def test_barge_in_is_exact_generation_scoped_and_idempotent():
    coordinator = ConversationCoordinator()
    coordinator.register_speech(
        "agent-1", activity_id="activity-1", activity_generation=7
    )
    request = SpeechBargeInPayload(
        requestId="barge-1",
        speechTurnId="agent-1",
        activityId="activity-1",
        activityGeneration=7,
    )
    accepted, changed = coordinator.request_barge_in(
        request, activity_id="activity-1", activity_generation=7
    )
    assert accepted["accepted"] is True
    assert changed is True
    replay, changed = coordinator.request_barge_in(
        request, activity_id="activity-1", activity_generation=7
    )
    assert replay == accepted
    assert changed is False

    stale = SpeechBargeInPayload(
        requestId="barge-stale",
        speechTurnId="agent-1",
        activityId="activity-1",
        activityGeneration=6,
    )
    rejected, changed = coordinator.request_barge_in(
        stale, activity_id="activity-1", activity_generation=7
    )
    assert rejected["accepted"] is False
    assert changed is False


async def test_barge_in_handler_is_control_only_and_cancels_exactly_once():
    bus = EventBus(lambda: 0)
    coordinator = ConversationCoordinator()
    coordinator.register_speech(
        "agent-1", activity_id="activity-1", activity_generation=7
    )
    cancelled: list[tuple[str, str]] = []

    class Driver:
        def cancel_speech_turn(self, speech_turn_id, reason):
            cancelled.append((speech_turn_id, reason))
            return True

    core = SimpleNamespace(
        bus=bus,
        conversations=coordinator,
        runner=SimpleNamespace(
            current=SimpleNamespace(id="activity-1"), _generation=7
        ),
        agent_driver=Driver(),
        cancel_speech=lambda *_args: None,
    )
    payload = {
        "requestId": "barge-1",
        "speechTurnId": "agent-1",
        "activityId": "activity-1",
        "activityGeneration": 7,
    }

    stage = bus.subscribe(role="stage")
    await handle_barge_in(core, stage, payload)
    denied = await stage.queue.get()
    assert denied["payload"]["accepted"] is False
    assert cancelled == []

    control = bus.subscribe(role="control")
    await handle_barge_in(core, control, payload)
    accepted = await control.queue.get()
    assert accepted["payload"]["accepted"] is True
    assert cancelled == [("agent-1", "control:barge_in")]

    await handle_barge_in(core, control, payload)
    replay = await control.queue.get()
    assert replay["payload"] == accepted["payload"]
    assert cancelled == [("agent-1", "control:barge_in")]


def test_second_hello_cannot_escalate_stage_connection_to_control():
    bus = EventBus(lambda: 0)
    core = SimpleNamespace(
        bus=bus,
        store=SimpleNamespace(snapshot=lambda: {"scene": {}, "lesson": {}}),
    )
    stage = bus.subscribe(role="stage")

    handle_client_hello(core, stage, {"role": "control"})

    frame = stage.queue.get_nowait()
    assert frame["type"] == "error"
    assert frame["payload"]["code"] == "role_locked"
    assert stage.role == "stage"

    handle_client_hello(core, stage, {"role": "stage"})
    assert stage.queue.get_nowait()["type"] == "scene.snapshot"


def handshake(ws) -> tuple[dict, dict]:
    """Drain the connect handshake and return (snapshot, mode).

    Two frames, always, in this order:
      1. `scene.snapshot` — unconditional, even when the client claims a
         stateVersion at or ahead of ours (PROTOCOL §9.1).
      2. `mode.changed`   — because that event otherwise fires only on a
         CHANGE, so a client connecting while we are already DEGRADED or
         OFFLINE would never hear about it and would sit on its own default.
         The facilitator console defaulted to FULL and reported a healthy
         agent while the agent was unreachable.
    """
    snapshot = ws.receive_json()
    assert snapshot["type"] == "scene.snapshot"
    mode = ws.receive_json()
    assert mode["type"] == "mode.changed"
    return snapshot, mode


def receive_until(ws, event_type: str, *, limit: int = 20) -> dict:
    for _ in range(limit):
        frame = ws.receive_json()
        if frame["type"] == event_type:
            return frame
    raise AssertionError(f"did not receive {event_type!r} within {limit} frames")


def test_hello_gets_a_snapshot_then_a_stream(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(HELLO))
        snapshot, mode = handshake(ws)
        assert snapshot["seq"] == 1
        assert snapshot["v"] == 3
        assert "scene" in snapshot["payload"] and "lesson" in snapshot["payload"]
        assert snapshot["payload"]["scene"]["stateVersion"] == snapshot["stateVersion"]
        assert snapshot["payload"]["lesson"]["activityCount"] == 0
        assert mode["seq"] == 2
        assert mode["payload"]["mode"] in {"FULL", "DEGRADED", "OFFLINE"}

        client.post("/dev/scene", json={"kind": "text", "props": {"text": "pushed"}})
        update = ws.receive_json()
        assert update["type"] == "scene.update"
        assert update["seq"] == 3
        assert update["payload"]["kind"] == "text"
        assert update["payload"]["props"]["text"] == "pushed"
        assert update["stateVersion"] > snapshot["stateVersion"]


def test_only_validated_stage_terminal_ack_is_relayed_to_control(client: TestClient):
    with client.websocket_connect("/ws") as stage, client.websocket_connect("/ws") as control:
        stage.send_text(json.dumps(HELLO))
        handshake(stage)
        control.send_text(json.dumps({"v": 3, "type": "client.hello", "payload": {"role": "control"}}))
        handshake(control)
        stage.send_text(json.dumps({
            "v": 3,
            "type": "capability.report",
            "payload": {
                "clientInstanceId": "stage-relay-test",
                "connectionEpoch": 1,
                "role": "stage",
                "capabilities": {"audioPlayback": True},
                "reportedAt": 1,
            },
        }))
        receive_until(stage, "stage.lease.granted")

        core = client.app.state.core
        turn_id = core.publish_speech("Hello", source="authored")
        receive_until(stage, "speech.turn.ended")
        receive_until(control, "speech.turn.ended")

        # A Control socket knows the public turn ID but cannot forge physical
        # completion or cause the authoritative relay.
        control.send_text(json.dumps({
            "v": 3,
            "type": "speech.playback.finished",
            "payload": {"speechTurnId": turn_id, "status": "completed"},
        }))
        assert receive_until(control, "error")["payload"]["code"] == "forbidden"
        assert not any(
            frame["type"] == "speech.playback.observed"
            for frame in core.bus.history
        )

        stage.send_text(json.dumps({
            "v": 3,
            "type": "speech.playback.started",
            "payload": {"speechTurnId": turn_id},
        }))
        stage.send_text(json.dumps({
            "v": 3,
            "type": "speech.playback.finished",
            "payload": {"speechTurnId": turn_id, "status": "completed"},
        }))
        observed = receive_until(control, "speech.playback.observed")
        assert observed["payload"] == {
            "speechTurnId": turn_id,
            "status": "completed",
        }


def test_dev_say_is_broadcast(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(HELLO))
        handshake(ws)
        body = client.post(
            "/dev/say", json={"text": "Hello class", "turnId": "t1"}
        ).json()
        assert body["ok"] is True and body["turnId"] == "t1"
        event = ws.receive_json()
        assert event["type"] == "speech.say"
        assert event["payload"] == {"text": "Hello class", "turnId": "t1"}


def test_two_clients_each_get_their_own_seq(client: TestClient):
    with client.websocket_connect("/ws") as a:
        a.send_text(json.dumps(HELLO))
        assert a.receive_json()["seq"] == 1
        with client.websocket_connect("/ws") as b:
            b.send_text(json.dumps({"v": 3, "type": "client.hello", "payload": {"role": "control"}}))
            assert b.receive_json()["seq"] == 1
            client.post("/dev/say", json={"text": "both", "turnId": "t"})
            assert a.receive_json()["seq"] == 2
            assert b.receive_json()["seq"] == 2


def test_interaction_over_the_socket_drives_the_runner(client: TestClient):
    client.post("/dev/lesson/start", json={"index": 2})   # q_meow
    core = client.app.state.core
    assert core.runner.on_response_window is not None
    while core.runner._pending_playback_turns:
        turn_id = core.runner._pending_playback_turns[0]
        assert client.portal.call(core.runner.on_playback_started, turn_id)
        assert client.portal.call(core.runner.on_playback_finished, turn_id)
    current_assignment = core.session_controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert current_assignment is not None, [
        (a.session_id, a.activity_id, a.activity_generation, a.state)
        for a in core.session_controller.assignments._assignments.values()
    ]
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(HELLO))
        snapshot = ws.receive_json()
        assert snapshot["payload"]["scene"]["kind"] == "choice"
        assignment = snapshot["payload"]["assignment"]

        ws.send_text(
            json.dumps({"v": 3, "type": "interaction.choice", "payload": {
                "optionId": "cat",
                "assignmentId": assignment["assignmentId"],
                "responseTurnId": assignment["responseTurnId"],
            }})
        )
        kinds = []
        for _ in range(4):
            event = ws.receive_json()
            kinds.append(event["type"])
            if event["type"] == "scene.update" and "revealed" in event["payload"]["props"]:
                assert event["payload"]["props"]["revealed"]["correctId"] == "cat"
        assert "scene.update" in kinds

    state = client.get("/dev/state").json()
    assert state["runner"]["lastOutcome"] == "correct"


def test_finishing_a_lesson_ends_the_session_and_queues_the_summary(client: TestClient):
    last = len(client.get("/dev/lesson").json()["activities"]) - 1
    started = client.post("/dev/lesson/start", json={"index": last, "studentId": "s01"}).json()
    session_id = started["sessionId"]
    assert client.get("/dev/state").json()["sessionId"] == session_id

    client.post("/dev/lesson/control", json={"cmd": "skip"})   # past the last activity
    state = client.get("/dev/state").json()

    assert state["runner"]["running"] is False
    assert state["sessionId"] is None, "the session must be closed when the lesson ends"
    assert f"summarize_session:{session_id}" in {job["id"] for job in state["jobs"]}
    assert state["snapshot"]["scene"]["kind"] == "idle"
    assert state["snapshot"]["lesson"]["stage"] == "DONE"


def test_unknown_client_event_returns_an_error_frame(client: TestClient):
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(HELLO))
        handshake(ws)
        ws.send_text(json.dumps({"v": 3, "type": "nonsense.event", "payload": {}}))
        event = ws.receive_json()
        assert event["type"] == "error"
        assert event["payload"]["code"] == "unknown_event"
        assert "nonsense.event" in event["payload"]["message"]


def test_wrong_protocol_version_is_rejected_loudly(client: TestClient):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"v": 99, "type": "client.hello", "payload": {}}))
            ws.receive_json()


def test_first_message_must_be_hello(client: TestClient):
    from starlette.websockets import WebSocketDisconnect

    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"v": 3, "type": "interaction.choice", "payload": {}}))
            ws.receive_json()


def test_assets_are_served_and_traversal_is_404(client: TestClient):
    ok = client.get("/assets/animals/cat.svg")
    assert ok.status_code == 200
    assert b"<svg" in ok.content

    assert client.get("/assets/animals/unicorn.svg").status_code == 404
    assert client.get("/assets/../config.py").status_code in (404, 400)
    assert client.get("/assets/%2e%2e/config.py").status_code in (404, 400)
    assert client.get("/assets/").status_code == 404


def test_dev_lesson_and_mode(client: TestClient):
    lesson = client.get("/dev/lesson").json()
    assert lesson["lessonId"] == "en-a1-animals-01"
    assert lesson["activities"][0]["id"] == "hook_hello"
    assert "durationS" in lesson["activities"][0]

    assert client.post("/dev/mode", json={"mode": "FULL", "reason": "test"}).json()["mode"] == "FULL"
    assert client.get("/health").json()["mode"] == "FULL"
    assert client.post("/dev/mode", json={"mode": "SIDEWAYS"}).status_code == 422


def test_dev_recall(client: TestClient):
    client.post("/dev/lesson/start", json={"index": 2, "studentId": "s01"})
    body = client.get("/dev/recall", params={"q": "cat", "k": 3}).json()
    assert body["query"] == "cat"
    assert isinstance(body["results"], list)


def test_dev_endpoints_can_be_switched_off(settings: Settings):
    settings.dev_endpoints = False
    with TestClient(create_app(settings)) as bare:
        assert bare.post("/dev/scene", json={"kind": "idle"}).status_code == 404
        assert bare.get("/health").status_code == 200


def test_control_can_start_a_lesson_with_dev_endpoints_off(settings: Settings):
    settings.dev_endpoints = False
    with TestClient(create_app(settings)) as bare:
        with bare.websocket_connect("/ws") as ws:
            ws.send_text(json.dumps({"v": 3, "type": "client.hello", "payload": {"role": "control"}}))
            handshake(ws)
            ws.send_text(
                json.dumps(
                    {
                        "v": 3,
                        "type": "lesson.start",
                        "payload": {
                            "requestId": "start-1",
                            "index": 0,
                            "studentId": "s01",
                            "studentName": "Mai",
                        },
                    }
                )
            )
            frames = []
            for _ in range(20):
                frames.append(ws.receive_json())
                if frames[-1]["type"] == "lesson.started":
                    break
            started = next(frame for frame in frames if frame["type"] == "lesson.started")
            assert started["payload"]["requestId"] == "start-1"
            assert started["payload"]["studentId"] == "s01"
            assert started["payload"]["conversationId"].startswith("conversation-")
            position = next(frame for frame in frames if frame["type"] == "lesson.position")
            assert position["payload"]["activityId"] == "hook_hello"
            assert position["payload"]["activityGeneration"] > 0


def test_speech_response_ack_is_correlated_and_stale_input_is_rejected(client: TestClient):
    client.post("/dev/lesson/start", json={"index": 9, "studentId": "s01"})
    core = client.app.state.core
    while core.runner._pending_playback_turns:
        turn_id = core.runner._pending_playback_turns[0]
        client.portal.call(core.runner.on_playback_started, turn_id)
        client.portal.call(core.runner.on_playback_finished, turn_id)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps({"v": 3, "type": "client.hello", "payload": {"role": "control"}}))
        snapshot, _ = handshake(ws)
        ws.send_text(json.dumps({
            "v": 3,
            "type": "capability.report",
            "payload": {
                "clientInstanceId": "control-test",
                "connectionEpoch": 1,
                "role": "control",
                "capabilities": {"audioCapture": True},
                "reportedAt": 1,
            },
        }))
        position = snapshot["payload"]["lesson"]
        assignment = snapshot["payload"]["assignment"]
        capture = snapshot["payload"]["capture"]

        ws.send_text(json.dumps({
            "v": 3,
            "type": "student.speech.final",
            "payload": {
                "text": "I like cats",
                "confidence": 0.99,
                "utteranceId": "utt-stale",
                "assignmentId": assignment["assignmentId"],
                "responseTurnId": assignment["responseTurnId"],
                "captureId": capture["captureId"],
                "captureOutcome": "speech",
                "activityId": position["activityId"],
                "activityGeneration": position["activityGeneration"],
            },
        }))
        rejected_frames = [ws.receive_json() for _ in range(2)]
        assert {f["type"] for f in rejected_frames} == {
            "error", "student.response.accepted"
        }
        rejected = next(
            f for f in rejected_frames if f["type"] == "student.response.accepted"
        )
        assert rejected["payload"] == {
            "utteranceId": "utt-stale", "outcome": "rejected"
        }

        correlation = {
            "captureId": capture["captureId"],
            "assignmentId": assignment["assignmentId"],
            "responseTurnId": assignment["responseTurnId"],
        }
        ws.send_text(json.dumps({
            "v": 3,
            "type": "response.capture.ready",
            "payload": {**correlation, "status": "ready"},
        }))
        ws.send_text(json.dumps({
            "v": 3,
            "type": "response.capture.started",
            "payload": correlation,
        }))

        ws.send_text(json.dumps({
            "v": 3,
            "type": "student.speech.final",
            "payload": {
                "text": "I like cats",
                "confidence": 0.95,
                "utteranceId": "utt-good",
                "assignmentId": assignment["assignmentId"],
                "responseTurnId": assignment["responseTurnId"],
                "captureId": capture["captureId"],
                "captureOutcome": "speech",
                "activityId": position["activityId"],
                "activityGeneration": position["activityGeneration"],
            },
        }))
        frames = []
        for _ in range(12):
            frames.append(ws.receive_json())
            if frames[-1]["type"] == "student.response.accepted":
                break
        accepted = next(f for f in frames if f["type"] == "student.response.accepted")
        assert accepted["payload"] == {"utteranceId": "utt-good", "outcome": "correct"}


def test_stage_cannot_submit_broadcast_speech_capability(client: TestClient):
    client.post("/dev/lesson/start", json={"index": 9, "studentId": "s01"})
    core = client.app.state.core
    while core.runner._pending_playback_turns:
        turn_id = core.runner._pending_playback_turns[0]
        client.portal.call(core.runner.on_playback_started, turn_id)
        client.portal.call(core.runner.on_playback_finished, turn_id)
    with client.websocket_connect("/ws") as ws:
        ws.send_text(json.dumps(HELLO))
        snapshot, _ = handshake(ws)
        assignment = snapshot["payload"]["assignment"]
        capture = snapshot["payload"]["capture"]
        position = snapshot["payload"]["lesson"]
        ws.send_text(json.dumps({
            "v": 3,
            "type": "student.speech.final",
            "payload": {
                "text": "I like cats",
                "confidence": 0.99,
                "utteranceId": "utt-stage",
                "assignmentId": assignment["assignmentId"],
                "responseTurnId": assignment["responseTurnId"],
                "captureId": capture["captureId"],
                "captureOutcome": "speech",
                "activityId": position["activityId"],
                "activityGeneration": position["activityGeneration"],
            },
        }))
        denied = ws.receive_json()
        assert denied["type"] == "error"
        assert denied["payload"]["code"] == "control_input_lease_required"
