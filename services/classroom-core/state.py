"""The state store -- classroom-core is the only writer of state.

Holds the current Scene, LessonPosition and Mode.  Every mutation bumps
``stateVersion`` exactly once and the new version is stamped into the Scene, so
a Scene frame is always self-describing.

Single writer: all mutators take a re-entrant lock and never await, so a
mutation is atomic with respect to both the event loop and the apscheduler
thread pool.
"""

from __future__ import annotations

import threading
from typing import Any, Callable

import config  # noqa: F401  -- installs the bright_contracts import path
from bright_contracts import LessonPosition, Mode, Scene, SceneOverlay

IDLE_LESSON = LessonPosition(
    lesson_id="",
    class_id="",
    activity_index=0,
    activity_count=0,
    stage="IDLE",
    activity_id="",
    activity_generation=0,
)


class StateStore:
    def __init__(
        self,
        *,
        lesson: LessonPosition | None = None,
        mode: Mode = "OFFLINE",
        on_change: Callable[[int], None] | None = None,
    ) -> None:
        self._lock = threading.RLock()
        self._version = 1
        self._scene = Scene(state_version=1, kind="idle", props={}, overlay=SceneOverlay())
        self._lesson = (lesson or IDLE_LESSON).model_copy(deep=True)
        self._mode: Mode = mode
        self._on_change = on_change
        self._apply_mode_badge()

    # ------------------------------------------------------------- reading
    @property
    def state_version(self) -> int:
        return self._version

    @property
    def scene(self) -> Scene:
        with self._lock:
            return self._scene.model_copy(deep=True)

    @property
    def lesson(self) -> LessonPosition:
        with self._lock:
            return self._lesson.model_copy(deep=True)

    @property
    def mode(self) -> Mode:
        return self._mode

    def snapshot(self) -> dict[str, Any]:
        """The payload of ``scene.snapshot``."""
        with self._lock:
            return {
                "scene": self._scene.model_copy(deep=True),
                "lesson": self._lesson.model_copy(deep=True),
            }

    # ------------------------------------------------------------ writing
    def _bump(self) -> int:
        self._version += 1
        self._scene.state_version = self._version
        if self._on_change is not None:
            self._on_change(self._version)
        return self._version

    def _apply_mode_badge(self) -> None:
        overlay = self._scene.overlay or SceneOverlay()
        overlay.mode_badge = None if self._mode == "FULL" else self._mode  # type: ignore[assignment]
        self._scene.overlay = overlay

    def set_scene(
        self,
        kind: str,
        props: dict[str, Any] | None = None,
        overlay: SceneOverlay | dict[str, Any] | None = None,
    ) -> Scene:
        """Replace the scene wholesale. Scenes are never patched (PROTOCOL §2)."""
        with self._lock:
            if isinstance(overlay, dict):
                overlay = SceneOverlay.model_validate(overlay)
            new_overlay = overlay.model_copy(deep=True) if overlay else SceneOverlay()
            self._scene = Scene(
                state_version=self._version,
                kind=kind,  # type: ignore[arg-type]
                props=dict(props or {}),
                overlay=new_overlay,
            )
            self._apply_mode_badge()
            self._bump()
            return self._scene.model_copy(deep=True)

    def set_scene_props(self, props: dict[str, Any]) -> Scene:
        """Re-render the current scene kind with new props (still a whole scene)."""
        with self._lock:
            return self.set_scene(self._scene.kind, props, self._scene.overlay)

    def set_overlay(self, **fields: Any) -> Scene:
        with self._lock:
            overlay = (self._scene.overlay or SceneOverlay()).model_copy(deep=True)
            for key, value in fields.items():
                if not hasattr(overlay, key):
                    raise KeyError(f"unknown overlay field: {key}")
                setattr(overlay, key, value)
            self._scene.overlay = overlay
            self._apply_mode_badge()
            self._bump()
            return self._scene.model_copy(deep=True)

    def set_lesson(self, lesson: LessonPosition) -> LessonPosition:
        with self._lock:
            self._lesson = lesson.model_copy(deep=True)
            self._bump()
            return self._lesson.model_copy(deep=True)

    def update_lesson(self, **fields: Any) -> LessonPosition:
        with self._lock:
            lesson = self._lesson.model_copy(deep=True)
            for key, value in fields.items():
                if not hasattr(lesson, key):
                    raise KeyError(f"unknown lesson field: {key}")
                setattr(lesson, key, value)
            self._lesson = lesson
            self._bump()
            return self._lesson.model_copy(deep=True)

    def set_mode(self, mode: Mode) -> bool:
        """Returns True when the mode actually changed."""
        with self._lock:
            if mode == self._mode:
                return False
            self._mode = mode
            self._apply_mode_badge()
            self._bump()
            return True


__all__ = ["StateStore", "IDLE_LESSON"]
