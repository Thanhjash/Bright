from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from class_session import (
    AssignmentRejected,
    CapabilityLeaseRegistry,
    ClassSessionController,
    ResponseAssignmentRegistry,
    SessionState,
)
from data_policy import DataPolicy, outbound_interaction
from db import open_database
from runner import LessonRunner, grade
from state import StateStore
from bright_contracts import Expect


async def test_response_capability_is_exactly_once_and_ignores_client_identity():
    registry = ResponseAssignmentRegistry(default_ttl_s=10)
    assignment = registry.issue(
        session_id="class-session",
        decision_revision=7,
        activity_id="food-request",
        activity_generation=3,
        target="learner-17",
        scope="selected_individual",
        capture_scope="answer_station",
        skill_ids=("polite_request",),
        evidence_policy="individual",
        capture=True,
    )
    registry.open(assignment.assignment_id)
    claimed = await registry.claim(
        assignment_id=assignment.assignment_id,
        response_turn_id=assignment.response_turn_id,
        capture_id=assignment.capture_id,
        session_id="class-session",
        decision_revision=7,
        activity_id="food-request",
        activity_generation=3,
    )
    assert claimed.target == "learner-17"
    with pytest.raises(AssignmentRejected, match="already claimed"):
        await registry.claim(
            assignment_id=assignment.assignment_id,
            response_turn_id=assignment.response_turn_id,
            capture_id=assignment.capture_id,
            session_id="class-session",
            decision_revision=7,
            activity_id="food-request",
            activity_generation=3,
        )


def test_hosted_data_policy_drops_raw_and_synthetic_dev_requires_explicit_marker():
    payload = {"text": "My real voice", "studentId": "learner-7", "optionId": "apple"}
    hosted = outbound_interaction(
        policy=DataPolicy.HOSTED_SEMANTIC,
        activity_id="a1",
        response_kind="speech",
        outcome="correct",
        payload=payload,
    ).render()
    assert "My real voice" not in hosted and "learner-7" not in hosted
    unmarked = outbound_interaction(
        policy=DataPolicy.SYNTHETIC_DEV,
        activity_id="a1",
        response_kind="speech",
        outcome="correct",
        payload=payload,
    ).render()
    assert "My real voice" not in unmarked
    marked = outbound_interaction(
        policy=DataPolicy.SYNTHETIC_DEV,
        activity_id="a1",
        response_kind="speech",
        outcome="correct",
        payload={**payload, "synthetic": True, "syntheticFixtureId": "fixture-voice-01"},
    ).render()
    assert "My real voice" in marked
    missing_provenance = outbound_interaction(
        policy=DataPolicy.SYNTHETIC_DEV,
        activity_id="a1",
        response_kind="speech",
        outcome="correct",
        payload={**payload, "synthetic": True},
    ).render()
    assert "My real voice" not in missing_provenance


def test_low_confidence_exact_speech_is_uncertain_not_near():
    expect = Expect(kind="speech", correct="I would like rice, please")
    assert grade(expect, "speech", {"text": "I would like rice, please", "confidence": 0.3}) == "uncertain"


def test_observation_dedupe_and_checkpoint_are_restart_safe(tmp_path):
    path = tmp_path / "class.db"
    db = open_database(path)
    session_id = db.start_session(lesson_id="market")
    first = db.record_observation(
        "learner-1",
        "polite_request",
        "correct",
        "activity=request",
        session_id,
        response_turn_id="response-1",
        activity_id="request",
    )
    replay = db.record_observation(
        "learner-1",
        "polite_request",
        "correct",
        "activity=request",
        session_id,
        response_turn_id="response-1",
        activity_id="request",
    )
    assert replay == first
    assert len(db.list_observations(session_id=session_id)) == 1
    db.save_session_checkpoint(
        session_id=session_id,
        decision_revision=4,
        activity_id="request",
        activity_generation=9,
        session_state="RUNNING",
        snapshot={"namedTurnsUsed": 2},
    )
    db.close()
    reopened = open_database(path)
    checkpoint = reopened.get_session_checkpoint(session_id)
    assert checkpoint["decision_revision"] == 4
    assert checkpoint["snapshot"] == {"namedTurnsUsed": 2}
    reopened.close()


def test_stage_output_and_control_input_owners_are_separate():
    core = SimpleNamespace(runner=None, session_controller=None)
    leases = CapabilityLeaseRegistry(core, ttl_s=30)
    stage = SimpleNamespace(id=1, role="stage")
    control = SimpleNamespace(id=2, role="control")
    stage_report = SimpleNamespace(
        role="stage", client_instance_id="stage-a", connection_epoch=1,
        capabilities={"audioPlayback": True},
    )
    control_report = SimpleNamespace(
        role="control", client_instance_id="control-a", connection_epoch=1,
        capabilities={"audioCapture": True},
    )
    assert leases.report(stage, stage_report) is not None
    assert leases.report(control, control_report) is None
    assert leases.owns_audio(stage) and not leases.owns_input(stage)
    assert leases.owns_input(control) and not leases.owns_audio(control)


async def test_missing_playback_ack_never_arms_activity(tiny_lesson, bus, store):
    tiny_lesson.activities[4].narration = [SimpleNamespace(text="Your turn", audio_asset=None, act=None)]
    runner = LessonRunner(
        bus,
        store,
        tiny_lesson,
        silence_timeout_s=0.05,
        playback_ack_timeout_s=0.01,
        publish_speech=lambda *_args, **_kwargs: "turn-prompt",
    )
    await runner.start(4)
    await __import__("asyncio").sleep(0.08)
    assert store.scene.overlay is None or store.scene.overlay.listening is not True
    assert runner._timer is None
    await runner.stop()


async def test_fair_queue_has_cooldown_and_bounded_named_budget(core):
    controller = core.session_controller
    roster = [
        {"id": f"l{i}", "displayName": f"Learner {i}", "seat": str(i)}
        for i in range(10)
    ]
    core.session_id = core.db.start_session(lesson_id="market")
    controller.configure_roster(roster, [item["id"] for item in roster])
    targets = [controller._next_fair_target() for _ in range(10)]
    assert targets[:8] == list(dict.fromkeys(targets[:8]))
    assert targets[8:] == [None, None]
    assert all(target not in targets[max(0, i - 3):i] for i, target in enumerate(targets[:8]))


async def test_controller_start_initializes_runner_lifecycle_before_first_commit(core):
    controller = core.session_controller
    runner = core.runner

    assert runner.running is False
    await controller.start(2)

    assert runner.running is True
    assert runner.finished is False
    assert runner.paused is False
    assert runner.current.id == "a3"


async def test_invalid_roster_is_rejected_before_session_or_conversation_mutation(core):
    assert core.session_id is None
    assert core.conversations.conversation_id is None

    with pytest.raises(ValueError, match="1..40"):
        await core.start_lesson(0, roster=[])

    assert core.session_id is None
    assert core.conversations.conversation_id is None
    assert core.runner.running is False


async def test_capture_watchdog_pauses_if_capture_never_starts(core):
    controller = core.session_controller
    controller.capture_ready_timeout_s = 0.02
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)
    while core.runner._pending_playback_turns:
        turn_id = core.runner._pending_playback_turns[0]
        assert core.runner.on_playback_started(turn_id)
        assert core.runner.on_playback_finished(turn_id)

    assignment = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert assignment is not None
    controller.note_capture_ready({
        "assignmentId": assignment.assignment_id,
        "responseTurnId": assignment.response_turn_id,
        "captureId": assignment.capture_id,
        "status": "ready",
    })

    await __import__("asyncio").sleep(0.05)

    assert controller.session_state == SessionState.PAUSED
    assert controller.pause_reason == "capture_start_deadline_expired"
    assert core.runner.paused is True
    assert core.runner.index == 4


async def test_speech_claim_requires_ready_and_started_capture(core):
    controller = core.session_controller
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)
    while core.runner._pending_playback_turns:
        turn_id = core.runner._pending_playback_turns[0]
        core.runner.on_playback_started(turn_id)
        core.runner.on_playback_finished(turn_id)
    assignment = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    payload = {
        "assignmentId": assignment.assignment_id,
        "responseTurnId": assignment.response_turn_id,
        "captureId": assignment.capture_id,
    }

    with pytest.raises(AssignmentRejected, match="capture has not started"):
        await controller.claim_response(payload)

    controller.note_capture_ready({**payload, "status": "ready"})
    with pytest.raises(AssignmentRejected, match="capture has not started"):
        await controller.claim_response(payload)

    controller.note_capture_started(payload)
    assert await controller.claim_response(payload) is assignment


async def test_control_state_is_owned_and_published_by_controller(core):
    controller = core.session_controller
    sub = core.bus.subscribe(role="control")
    await controller.start(2)
    while not sub.queue.empty():
        sub.queue.get_nowait()

    await controller.control("pause")
    assert controller.session_state == SessionState.PAUSED
    assert controller.pause_reason == "facilitator_pause"
    paused = [sub.queue.get_nowait() for _ in range(sub.queue.qsize())]
    status = next(frame for frame in paused if frame["type"] == "classroom.status")
    assert set(status["payload"]) == {
        "liveness", "readiness", "teachable", "lessonId", "reason", "recovery"
    }
    assert any(frame["type"] == "class.session.updated" for frame in paused)

    await controller.control("resume")
    assert controller.session_state == SessionState.RUNNING
    assert controller.pause_reason is None
    assert core.runner.paused is False
