from __future__ import annotations

import pytest

from bright_contracts import LessonPosition
from state import StateStore


def test_state_version_is_strictly_monotonic(store: StateStore):
    seen = [store.state_version]
    store.set_scene("text", {"text": "one"})
    seen.append(store.state_version)
    store.set_scene("vocabulary", {"items": [], "interaction": "none"})
    seen.append(store.state_version)
    store.set_overlay(subtitle="hello")
    seen.append(store.state_version)
    store.update_lesson(activity_index=1)
    seen.append(store.state_version)
    store.set_mode("FULL")
    seen.append(store.state_version)

    assert seen == sorted(seen)
    assert len(set(seen)) == len(seen)
    assert all(b == a + 1 for a, b in zip(seen, seen[1:]))


def test_scene_carries_the_current_state_version(store: StateStore):
    scene = store.set_scene("text", {"text": "hi"})
    assert scene.state_version == store.state_version
    assert store.scene.state_version == store.state_version


def test_no_op_mode_set_does_not_bump(store: StateStore):
    before = store.state_version
    assert store.set_mode(store.mode) is False
    assert store.state_version == before


def test_mode_badge_is_hidden_in_full(store: StateStore):
    store.set_scene("text", {"text": "hi"})
    assert store.scene.overlay.mode_badge == "OFFLINE"
    store.set_mode("DEGRADED")
    assert store.scene.overlay.mode_badge == "DEGRADED"
    store.set_mode("FULL")
    assert store.scene.overlay.mode_badge is None
    # and a fresh scene in FULL still has no badge
    store.set_scene("idle", {})
    assert store.scene.overlay.mode_badge is None


def test_snapshot_is_a_copy(store: StateStore):
    store.set_scene("text", {"text": "hi"})
    snap = store.snapshot()
    snap["scene"].props["text"] = "mutated"
    snap["lesson"].stage = "MUTATED"
    assert store.scene.props["text"] == "hi"
    assert store.lesson.stage != "MUTATED"
    assert set(snap) == {"scene", "lesson"}


def test_set_lesson_replaces_position(store: StateStore):
    position = LessonPosition(
        lessonId="l", classId="c", activityIndex=3, activityCount=9, stage="INPUT"
    )
    store.set_lesson(position)
    assert store.lesson.activity_index == 3
    assert store.lesson.activity_count == 9


def test_unknown_fields_are_rejected(store: StateStore):
    with pytest.raises(KeyError):
        store.set_overlay(nope=True)
    with pytest.raises(KeyError):
        store.update_lesson(nope=True)


def test_on_change_hook_fires_once_per_mutation():
    seen: list[int] = []
    store = StateStore(on_change=seen.append)
    store.set_scene("text", {"text": "a"})
    store.set_overlay(listening=True)
    assert seen == [2, 3]
