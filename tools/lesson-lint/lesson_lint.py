#!/usr/bin/env python3
"""lesson-lint -- can this lesson produce a complete, playable run?

    python3 tools/lesson-lint/lesson_lint.py content/lessons/example/format-example.md

That is the only question this tool answers. Not "is the YAML valid" -- valid
YAML that stalls in front of thirty children is the failure we are guarding
against. Every rule here corresponds to something that would go visibly wrong in
a real class with the LLM switched off (NS-1).

Output is written for a teacher, not a programmer: what is wrong, which line,
what the class would experience, and the exact text to add. Exit code 0 means
the lesson can be taught; 1 means it cannot; 2 means the file could not be read.

Options
    --assets DIR   where asset:// resolves (default: content/media, then
                   services/classroom-core/assets)
    --json         machine-readable output for CI
    --strict       treat warnings as failures
    --quiet        only the summary line
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parse import (  # noqa: E402
    EMOTION_MOTION_GROUP,
    OUTCOMES,
    SCENE_KINDS,
    ActivitySrc,
    LessonSourceError,
    LessonSrc,
    parse_lesson,
    speech_seconds,
    walk_assets,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ASSET_ROOTS = (
    REPO_ROOT / "content" / "media",
    REPO_ROOT / "services" / "classroom-core" / "assets",
)

GRADED_OUTCOMES = ("correct", "near", "wrong", "silence", "timeout")
AUTONOMOUS_OUTCOMES = (*GRADED_OUTCOMES, "uncertain", "unhandled")

# Required prop keys per scene kind (PROTOCOL.md §2). A scene missing these
# renders as an empty or broken board in front of the class.
REQUIRED_PROPS: dict[str, tuple[str, ...]] = {
    "idle": (),
    "text": ("text",),
    "image": ("asset",),
    "video": ("asset",),
    "vocabulary": ("items", "interaction"),
    "choice": ("prompt", "options"),
    "matching": ("left", "right"),
    "sentence_builder": ("tokens",),
    "pronunciation": ("word", "phonemes"),
    "roleplay": ("environment", "aiRole", "studentRole"),
    "explore": ("topic", "nodes"),
}

# Which interaction each scene can actually receive.
SCENE_EXPECT_KINDS: dict[str, tuple[str, ...]] = {
    "choice": ("choice", "speech"),
    "vocabulary": ("point", "speech"),
    "matching": ("drag", "speech"),
    "sentence_builder": ("drag", "speech"),
    "pronunciation": ("speech",),
    "roleplay": ("speech",),
    "explore": ("speech", "point"),
    "image": ("speech", "point"),
    "text": ("speech",),
    "video": ("speech",),
    "idle": (),
}


@dataclass
class Problem:
    level: str                    # "error" | "warning"
    line: int
    where: str                    # activity id, or "" for lesson-wide
    what: str
    why: str = ""
    fix: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "level": self.level, "line": self.line, "activity": self.where,
            "what": self.what, "why": self.why, "fix": self.fix,
        }


@dataclass
class Report:
    path: Path
    problems: list[Problem] = field(default_factory=list)
    stats: dict[str, Any] = field(default_factory=dict)

    def error(self, line: int, where: str, what: str, why: str = "", fix: str = "") -> None:
        self.problems.append(Problem("error", line, where, what, why, fix))

    def warn(self, line: int, where: str, what: str, why: str = "", fix: str = "") -> None:
        self.problems.append(Problem("warning", line, where, what, why, fix))

    @property
    def errors(self) -> list[Problem]:
        return [p for p in self.problems if p.level == "error"]

    @property
    def warnings(self) -> list[Problem]:
        return [p for p in self.problems if p.level == "warning"]


# ------------------------------------------------------------------ rules


def _ids_in_props(activity: ActivitySrc) -> set[str]:
    """Every id a student interaction could produce for this scene."""
    props = activity.props or {}
    out: set[str] = set()
    for key in ("items", "options", "left", "right", "tokens", "nodes"):
        for entry in props.get(key) or []:
            if isinstance(entry, dict) and entry.get("id"):
                out.add(str(entry["id"]))
    return out


def _duplicate_ids(entries: Iterable[Any]) -> list[str]:
    seen: set[str] = set()
    dupes: list[str] = []
    for entry in entries:
        if isinstance(entry, dict) and entry.get("id"):
            key = str(entry["id"])
            if key in seen:
                dupes.append(key)
            seen.add(key)
    return dupes


def check_meta(lesson: LessonSrc, report: Report, *, release: bool = False) -> None:
    for key, why in (
        ("id", "classroom-core uses it as lessonId, and the student records key off it"),
        ("title", "the teacher sees this in the console and the lesson list"),
    ):
        if not lesson.meta.get(key):
            report.error(
                2, "", f"the lesson has no '{key}' in its settings",
                why, f"add   {key}: <value>   between the two '---' lines at the top",
            )
    if not lesson.meta.get("class"):
        report.warn(
            2, "", "no 'class:' in the lesson settings",
            "the compiled run needs a class id; 'demo' will be used",
            "add   class: 7A   to the frontmatter",
        )
    if not lesson.activities:
        report.error(
            2, "", "the lesson has no activities",
            "there is nothing to teach",
            "add a section starting with '## some_activity_id' and a yaml block under it",
        )
    delivery = lesson.meta.get("delivery_mode", "legacy_single")
    if delivery not in ("legacy_single", "autonomous_class"):
        report.error(2, "", f"unknown delivery_mode '{delivery}'",
                     "competition packaging must know which runtime invariants apply",
                     "use delivery_mode: legacy_single or autonomous_class")
    if delivery == "autonomous_class":
        for key in ("curriculum", "session_plan"):
            if not isinstance(lesson.meta.get(key), dict):
                report.error(2, "", f"autonomous lesson has no '{key}' block",
                             "Core cannot enforce pedagogy, pacing and closure without compiled data",
                             f"add a {key}: mapping to the frontmatter")
        duration = lesson.meta.get("duration_min")
        if not isinstance(duration, (int, float)) or not 35 <= float(duration) <= 45:
            report.error(2, "", "autonomous lesson duration is outside 35–45 minutes",
                         "the product unit of truth is one complete classroom period",
                         "set duration_min between 35 and 45")
        curriculum = lesson.meta.get("curriculum") or {}
        if release and curriculum.get("approvalStatus") != "approved":
            report.error(2, "", "curriculum approval is not 'approved'",
                         "a playable lesson is not automatically safe or pedagogically valid",
                         "name the curriculum approver, complete review, then set approvalStatus: approved")


def check_activity(activity: ActivitySrc, lesson: LessonSrc, report: Report,
                   asset_roots: tuple[Path, ...]) -> None:
    where = activity.id

    if lesson.meta.get("delivery_mode") == "autonomous_class":
        required = {
            "stage", "stageBudgetS", "responseScope", "participationMode",
            "skillIds", "evidencePolicy", "recovery",
        }
        teaching = activity.teaching or {}
        missing = sorted(required - set(teaching))
        if missing:
            report.error(activity.yaml_line, where,
                         "autonomous activity is missing teaching fields: " + ", ".join(missing),
                         "the class controller cannot infer pedagogy from a board type",
                         "add a complete teaching: block")
        recovery = teaching.get("recovery") if isinstance(teaching, dict) else None
        if not isinstance(recovery, dict) or not {
            "easierActivityId", "safeDefaultActivityId"
        }.issubset(recovery):
            report.error(activity.yaml_line, where,
                         "autonomous activity has no complete recovery ladder",
                         "agent/audio/noise failure needs a deterministic next move",
                         "set recovery.easierActivityId and recovery.safeDefaultActivityId")

    if activity.scene is None:
        report.error(
            activity.heading_line, where, "this activity has no 'scene:' (or no yaml block at all)",
            "classroom-core would not know what to put on the board, and the lesson stops here",
            "add a ```yaml block with at least   scene: text   and   props:",
        )
        return
    if activity.scene not in SCENE_KINDS:
        report.error(
            activity.locate("scene:"), where, f"unknown scene kind '{activity.scene}'",
            "the board shows a red error card instead of the activity",
            "use one of: " + ", ".join(SCENE_KINDS),
        )
        return

    # --- narration -------------------------------------------------------
    if not activity.say:
        report.error(
            activity.yaml_line, where, "no narration -- the avatar says nothing here",
            "the board changes in silence and the class does not know what to do",
            'add   say:\n        - "..."   to this activity',
        )
    for line in activity.say:
        if not line.text.strip():
            report.error(line.line_no, where, "an empty narration line",
                         "the avatar would pause for no reason", "remove it, or write the words")
        if line.raw_emotion and line.emotion is None:
            report.error(
                line.line_no, where, f"'@{line.raw_emotion}' is not one of the nine emotions",
                "the avatar would not react, and the cue is spoken as text in some players",
                "use one of: " + " ".join(EMOTION_MOTION_GROUP),
            )
        if line.motion and line.emotion:
            expected = EMOTION_MOTION_GROUP[line.emotion]
            if line.motion != expected:
                report.warn(
                    line.line_no, where,
                    f"'@{line.emotion}/{line.motion}' -- the usual motion for {line.emotion} is {expected}",
                    "an unknown motion group is ignored by the avatar; the emotion still works",
                    f"write   @{line.emotion}/{expected}   unless this model really has '{line.motion}'",
                )
        if line.intensity is not None and not 0.0 <= line.intensity <= 1.0:
            report.error(line.line_no, where, f"intensity {line.intensity} is outside 0..1",
                         "the avatar rejects it", "use a number between 0 and 1, e.g. @curious:0.6")

    # --- props -----------------------------------------------------------
    props = activity.props or {}
    if not isinstance(props, dict):
        report.error(activity.yaml_line, where, "'props:' must be a set of 'key: value' settings",
                     "", "check the indentation under props:")
        return
    for key in REQUIRED_PROPS.get(activity.scene, ()):
        if props.get(key) in (None, "", [], {}):
            report.error(
                activity.locate("props:"), where,
                f"a '{activity.scene}' scene needs '{key}:' in its props, and it is missing or empty",
                f"the board would render without its {key}",
                f"add   {key}:   under props:",
            )
    for key in ("items", "options", "left", "right", "tokens", "nodes"):
        entries = props.get(key)
        if isinstance(entries, list):
            for i, entry in enumerate(entries):
                if not isinstance(entry, dict) or not entry.get("id"):
                    report.error(
                        activity.locate(f"{key}:"), where,
                        f"{key}[{i}] has no 'id:'",
                        "core grades answers by id; without one this item can never be chosen",
                        "write   { id: apple, text: apple, asset: \"asset://...\" }",
                    )
            for dupe in _duplicate_ids(entries):
                report.error(
                    activity.locate(f"{key}:"), where, f"two entries in {key} share the id '{dupe}'",
                    "grading picks the first one, so the other can never be correct",
                    "give each item its own id",
                )
    if activity.scene == "vocabulary":
        interaction = props.get("interaction")
        if interaction not in ("none", "point", "tap", None):
            report.error(activity.locate("interaction:"), where,
                         f"interaction '{interaction}' is not valid for a vocabulary scene",
                         "", "use   interaction: none   or   interaction: point")
        if interaction in ("point", "tap") and activity.expect is None:
            report.warn(
                activity.locate("interaction:"), where,
                "children can tap this board, but nothing grades the tap",
                "a child taps, nothing happens, and they stop trying",
                "add an   expect:   block, or set   interaction: none",
            )
        highlight = props.get("highlightId")
        if highlight and highlight not in _ids_in_props(activity):
            report.error(activity.locate("highlightId:"), where,
                         f"highlightId '{highlight}' is not one of the items on this board",
                         "nothing is highlighted", "use one of: " + ", ".join(sorted(_ids_in_props(activity))))

    # --- assets ----------------------------------------------------------
    for ref in walk_assets(props):
        rel = ref[len("asset://"):]
        if not rel:
            report.error(activity.locate(ref), where, "an empty asset:// reference", "", "")
            continue
        if not any((root / rel).is_file() for root in asset_roots):
            tried = "\n        ".join(str(root / rel) for root in asset_roots)
            report.error(
                activity.locate(ref), where, f"the picture {ref} does not exist",
                "the board shows a broken image in front of the class",
                f"put the file at one of:\n        {tried}",
            )
    for key, value in props.items():
        if isinstance(value, str) and value.endswith((".svg", ".png", ".webp", ".jpg", ".mp4")) \
                and not value.startswith("asset://"):
            report.error(
                activity.locate(key + ":"), where,
                f"'{key}: {value}' looks like a file path, not an asset reference",
                "the board never sees the filesystem; it can only load asset:// ids",
                f'write   {key}: "asset://{Path(value).name}"',
            )

    # Pre-rendered narration audio. PROTOCOL.md §4: if audioAsset is present the
    # player does NOT fall back to live TTS, so a missing file is silence in class.
    for line in list(activity.say) + [ln for b in activity.branches for ln in b.say]:
        if not line.audio:
            continue
        if not line.audio.startswith("asset://"):
            report.error(line.line_no, where,
                         f"narration audio '{line.audio}' is not an asset:// reference",
                         "the board can only load asset:// ids, never file paths",
                         f'write   audio: "asset://narration/{Path(line.audio).name}"')
            continue
        rel = line.audio[len("asset://"):]
        if not any((root / rel).is_file() for root in asset_roots):
            report.error(
                line.line_no, where, f"the recorded line {line.audio} does not exist",
                "a line with recorded audio is never spoken by the computer voice, so this "
                "line would be silent in class",
                "record the file, or delete the 'audio:' line to use the computer voice",
            )

    # --- expect / branches ----------------------------------------------
    expect = activity.expect
    branch_by_outcome = {b.on: b for b in activity.branches}
    for branch in activity.branches:
        if branch.on not in OUTCOMES:
            report.error(branch.line_no, where, f"'{branch.on}:' is not a real outcome",
                         "this branch can never be taken",
                         "use one of: " + ", ".join(OUTCOMES))
        if not branch.goto:
            report.error(branch.line_no, where, f"the '{branch.on}' branch has no 'goto:'",
                         "core would fall through to the next activity instead of recovering",
                         "add   goto: <activity id>")
        elif branch.goto not in lesson.by_id:
            close = _suggest(branch.goto, lesson.by_id)
            report.error(
                branch.line_no, where, f"'{branch.on}: goto {branch.goto}' points at an activity that does not exist",
                "the lesson would silently skip to the next activity instead of the recovery you wrote",
                (f"did you mean '{close}'?" if close else "check the '## <id>' headings for the right id"),
            )
        if not branch.say and branch.on in ("wrong", "near", "silence", "timeout"):
            report.warn(
                branch.line_no, where, f"the '{branch.on}' branch says nothing",
                "the board jumps somewhere else with no explanation; children read that as punishment",
                'add   say: ["..."]   to this branch',
            )

    if expect is not None:
        kind = expect.get("kind")
        if kind not in ("choice", "point", "drag", "speech", "none"):
            report.error(activity.locate("kind:"), where, f"expect kind '{kind}' is not valid",
                         "", "use one of: choice, point, drag, speech, none")
        elif kind != "none":
            allowed = SCENE_EXPECT_KINDS.get(activity.scene, ())
            if allowed and kind not in allowed:
                report.warn(
                    activity.locate("kind:"), where,
                    f"a '{activity.scene}' board cannot produce a '{kind}' answer",
                    "nothing a child does on this board is graded, so the activity always times out",
                    "expected one of: " + ", ".join(allowed),
                )
            correct = expect.get("correct")
            correct_list = [correct] if isinstance(correct, str) else list(correct or [])
            fuzzy = list(expect.get("fuzzy") or expect.get("acceptFuzzy") or [])
            if not correct_list:
                report.error(activity.locate("expect:"), where, "expect has no 'correct:' answer",
                             "every answer would be graded wrong",
                             "add   correct: <id>   (or a list of accepted sentences for speech)")
            if kind in ("choice", "point", "drag"):
                known = _ids_in_props(activity)
                for value in correct_list + fuzzy:
                    if known and str(value) not in known and ">" not in str(value):
                        report.error(
                            activity.locate(str(value)), where,
                            f"'{value}' is not one of the ids on this board",
                            "the correct answer can never be given, so the class always fails this question",
                            "use one of: " + ", ".join(sorted(known)),
                        )
            # the branch-coverage rule from PROTOCOL.md §4
            has_always = "always" in branch_by_outcome
            for outcome, consequence in (
                ("wrong", "a child answers wrongly and the lesson moves on with no help"),
                ("silence", "nobody answers and the lesson moves on as if they had"),
            ):
                if outcome not in branch_by_outcome and not has_always:
                    report.error(
                        activity.locate("on:") if activity.branches else activity.yaml_line, where,
                        f"no '{outcome}' branch",
                        consequence + " -- this is the single most common way an authored lesson fails a class",
                        f'add   {outcome}: {{ goto: <recovery activity>, say: ["..."] }}   under  on:',
                    )
            if lesson.meta.get("delivery_mode") == "autonomous_class" and not has_always:
                for outcome in ("uncertain", "unhandled"):
                    if outcome not in branch_by_outcome:
                        report.error(
                            activity.locate("on:") if activity.branches else activity.yaml_line,
                            where, f"no '{outcome}' branch",
                            "autonomous speech/noise/off-script recovery must be authored, not improvised",
                            f'add   {outcome}: {{ goto: <safe activity>, say: ["..."] }}   under  on:',
                        )
            # what can *actually* fire, given the timing (PROTOCOL §9.4)
            live = "timeout" if activity.duration_s else "silence"
            if live not in branch_by_outcome and not has_always:
                report.warn(
                    activity.yaml_line, where,
                    f"with duration_s {'set' if activity.duration_s else 'unset'}, "
                    f"no-answer is reported as '{live}', and there is no '{live}' branch",
                    "the recovery you wrote for the other one will not run",
                    f"add a '{live}' branch (usually the same goto as the other)",
                )
            if "near" in branch_by_outcome and not fuzzy:
                report.warn(
                    branch_by_outcome["near"].line_no, where,
                    "there is a 'near' branch but no 'fuzzy:' answers, so it can never be taken",
                    "the near-miss recovery you wrote is dead",
                    'add   fuzzy: ["..."]   under expect:',
                )
            if fuzzy and "near" not in branch_by_outcome and not has_always:
                report.warn(
                    activity.locate("fuzzy:"), where,
                    "'fuzzy:' answers are listed but there is no 'near' branch",
                    "a near-miss is treated exactly like a wrong answer, which is the opposite of the intent",
                    'add   near: { goto: <recast activity>, say: ["..."] }   under  on:',
                )
    else:
        for outcome in GRADED_OUTCOMES:
            if outcome in branch_by_outcome:
                report.warn(
                    branch_by_outcome[outcome].line_no, where,
                    f"a '{outcome}' branch, but this activity grades nothing",
                    "the branch can never be taken",
                    "add an   expect:   block, or use   goto: <id>   for a plain next step",
                )

    # --- can this activity ever end? -------------------------------------
    graded = expect is not None and expect.get("kind") not in (None, "none")
    if not activity.duration_s and not graded and "always" not in branch_by_outcome:
        report.error(
            activity.yaml_line, where, "this activity never ends on its own",
            "no duration_s, nothing to answer, no next step: the board freezes until the "
            "teacher presses Skip",
            "add   duration_s: <seconds>   (or an expect: block, or goto: <id>)",
        )

    # --- pacing ----------------------------------------------------------
    needed = speech_seconds(activity.say)
    if activity.duration_s and needed > activity.duration_s + 0.5:
        report.warn(
            activity.locate("duration_s:"), where,
            f"duration_s is {activity.duration_s}s but the narration takes about {needed:.0f}s to say",
            "the board moves on while the avatar is still talking",
            f"raise it to at least {int(needed) + 2}s, or cut a line",
        )


def check_flow(lesson: LessonSrc, report: Report) -> dict[str, Any]:
    """Reachability, dead ends, and how long the lesson actually runs."""
    activities = lesson.activities
    index = {a.id: i for i, a in enumerate(activities)}

    seen: dict[str, ActivitySrc] = {}
    for activity in activities:
        if activity.id in seen:
            report.error(
                activity.heading_line, activity.id, f"two activities are both called '{activity.id}'",
                "every 'goto' to this id lands on the first one, so the second is unreachable",
                "rename one of them",
            )
        seen[activity.id] = activity

    def successors(i: int) -> list[int]:
        activity = activities[i]
        out: list[int] = []
        by_outcome = {b.on: b for b in activity.branches}
        for branch in activity.branches:
            if branch.goto in index:
                out.append(index[branch.goto])
        covered = "always" in by_outcome
        if activity.expect is not None and activity.expect.get("kind") not in (None, "none"):
            required_outcomes = (AUTONOMOUS_OUTCOMES
                                 if lesson.meta.get("delivery_mode") == "autonomous_class"
                                 else GRADED_OUTCOMES)
            covered = covered or all(o in by_outcome for o in required_outcomes)
        if not covered and i + 1 < len(activities):
            out.append(i + 1)                       # core's fall-through
        return out

    reachable = {0} if activities else set()
    stack = [0] if activities else []
    while stack:
        for j in successors(stack.pop()):
            if j not in reachable:
                reachable.add(j)
                stack.append(j)
    for i, activity in enumerate(activities):
        if i not in reachable:
            report.error(
                activity.heading_line, activity.id, "nothing can ever reach this activity",
                "you wrote it, and the class will never see it",
                "point some branch at it with   goto: " + activity.id +
                "   , or delete it if it is left over",
            )

    for activity in activities:
        for branch in activity.branches:
            if branch.goto == activity.id and branch.on in ("wrong", "silence", "timeout"):
                report.warn(
                    branch.line_no, activity.id,
                    f"the '{branch.on}' branch points back at the same activity",
                    "a child who cannot answer is asked the same question forever",
                    "point it at a recovery activity that lowers the difficulty instead",
                )

    def walk(prefer: tuple[str, ...]) -> float:
        i, total, guard = 0, 0.0, 0
        visited: set[int] = set()
        while 0 <= i < len(activities) and guard < 500:
            guard += 1
            activity = activities[i]
            total += float(activity.duration_s or speech_seconds(activity.say))
            visited.add(i)
            by_outcome = {b.on: b for b in activity.branches}
            nxt = None
            for outcome in prefer:
                branch = by_outcome.get(outcome)
                if branch and branch.goto in index:
                    nxt = index[branch.goto]
                    break
            if nxt is None:
                nxt = i + 1
            if nxt in visited:                      # do not double-count a loop
                nxt = i + 1
            i = nxt
        return total

    happy = walk(("correct", "always"))
    hard = walk(("wrong", "always"))
    return {
        "activities": len(activities),
        "graded": sum(1 for a in activities
                      if a.expect is not None and a.expect.get("kind") not in (None, "none")),
        "recovery": sum(1 for a in activities
                        if any(b.on == "always" for b in a.branches)),
        "narration_lines": sum(len(a.say) + sum(len(b.say) for b in a.branches)
                               for a in activities),
        "happy_path_s": round(happy),
        "recovery_path_s": round(hard),
    }


def _suggest(value: str, known: dict[str, Any]) -> str | None:
    import difflib

    matches = difflib.get_close_matches(value, list(known), n=1, cutoff=0.6)
    return matches[0] if matches else None


def lint(path: Path, asset_roots: tuple[Path, ...], *, release: bool = False) -> Report:
    report = Report(path=path)
    lesson = parse_lesson(path)
    check_meta(lesson, report, release=release)
    for activity in lesson.activities:
        check_activity(activity, lesson, report, asset_roots)
    report.stats = check_flow(lesson, report)

    refs = sorted({ref for a in lesson.activities for ref in walk_assets(a.props)})
    report.stats["media"] = len(refs)
    declared = lesson.meta.get("duration_min")
    if declared:
        happy = report.stats["happy_path_s"] / 60.0
        if happy > float(declared) * 1.25 or happy < float(declared) * 0.45:
            report.warn(
                2, "",
                f"the lesson says {declared} minutes, but the activities run about "
                f"{happy:.0f} minutes on the straight-through path",
                "lessons that overrun get cut off by the bell, and the wrap-up is what makes it stick",
                "adjust duration_s values, or change duration_min in the settings",
            )
    return report


# ----------------------------------------------------------------- output

BOLD, DIM, RED, YELLOW, GREEN, RESET = (
    "\033[1m", "\033[2m", "\033[31m", "\033[33m", "\033[32m", "\033[0m"
)


def _paint(enabled: bool) -> dict[str, str]:
    if enabled:
        return {"bold": BOLD, "dim": DIM, "red": RED, "yellow": YELLOW,
                "green": GREEN, "reset": RESET}
    return dict.fromkeys(("bold", "dim", "red", "yellow", "green", "reset"), "")


def render(report: Report, colour: bool, quiet: bool) -> str:
    c = _paint(colour)
    out: list[str] = []
    stats = report.stats
    out.append(f"{c['bold']}{report.path}{c['reset']}")
    out.append(
        f"  {stats.get('activities', 0)} activities "
        f"({stats.get('graded', 0)} ask the class something, "
        f"{stats.get('recovery', 0)} are recovery steps) · "
        f"{stats.get('narration_lines', 0)} spoken lines · "
        f"{stats.get('media', 0)} pictures"
    )
    out.append(
        f"  runs {stats.get('happy_path_s', 0) / 60:.0f} min straight through, "
        f"about {stats.get('recovery_path_s', 0) / 60:.0f} min if the class needs every recovery step"
    )
    out.append("")

    if not quiet:
        for problem in sorted(report.problems, key=lambda p: (p.level != "error", p.line)):
            mark = f"{c['red']}✗{c['reset']}" if problem.level == "error" else f"{c['yellow']}!{c['reset']}"
            where = f" · {c['bold']}{problem.where}{c['reset']}" if problem.where else ""
            out.append(f"  {mark} line {problem.line}{where}")
            out.append(f"      {problem.what}")
            if problem.why:
                out.append(f"      {c['dim']}in class:{c['reset']} {problem.why}")
            if problem.fix:
                fix = problem.fix.replace("\n", "\n      ")
                out.append(f"      {c['dim']}fix:{c['reset']} {fix}")
            out.append("")

    errors, warnings = len(report.errors), len(report.warnings)
    if errors:
        out.append(f"{c['red']}{c['bold']}✗ {errors} problem(s) must be fixed before this lesson "
                   f"can be taught{c['reset']}" + (f", {warnings} to check" if warnings else ""))
    elif warnings:
        out.append(f"{c['yellow']}{c['bold']}✓ playable{c['reset']} — "
                   f"{warnings} thing(s) worth checking")
    else:
        out.append(f"{c['green']}{c['bold']}✓ this lesson can be taught end to end, "
                   f"with or without the AI{c['reset']}")
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lesson-lint", description="Can this lesson produce a complete, playable run?"
    )
    parser.add_argument("lesson", nargs="+", help="path to a lesson.md")
    parser.add_argument("--assets", action="append", default=[],
                        help="directory that asset:// resolves against (repeatable)")
    parser.add_argument("--json", action="store_true", help="machine-readable output")
    parser.add_argument("--strict", action="store_true", help="warnings fail too")
    parser.add_argument("--release", action="store_true",
                        help="enforce curriculum approval and competition packaging gates")
    parser.add_argument("--quiet", action="store_true", help="summary only")
    parser.add_argument("--no-color", action="store_true")
    args = parser.parse_args(argv)

    roots = tuple(Path(p).resolve() for p in args.assets) or DEFAULT_ASSET_ROOTS
    colour = sys.stdout.isatty() and not args.no_color

    worst = 0
    payloads = []
    for raw in args.lesson:
        path = Path(raw)
        try:
            report = lint(path, roots, release=args.release)
        except LessonSourceError as exc:
            if args.json:
                payloads.append({"lesson": str(path), "ok": False,
                                 "problems": [{"level": "error", "line": exc.line,
                                               "activity": "", "what": exc.message,
                                               "why": "the file could not be read at all",
                                               "fix": ""}]})
            else:
                print(f"{path}\n  ✗ line {exc.line}: {exc.message}")
            worst = max(worst, 2)
            continue
        except FileNotFoundError:
            print(f"{path}: no such file", file=sys.stderr)
            worst = max(worst, 2)
            continue

        failed = bool(report.errors) or (args.strict and bool(report.warnings))
        worst = max(worst, 1 if failed else 0)
        if args.json:
            payloads.append({
                "lesson": str(path), "ok": not failed, "stats": report.stats,
                "problems": [p.as_dict() for p in report.problems],
            })
        else:
            print(render(report, colour, args.quiet))
    if args.json:
        print(json.dumps(payloads if len(payloads) != 1 else payloads[0], indent=2, ensure_ascii=False))
    return worst


if __name__ == "__main__":
    raise SystemExit(main())
