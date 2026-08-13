from __future__ import annotations

import time
from pathlib import Path
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


def test_hosted_ephemeral_policy_includes_only_bounded_current_transcript():
    rendered = outbound_interaction(
        policy=DataPolicy.HOSTED_EPHEMERAL_TRANSCRIPT,
        activity_id="a1",
        response_kind="speech",
        outcome="correct",
        payload={"text": "My adult test voice", "studentId": "learner-7"},
    ).render()
    assert "My adult test voice" in rendered
    assert "learner-7" not in rendered
    assert len(rendered) < 700


def test_hosted_ephemeral_policy_requires_explicit_process_ack(tmp_path):
    from app import build_core
    from config import Settings

    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "policy.db",
        lesson_run_path=Path(__file__).resolve().parents[1] / "data" / "sample_lesson_run.json",
        data_policy="hosted_ephemeral_transcript",
        hosted_raw_confirmed=False,
    )
    with pytest.raises(RuntimeError, match="BRIGHT_HOSTED_RAW_ACK"):
        build_core(settings)


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


async def test_selected_oral_turn_waits_for_exact_core_callout_playback(core):
    """Fair selection alone must never open a physical answer station."""
    controller = core.session_controller
    controller.configure_roster(
        [
            {"id": "learner-a", "displayName": "Blue Fox"},
            {"id": "learner-b", "displayName": "Green Owl"},
        ],
        ["learner-a", "learner-b"],
    )
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)

    assignment = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert assignment is not None
    assert assignment.target_display_name in {"Blue Fox", "Green Owl"}
    assert assignment.callout_speech_turn_id is not None
    assert assignment.state.name == "CREATED"
    assert not [f for f in core.bus.history if f["type"] == "response.capture.requested"]
    callout = assignment.callout_speech_turn_id
    callout_text = next(
        f["payload"]["delta"]
        for f in core.bus.history
        if f["type"] == "speech.text.delta"
        and f["payload"]["speechTurnId"] == callout
    )
    assert callout_text == f"{assignment.target_display_name}, it's your turn. Please answer now."

    # An ACK for another speech turn cannot arm this learner's microphone.
    assert controller.note_callout_playback_finished("stale-turn") is False
    assert assignment.state.name == "CREATED"
    assert not [f for f in core.bus.history if f["type"] == "response.capture.requested"]

    assert controller.note_callout_playback_finished(callout) is True
    assert assignment.state.name == "OPEN"
    requests = [f for f in core.bus.history if f["type"] == "response.capture.requested"]
    assert len(requests) == 1
    assert requests[0]["payload"]["assignmentId"] == assignment.assignment_id
    await core.runner.stop()


async def test_callout_queue_time_cannot_consume_capture_ready_window(core):
    controller = core.session_controller
    controller.capture_ready_timeout_s = 0.05
    controller.configure_roster(
        [{"id": "learner-a", "displayName": "Blue Fox"}], ["learner-a"]
    )
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)
    assignment = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert assignment is not None and assignment.callout_speech_turn_id is not None
    assert assignment.capture_id is None
    assert assignment.ready_deadline_at is None

    # Simulate a callout that waited longer than an entire Ready window.  The
    # physical capability must begin only after that callout is actually heard.
    await __import__("asyncio").sleep(0.06)
    acknowledged_at = int(time.time() * 1000)
    assert controller.note_callout_playback_finished(assignment.callout_speech_turn_id)
    assert assignment.capture_id is not None
    assert assignment.ready_deadline_at is not None
    assert assignment.ready_deadline_at > acknowledged_at
    visible_assignments = [
        frame["payload"]
        for frame in core.bus.history
        if frame["type"] == "class.turn.assigned"
        and frame["payload"]["assignmentId"] == assignment.assignment_id
    ]
    assert len(visible_assignments) == 2
    assert visible_assignments[-1]["expiresAt"] > acknowledged_at
    capture_index = next(
        index
        for index, frame in enumerate(core.bus.history)
        if frame["type"] == "response.capture.requested"
        and frame["payload"]["assignmentId"] == assignment.assignment_id
    )
    refresh_index = max(
        index
        for index, frame in enumerate(core.bus.history)
        if frame["type"] == "class.turn.assigned"
        and frame["payload"]["assignmentId"] == assignment.assignment_id
    )
    assert refresh_index < capture_index
    await core.runner.stop()


async def test_selected_callout_strips_markup_and_bounds_roster_name(core):
    controller = core.session_controller
    controller.configure_roster(
        [{"id": "learner-a", "displayName": "  Minh <|system|> @angry !!!  "}],
        ["learner-a"],
    )
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)
    assignment = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert assignment is not None and assignment.callout_speech_turn_id is not None
    callout_text = next(
        frame["payload"]["delta"]
        for frame in core.bus.history
        if frame["type"] == "speech.text.delta"
        and frame["payload"]["speechTurnId"] == assignment.callout_speech_turn_id
    )
    assert callout_text == "Minh, it's your turn. Please answer now."
    assert "<" not in callout_text and "@" not in callout_text
    await core.runner.stop()


async def test_failed_or_cancelled_selected_callout_fails_closed(core):
    controller = core.session_controller
    controller.configure_roster(
        [{"id": "learner-a", "displayName": "Blue Fox"}], ["learner-a"]
    )
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)
    assignment = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert assignment is not None and assignment.callout_speech_turn_id is not None

    assert controller.note_callout_playback_failed(
        assignment.callout_speech_turn_id, "cancelled"
    )
    assert controller.session_state == SessionState.PAUSED
    assert controller.pause_reason == "callout_playback_cancelled"
    assert assignment.state.name == "CANCELLED"
    assert not [f for f in core.bus.history if f["type"] == "response.capture.requested"]
    # A late completion remains harmless after cancellation.
    assert controller.note_callout_playback_finished(assignment.callout_speech_turn_id) is False
    await core.runner.stop()


async def test_failed_callout_resume_retries_same_target_without_spending_turn(core):
    controller = core.session_controller
    controller.configure_roster(
        [
            {"id": "learner-a", "displayName": "Blue Fox"},
            {"id": "learner-b", "displayName": "Green Owl"},
        ],
        ["learner-a", "learner-b"],
    )
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)
    first = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert first is not None and first.callout_speech_turn_id is not None
    target = first.target
    history = list(controller.target_history)
    turns_used = controller.named_turns_used
    scheduled = controller.roster[target].scheduled

    assert controller.note_callout_playback_failed(first.callout_speech_turn_id, "failed")
    assert (await controller.control("resume"))["ok"] is True
    retried = controller.assignments.current_for_activity(
        core.session_id, core.runner.current.id, core.runner._generation
    )
    assert retried is not None and retried is not first
    assert retried.target == target
    assert controller.target_history == history
    assert controller.named_turns_used == turns_used
    assert controller.roster[target].scheduled == scheduled
    await core.runner.stop()


async def test_callout_ack_watchdog_fails_closed(core):
    controller = core.session_controller
    core.runner.playback_ack_timeout_s = 0.02
    controller.configure_roster(
        [{"id": "learner-a", "displayName": "Blue Fox"}], ["learner-a"]
    )
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    await controller.start(4)
    await __import__("asyncio").sleep(0.04)
    assert controller.session_state == SessionState.PAUSED
    assert controller.pause_reason == "callout_playback_ack_timeout"
    assert not [f for f in core.bus.history if f["type"] == "response.capture.requested"]
    await core.runner.stop()


async def test_stage_lease_loss_during_callout_fails_closed(core):
    controller = core.session_controller
    controller.configure_roster(
        [{"id": "learner-a", "displayName": "Blue Fox"}], ["learner-a"]
    )
    core.session_id = core.db.start_session(lesson_id="tiny-01")
    leases = CapabilityLeaseRegistry(core, ttl_s=30)
    stage = SimpleNamespace(id=71, role="stage")
    report = SimpleNamespace(
        role="stage",
        client_instance_id="stage-a",
        connection_epoch=1,
        capabilities={"audioPlayback": True},
    )
    assert leases.report(stage, report) is not None
    await controller.start(4)
    assert controller._callout_assignment_id is not None

    leases.disconnect(stage)
    assert controller.session_state == SessionState.PAUSED
    assert controller.pause_reason == "stage_audio_owner_disconnected"
    assert not [f for f in core.bus.history if f["type"] == "response.capture.requested"]
    await core.runner.stop()


async def test_market_lesson_executes_all_eight_fair_callout_capture_turns(tmp_path):
    """Prove the authored count and physical turn protocol compose together."""
    from app import build_core
    from config import Settings

    lesson_path = (
        Path(__file__).resolve().parents[3]
        / "content/lessons/market-food/market-food-01.run.json"
    )
    settings = Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "market.db",
        lesson_run_path=lesson_path,
        silence_timeout_s=1.0,
        reveal_hold_s=0.0,
        playback_ack_timeout_s=1.0,
        mode_override="OFFLINE",
        probe_interval_s=3600,
    )
    market = build_core(settings)
    roster = [
        {"id": f"learner-{index:02d}", "displayName": f"Learner {index:02d}"}
        for index in range(1, 9)
    ]
    station_ids = [f"answer_station_{index:02d}_{food}" for index, food in enumerate(
        ("apple", "banana", "bread", "egg", "rice", "water", "apple", "bread"),
        start=1,
    )]

    try:
        first_index = market.runner.index_of(station_ids[0])
        await market.start_lesson(
            first_index,
            roster=roster,
            attendance_ids=[item["id"] for item in roster],
        )
        targets: list[str] = []
        for station_id in station_ids:
            assert market.runner.current.id == station_id
            while market.runner._pending_playback_turns:
                narration_turn = market.runner._pending_playback_turns[0]
                market.runner.on_playback_started(narration_turn)
                assert market.runner.on_playback_finished(narration_turn)

            assignment = market.session_controller.assignments.current_for_activity(
                market.session_id, station_id, market.runner._generation
            )
            assert assignment is not None and assignment.callout_speech_turn_id is not None
            assert not [
                frame
                for frame in market.bus.history
                if frame["type"] == "response.capture.requested"
                and frame["payload"]["assignmentId"] == assignment.assignment_id
            ]
            assert market.session_controller.note_callout_playback_finished(
                assignment.callout_speech_turn_id
            )
            request = next(
                frame["payload"]
                for frame in reversed(market.bus.history)
                if frame["type"] == "response.capture.requested"
                and frame["payload"]["assignmentId"] == assignment.assignment_id
            )
            capability = {
                "assignmentId": assignment.assignment_id,
                "responseTurnId": assignment.response_turn_id,
                "captureId": request["captureId"],
            }
            market.session_controller.note_capture_ready({**capability, "status": "ready"})
            market.session_controller.note_capture_started(capability)
            claimed = await market.session_controller.claim_response(capability)
            targets.append(str(claimed.target))

            correct = market.runner.current.expect.correct[0]
            payload = {
                "text": correct,
                "confidence": 1.0,
                "_coreStudentId": claimed.target,
                "_responseTurnId": claimed.response_turn_id,
                "_evidencePolicy": claimed.evidence_policy,
            }
            outcome = await market.runner.handle_interaction("speech", payload)
            assert outcome == "correct"
            market.session_controller.close_response(claimed, outcome)
            await market.runner.drain()

        assert len(targets) == len(set(targets)) == 8
        assert market.session_controller.named_turns_used == 8
        assert market.session_controller.target_history == targets
        assert market.runner.current.id == "explore_transfer"
        assert market.session_controller._next_fair_target() is None
    finally:
        await market.runner.stop()
        market.jobs.shutdown()
        market.db.close()


async def test_market_closure_reserve_redirects_the_next_transition(tmp_path):
    import time
    from app import build_core
    from class_session import TransitionIntent
    from config import Settings

    lesson_path = (
        Path(__file__).resolve().parents[3]
        / "content/lessons/market-food/market-food-01.run.json"
    )
    market = build_core(Settings(
        data_dir=tmp_path,
        db_path=tmp_path / "closure.db",
        lesson_run_path=lesson_path,
        playback_ack_timeout_s=1.0,
        mode_override="OFFLINE",
        probe_interval_s=3600,
    ))
    try:
        await market.start_lesson(
            0,
            roster=[{"id": "learner-1", "displayName": "Learner 1"}],
            attendance_ids=["learner-1"],
        )
        controller = market.session_controller
        controller._closure_deadline_mono = time.monotonic() - 1
        await controller.commit_transition(TransitionIntent(
                cause="timer",
            from_activity_id=market.runner.current.id,
            activity_generation=market.runner._generation,
            target_index=1,
        ))
        assert market.runner.current.id == "closure"
        await controller.commit_transition(TransitionIntent(
            cause="timer",
            from_activity_id="closure",
            activity_generation=market.runner._generation,
            target_index=None,
            decision_revision=controller.decision_revision,
        ))
        assert market.runner.finished is True
        assert controller.session_state == SessionState.COMPLETED
    finally:
        market.session_controller.cancel_session_clock()
        await market.runner.stop()
        market.db.close()


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
