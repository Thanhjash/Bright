"""Parser for the authored lesson source format (``lesson.md``).

One parser, shared by ``lesson-lint`` and ``lesson-compile``, so the thing that
is validated is exactly the thing that is compiled.

The format, in full
-------------------

A lesson is Markdown with YAML frontmatter (architecture.md §8)::

    ---
    id: en-a1-market-01
    class: 7A
    title: At the Market
    ...
    ---

    # free prose: pedagogy notes, misconceptions, anything the teacher needs

    ## <activity_id> — OPTIONAL LABEL

    Free prose about this activity. Ignored by the tools, read by humans.

    ```yaml
    scene: choice
    props:
      prompt: "Which one do you drink?"
      options:
        - { id: water, text: water, asset: "asset://market/water.svg" }
    duration_s: 25
    say:
      - "Which one do you drink? @question"
    expect:
      kind: choice
      correct: water
      fuzzy: [rice]
    on:
      correct: { goto: next_one, say: ["Yes! @happy/Happy"] }
      wrong:   { goto: help_water, say: ["Look again. @curious"] }
      silence: { goto: help_water, say: ["Let me help. @think"] }
      timeout: { goto: help_water, say: ["Let us look. @think"] }
    ```

Every ``##`` section is one activity, in lesson order. The first fenced YAML
block in the section is the activity; prose around it is author notes.

Narration lines (``say:``)
    A plain string, optionally ending with an avatar cue::

        "Well done! @happy/Happy"      emotion + Live2D motion group
        "Hmm... @think"                emotion only
        "Look here. @curious:0.6"      emotion with intensity

    The mapping form is also accepted when you need pre-rendered audio::

        - { text: "Hello!", act: { emotion: happy, motion: Happy }, audio: "asset://narration/x.opus" }

Branches (``on:``)
    A mapping from outcome to ``{ goto, say }``. Outcomes are the six from
    PROTOCOL.md §4: ``correct near wrong silence timeout always``.
    ``goto: <id>`` at the top level of an activity is shorthand for
    ``on: { always: { goto: <id> } }``.

Nothing here calls an LLM. The expansion from a sketch to this file is done by a
person (with a frontier model helping); the compile from this file to
``lesson_run.json`` is deterministic, which is the only reason lint can promise
anything about the run.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

# The nine emotions, and the Live2D motion group each maps to.
# Mirrors bright_contracts.EMOTION_MOTION_GROUP -- note neutral -> "Idle".
EMOTION_MOTION_GROUP = {
    "happy": "Happy", "sad": "Sad", "angry": "Angry", "think": "Think",
    "surprised": "Surprise", "awkward": "Awkward", "question": "Question",
    "curious": "Curious", "neutral": "Idle",
}
EMOTIONS = tuple(EMOTION_MOTION_GROUP)

SCENE_KINDS = (
    "idle", "text", "image", "video", "vocabulary", "choice",
    "matching", "sentence_builder", "pronunciation", "roleplay", "explore",
)

OUTCOMES = ("correct", "near", "wrong", "silence", "timeout", "always")

_FRONTMATTER_RE = re.compile(r"\A---\r?\n(.*?)\r?\n---\r?\n?", re.DOTALL)
_HEADING_RE = re.compile(r"^##[ \t]+(?P<rest>\S.*?)[ \t]*$")
_FENCE_RE = re.compile(r"^(?P<fence>```+|~~~+)[ \t]*(?P<info>\w*)")
# " ... text @happy:0.6/Happy" -- the cue is always the tail of the line.
_CUE_RE = re.compile(
    r"\s+@(?P<emotion>[a-zA-Z_]+)(?::(?P<intensity>\d*\.?\d+))?(?:/(?P<motion>[A-Za-z][\w-]*))?\s*$"
)


class LessonSourceError(Exception):
    """Fatal: the file could not be parsed at all. Carries a line number."""

    def __init__(self, message: str, line: int = 0) -> None:
        super().__init__(message)
        self.message = message
        self.line = line


@dataclass
class Line:
    """One narration line, already split from its avatar cue."""

    text: str
    emotion: str | None = None
    intensity: float | None = None
    motion: str | None = None
    audio: str | None = None
    line_no: int = 0
    raw_emotion: str | None = None      # what the author typed, valid or not


@dataclass
class BranchSrc:
    on: str
    goto: str | None
    say: list[Line] = field(default_factory=list)
    line_no: int = 0


@dataclass
class ActivitySrc:
    id: str
    label: str | None
    scene: str | None
    props: dict[str, Any]
    say: list[Line]
    duration_s: int | None
    expect: dict[str, Any] | None
    branches: list[BranchSrc]
    heading_line: int
    yaml_line: int
    raw: str
    notes: str = ""

    def locate(self, needle: str) -> int:
        """Line number of the first occurrence of ``needle`` in this section,
        so an error can point at the offending line rather than the section."""
        idx = self.raw.find(needle)
        if idx < 0:
            return self.heading_line
        return self.heading_line + self.raw.count("\n", 0, idx)


@dataclass
class LessonSrc:
    path: Path
    meta: dict[str, Any]
    notes: str
    activities: list[ActivitySrc]

    @property
    def by_id(self) -> dict[str, ActivitySrc]:
        out: dict[str, ActivitySrc] = {}
        for activity in self.activities:
            out.setdefault(activity.id, activity)
        return out


# --------------------------------------------------------------- narration


def parse_line(value: Any, line_no: int = 0) -> Line:
    """A narration entry -> ``Line``. Accepts the string and mapping forms."""
    if isinstance(value, str):
        text = value.strip()
        match = _CUE_RE.search(text)
        if not match:
            return Line(text=text, line_no=line_no)
        emotion = match.group("emotion")
        intensity = match.group("intensity")
        motion = match.group("motion")
        clean = text[: match.start()].rstrip()
        known = emotion.lower() in EMOTION_MOTION_GROUP
        return Line(
            text=clean,
            emotion=emotion.lower() if known else None,
            raw_emotion=emotion,
            intensity=float(intensity) if intensity is not None else None,
            motion=motion,
            line_no=line_no,
        )
    if isinstance(value, dict):
        act = value.get("act") or {}
        emotion = act.get("emotion") if isinstance(act, dict) else act
        intensity = None
        if isinstance(emotion, dict):
            intensity = emotion.get("intensity")
            emotion = emotion.get("name")
        known = isinstance(emotion, str) and emotion.lower() in EMOTION_MOTION_GROUP
        return Line(
            text=str(value.get("text", "")).strip(),
            emotion=str(emotion).lower() if known else None,
            raw_emotion=str(emotion) if emotion is not None else None,
            intensity=float(intensity) if intensity is not None else None,
            motion=act.get("motion") if isinstance(act, dict) else None,
            audio=value.get("audio") or value.get("audioAsset"),
            line_no=line_no,
        )
    raise LessonSourceError(
        f"a narration line must be text (or a mapping with 'text'), got {type(value).__name__}",
        line_no,
    )


def _lines(block: Any, base_line: int, raw: str) -> list[Line]:
    if block is None:
        return []
    if isinstance(block, (str, dict)):
        block = [block]
    if not isinstance(block, list):
        raise LessonSourceError("'say:' must be a list of narration lines", base_line)
    out: list[Line] = []
    for entry in block:
        line = parse_line(entry, base_line)
        if line.text:
            idx = raw.find(line.text)
            if idx >= 0:
                line.line_no = base_line + raw.count("\n", 0, idx)
        out.append(line)
    return out


# ------------------------------------------------------------------ file


def _unbool_keys(value: Any) -> Any:
    """YAML 1.1 reads a bare ``on:`` key as the boolean ``True`` (likewise
    ``off``/``yes``/``no``). ``on:`` is the natural word for a branch table and
    authors will keep writing it, so map those keys back to text rather than
    forbidding the word. Silent data loss otherwise -- every branch in the file
    would simply vanish."""
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        for key, item in value.items():
            if key is True:
                key = "on"
            elif key is False:
                key = "off"
            out[key] = _unbool_keys(item)
        return out
    if isinstance(value, list):
        return [_unbool_keys(item) for item in value]
    return value


def _split_fenced_yaml(section: str) -> tuple[str | None, int]:
    """First fenced block in a section -> (body, 0-based offset of its first line)."""
    lines = section.splitlines()
    i = 0
    while i < len(lines):
        match = _FENCE_RE.match(lines[i])
        if match:
            fence = match.group("fence")[0] * 3
            body: list[str] = []
            j = i + 1
            while j < len(lines) and not lines[j].startswith(fence):
                body.append(lines[j])
                j += 1
            return "\n".join(body), i + 1
        i += 1
    return None, 0


def _strip_fenced(text: str) -> str:
    """Blank out fenced code blocks so a ``##`` inside one is not a heading."""
    out, in_fence, fence = [], False, ""
    for line in text.splitlines():
        match = _FENCE_RE.match(line)
        if not in_fence and match:
            in_fence, fence = True, match.group("fence")[0] * 3
            out.append("")
            continue
        if in_fence:
            out.append("")
            if line.startswith(fence):
                in_fence = False
            continue
        out.append(line)
    return "\n".join(out)


def parse_lesson(path: str | Path) -> LessonSrc:
    path = Path(path)
    text = path.read_text(encoding="utf-8")

    match = _FRONTMATTER_RE.match(text)
    if not match:
        raise LessonSourceError(
            "no YAML frontmatter. The file must start with a '---' line, the lesson "
            "settings (id, title, level, ...), then another '---' line.",
            1,
        )
    try:
        meta = _unbool_keys(yaml.safe_load(match.group(1)) or {})
    except yaml.YAMLError as exc:
        raise LessonSourceError(f"the frontmatter is not valid YAML: {exc}", 2) from exc
    if not isinstance(meta, dict):
        raise LessonSourceError("the frontmatter must be a list of 'key: value' settings", 2)

    body = text[match.end():]
    body_start_line = text.count("\n", 0, match.end()) + 1

    masked = _strip_fenced(body).splitlines()
    original = body.splitlines()
    starts: list[tuple[int, str]] = []
    for i, line in enumerate(masked):
        heading = _HEADING_RE.match(line)
        if heading:
            starts.append((i, _HEADING_RE.match(original[i]).group("rest")))  # type: ignore[union-attr]

    notes = "\n".join(original[: starts[0][0]]).strip() if starts else "\n".join(original).strip()

    activities: list[ActivitySrc] = []
    for n, (idx, rest) in enumerate(starts):
        end = starts[n + 1][0] if n + 1 < len(starts) else len(original)
        raw = "\n".join(original[idx:end])
        heading_line = body_start_line + idx

        parts = re.split(r"\s+[—–-]\s+", rest, maxsplit=1)
        activity_id = parts[0].strip().strip("`")
        label = parts[1].strip() if len(parts) > 1 else None

        yaml_body, offset = _split_fenced_yaml(raw)
        yaml_line = heading_line + offset
        if yaml_body is None:
            activities.append(
                ActivitySrc(
                    id=activity_id, label=label, scene=None, props={}, say=[],
                    duration_s=None, expect=None, branches=[],
                    heading_line=heading_line, yaml_line=heading_line, raw=raw,
                )
            )
            continue
        try:
            spec = _unbool_keys(yaml.safe_load(yaml_body) or {})
        except yaml.YAMLError as exc:
            raise LessonSourceError(
                f"activity '{activity_id}': the yaml block is not valid YAML: {exc}", yaml_line
            ) from exc
        if not isinstance(spec, dict):
            raise LessonSourceError(
                f"activity '{activity_id}': the yaml block must be 'key: value' settings", yaml_line
            )

        say = _lines(spec.get("say") or spec.get("narration"), yaml_line, raw)

        branches: list[BranchSrc] = []
        on = spec.get("on") or {}
        if isinstance(on, dict):
            for outcome, branch in on.items():
                if isinstance(branch, str):
                    branch = {"goto": branch}
                branch = branch or {}
                branches.append(
                    BranchSrc(
                        on=str(outcome),
                        goto=branch.get("goto"),
                        say=_lines(branch.get("say") or branch.get("narration"), yaml_line, raw),
                        line_no=heading_line + raw.count("\n", 0, max(raw.find(f"{outcome}:"), 0)),
                    )
                )
        elif isinstance(on, list):          # list form, as in lesson_run.json
            for branch in on:
                branches.append(
                    BranchSrc(
                        on=str(branch.get("on", "")),
                        goto=branch.get("goto"),
                        say=_lines(branch.get("say") or branch.get("narration"), yaml_line, raw),
                        line_no=yaml_line,
                    )
                )
        if spec.get("goto"):                # shorthand for on: { always: ... }
            branches.append(
                BranchSrc(on="always", goto=str(spec["goto"]), line_no=activity_line(raw, heading_line, "goto:"))
            )

        expect = spec.get("expect")
        if expect is not None and not isinstance(expect, dict):
            raise LessonSourceError(
                f"activity '{activity_id}': 'expect:' must have a 'kind:' under it", yaml_line
            )

        duration = spec.get("duration_s", spec.get("durationS"))
        activities.append(
            ActivitySrc(
                id=activity_id,
                label=label,
                scene=spec.get("scene") or spec.get("kind"),
                props=spec.get("props") or {},
                say=say,
                duration_s=int(duration) if duration is not None else None,
                expect=expect,
                branches=branches,
                heading_line=heading_line,
                yaml_line=yaml_line,
                raw=raw,
                notes="",
            )
        )

    return LessonSrc(path=path, meta=meta, notes=notes, activities=activities)


def activity_line(raw: str, heading_line: int, needle: str) -> int:
    idx = raw.find(needle)
    return heading_line if idx < 0 else heading_line + raw.count("\n", 0, idx)


# ------------------------------------------------------------- utilities


def walk_assets(value: Any) -> list[str]:
    """Every ``asset://...`` string anywhere inside a props tree, in order."""
    found: list[str] = []
    if isinstance(value, str):
        if value.startswith("asset://"):
            found.append(value)
    elif isinstance(value, dict):
        for item in value.values():
            found.extend(walk_assets(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(walk_assets(item))
    return found


WORDS_PER_SECOND = 2.4          # measured against Piper at the pace a class needs
GAP_S = 0.6                     # breath between narration lines


def speech_seconds(lines: list[Line]) -> float:
    if not lines:
        return 0.0
    words = sum(len(line.text.split()) for line in lines)
    return words / WORDS_PER_SECOND + GAP_S * len(lines)


__all__ = [
    "EMOTIONS", "EMOTION_MOTION_GROUP", "SCENE_KINDS", "OUTCOMES",
    "LessonSourceError", "Line", "BranchSrc", "ActivitySrc", "LessonSrc",
    "parse_lesson", "parse_line", "walk_assets", "speech_seconds",
]
