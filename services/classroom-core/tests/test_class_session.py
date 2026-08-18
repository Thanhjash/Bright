from __future__ import annotations

from types import SimpleNamespace

import pytest

from data_policy import DataPolicy, outbound_interaction
from db import open_database
from leases import CapabilityLeaseRegistry


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
        data_policy="hosted_ephemeral_transcript",
        hosted_raw_confirmed=False,
    )
    with pytest.raises(RuntimeError, match="BRIGHT_HOSTED_RAW_ACK"):
        build_core(settings)


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
    core = SimpleNamespace()
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
