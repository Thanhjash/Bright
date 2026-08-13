"""Product-truth gates for the autonomous classroom lesson contract."""

from __future__ import annotations

import json
import importlib.util
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTRACTS = ROOT / "packages" / "contracts" / "python"
sys.path.insert(0, str(CONTRACTS))

from bright_contracts import LessonRun, PROTOCOL_VERSION  # noqa: E402
from pydantic import ValidationError
import pytest


MARKET_SOURCE = ROOT / "content" / "lessons" / "market-food" / "market-food-01.md"
MARKET_RUN = MARKET_SOURCE.with_suffix(".run.json")


def test_wire_and_lesson_schema_versions_are_independent() -> None:
    run = LessonRun.model_validate_json(MARKET_RUN.read_text(encoding="utf-8"))
    assert run.v == PROTOCOL_VERSION == 3
    assert run.lesson_schema_version == 1
    assert run.delivery_mode == "autonomous_class"


def test_market_lesson_is_honestly_draft_and_has_a_full_period_plan() -> None:
    run = LessonRun.model_validate_json(MARKET_RUN.read_text(encoding="utf-8"))
    assert run.curriculum is not None
    assert run.curriculum.approval_status == "draft"
    assert "UNASSIGNED" in run.curriculum.approver
    assert run.session_plan is not None
    assert 35 <= run.session_plan.duration_min <= 45
    assert all(activity.teaching is not None for activity in run.activities)
    assert {skill for activity in run.activities for skill in activity.teaching.skill_ids} == {
        "food_recognition",
        "polite_request",
    }


def test_market_lesson_lints_compiles_and_all_simulated_paths_finish() -> None:
    lint = subprocess.run(
        [sys.executable, "tools/lesson-lint/lesson_lint.py", str(MARKET_SOURCE), "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert lint.returncode == 0, lint.stdout + lint.stderr

    play = subprocess.run(
        [sys.executable, "tools/lesson-play/lesson_play.py", str(MARKET_RUN), "--json"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert play.returncode == 0, play.stdout + play.stderr
    report = json.loads(play.stdout)
    assert report["modes"]
    run = LessonRun.model_validate_json(MARKET_RUN.read_text(encoding="utf-8"))
    assert run.session_plan is not None
    # `durationMin` includes teaching, EXIT and CLOSURE.  Reserve protects the
    # final close only; it cannot be declared by stealing authored lesson time.
    assert run.session_plan.duration_min == 45
    assert run.session_plan.closure_reserve_s == 60
    for mode, result in report["modes"].items():
        assert result["stalls"] == [], mode
        assert result["unhandled"] == [], mode
        assert 35 <= result["minutes"] <= 45, mode
        assert result["minutes"] <= run.session_plan.duration_min, mode


def test_market_authored_paths_enter_closure_inside_the_protected_final_minute() -> None:
    """Treat EXIT as lesson time and reserve only the actual CLOSURE stage.

    This is a fast virtual-clock check over the real runner, not a claim that
    browser audio has already completed within those timings.
    """
    spec = importlib.util.spec_from_file_location(
        "bright_lesson_play", ROOT / "tools" / "lesson-play" / "lesson_play.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)

    run = LessonRun.model_validate_json(MARKET_RUN.read_text(encoding="utf-8"))
    assert run.session_plan is not None
    durations = {activity.id: float(activity.duration_s or 0) for activity in run.activities}
    closure = next(activity for activity in run.activities if activity.teaching.stage == "CLOSURE")
    assert durations[closure.id] <= run.session_plan.closure_reserve_s
    teaching_deadline_s = run.session_plan.duration_min * 60 - run.session_plan.closure_reserve_s

    import asyncio

    for mode in ("correct", "near", "wrong", "silence", "mixed"):
        trace = asyncio.run(module.play(run, mode))
        assert closure.id in trace.steps, mode
        closure_index = trace.steps.index(closure.id)
        before_closure_s = sum(durations[activity_id] for activity_id in trace.steps[:closure_index])
        assert before_closure_s <= teaching_deadline_s, (mode, before_closure_s, teaching_deadline_s)


def test_draft_market_lesson_cannot_be_packaged_as_a_release() -> None:
    release = subprocess.run(
        [sys.executable, "tools/lesson-lint/lesson_lint.py", str(MARKET_SOURCE), "--release"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert release.returncode == 1
    assert "curriculum approval is not 'approved'" in release.stdout
    compile_release = subprocess.run(
        [
            sys.executable,
            "tools/lesson-compile/lesson_compile.py",
            str(MARKET_SOURCE),
            "--release",
            "--stdout",
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert compile_release.returncode == 1
    assert "curriculum approval is not 'approved'" in compile_release.stderr


def test_every_graded_autonomous_activity_has_uncertain_and_unhandled_recovery() -> None:
    run = LessonRun.model_validate_json(MARKET_RUN.read_text(encoding="utf-8"))
    for activity in run.activities:
        if activity.expect is None or activity.expect.kind == "none":
            continue
        branches = {branch.on for branch in activity.branches or []}
        assert {"uncertain", "unhandled"} <= branches, activity.id


def test_named_turn_budget_equals_explicit_selected_individual_speech_stations() -> None:
    run = LessonRun.model_validate_json(MARKET_RUN.read_text(encoding="utf-8"))
    assert run.session_plan is not None
    stations = [
        activity
        for activity in run.activities
        if activity.expect is not None
        and activity.expect.kind == "speech"
        and activity.teaching is not None
        and activity.teaching.response_scope == "selected_individual"
        and activity.teaching.participation_mode == "selected_individual"
    ]
    assert len(stations) == run.session_plan.named_turn_budget == 8
    assert [station.id for station in stations] == [
        "answer_station_01_apple",
        "answer_station_02_banana",
        "answer_station_03_bread",
        "answer_station_04_egg",
        "answer_station_05_rice",
        "answer_station_06_water",
        "answer_station_07_apple",
        "answer_station_08_bread",
    ]
    asserted_requests = {
        answer
        for station in stations
        for answer in (station.expect.correct or [])
    }
    assert {
        "i would like an apple please",
        "i would like a banana please",
        "i would like bread please",
        "i would like an egg please",
        "i would like rice please",
        "i would like water please",
    } <= asserted_requests
    assert all(activity.duration_s == 30 for activity in stations)

    recoveries = [
        activity
        for activity in run.activities
        if activity.id.startswith("answer_station_help_")
    ]
    assert len(recoveries) == len(stations)
    assert all(activity.duration_s == 20 for activity in recoveries)
    assert all(
        activity.teaching is not None
        and activity.teaching.response_scope == "choral"
        and activity.teaching.participation_mode == "whole_class"
        for activity in recoveries
    )
    assert [
        activity.id
        for activity in run.activities
        if activity.teaching is not None and activity.teaching.stage == "CLOSURE"
    ] == ["closure"]


def test_lint_rejects_named_turn_budget_that_does_not_match_authored_stations(tmp_path: Path) -> None:
    bad_lesson = tmp_path / MARKET_SOURCE.name
    bad_lesson.write_text(
        MARKET_SOURCE.read_text(encoding="utf-8").replace("namedTurnBudget: 8", "namedTurnBudget: 7", 1),
        encoding="utf-8",
    )
    lint = subprocess.run(
        [sys.executable, "tools/lesson-lint/lesson_lint.py", str(bad_lesson), "--strict"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert lint.returncode == 1
    assert "namedTurnBudget does not match authored selected-individual speech stations" in lint.stdout


def test_autonomous_schema_fails_closed_on_missing_teaching_or_unknown_fields() -> None:
    raw = json.loads(MARKET_RUN.read_text(encoding="utf-8"))
    raw["activities"][0].pop("teaching")
    with pytest.raises(ValidationError, match="teaching metadata"):
        LessonRun.model_validate(raw)

    raw = json.loads(MARKET_RUN.read_text(encoding="utf-8"))
    raw["activities"][0]["mysteryPolicy"] = True
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        LessonRun.model_validate(raw)
