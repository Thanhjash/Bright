#!/usr/bin/env python3
"""lesson-compile -- lesson.md  ->  lesson_run.json (PROTOCOL.md §4).

    python3 tools/lesson-compile/lesson_compile.py \
        content/lessons/example/format-example.md \
        -o data/runs/7A/2026-08-12-example.json

The compile is **deterministic and offline**: no model call, no network, no
randomness. A frontier model helps a human write the ``.md``; from there to the
playable run is plain mechanics, which is the only reason ``lesson-lint`` can
promise anything about what happens in class.

It refuses to write a run that lint rejects (``--force`` overrides, for looking
at a work in progress), and it validates its own output against the
``bright_contracts`` pydantic models before writing -- so if this exits 0, the
file loads in classroom-core.

What the compiler adds that the source does not spell out:

* ``mediaManifest`` -- collected from every ``asset://`` in every scene, sorted
  and de-duplicated. Authors never maintain this list by hand.
* branch order -- ``correct, near, wrong, silence, timeout, always``, so a run
  diff stays readable when only the wording changes.
* ``act`` payloads -- ``@happy/Happy`` becomes ``{"emotion": "happy",
  "motion": "Happy"}``; a bare ``@happy`` fills in the canonical Live2D motion
  group (``neutral`` -> ``Idle``, PROTOCOL.md §5).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
sys.path.insert(0, str(REPO_ROOT / "tools" / "lesson-lint"))
sys.path.insert(0, str(REPO_ROOT / "packages" / "contracts" / "python"))

from parse import (  # noqa: E402
    EMOTION_MOTION_GROUP,
    OUTCOMES,
    ActivitySrc,
    LessonSourceError,
    LessonSrc,
    Line,
    parse_lesson,
    walk_assets,
)
import lesson_lint  # noqa: E402

BRANCH_ORDER = {name: i for i, name in enumerate(OUTCOMES)}


def _act(line: Line) -> dict[str, Any] | None:
    if not line.emotion:
        return None
    emotion: Any = line.emotion
    if line.intensity is not None:
        emotion = {"name": line.emotion, "intensity": line.intensity}
    act: dict[str, Any] = {"emotion": emotion}
    act["motion"] = line.motion or EMOTION_MOTION_GROUP[line.emotion]
    return act


def _narration(lines: list[Line]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lines:
        entry: dict[str, Any] = {"text": line.text}
        if line.audio:
            entry["audioAsset"] = line.audio
        act = _act(line)
        if act:
            entry["act"] = act
        out.append(entry)
    return out


def _expect(raw: dict[str, Any] | None) -> dict[str, Any] | None:
    if not raw:
        return None
    out: dict[str, Any] = {"kind": raw.get("kind")}
    correct = raw.get("correct")
    if correct is not None:
        out["correct"] = correct
    fuzzy = raw.get("fuzzy") or raw.get("acceptFuzzy")
    if fuzzy:
        out["acceptFuzzy"] = list(fuzzy)
    return out


def compile_activity(activity: ActivitySrc) -> dict[str, Any]:
    out: dict[str, Any] = {
        "id": activity.id,
        "scene": activity.scene,
        "props": activity.props or {},
    }
    if activity.say:
        out["narration"] = _narration(activity.say)
    if activity.duration_s is not None:
        out["durationS"] = int(activity.duration_s)
    expect = _expect(activity.expect)
    if expect:
        out["expect"] = expect
    if activity.branches:
        branches = []
        for branch in sorted(activity.branches, key=lambda b: BRANCH_ORDER.get(b.on, 99)):
            entry: dict[str, Any] = {"on": branch.on, "goto": branch.goto}
            if branch.say:
                entry["narration"] = _narration(branch.say)
            branches.append(entry)
        out["branches"] = branches
    if activity.teaching:
        out["teaching"] = activity.teaching
    return out


def compile_lesson(lesson: LessonSrc, *, class_id: str | None = None) -> dict[str, Any]:
    meta = lesson.meta
    activities = [compile_activity(a) for a in lesson.activities]

    manifest: list[str] = []
    for activity in activities:
        for ref in walk_assets(activity.get("props")):
            if ref not in manifest:
                manifest.append(ref)
    for activity in activities:
        for line in activity.get("narration") or []:
            audio = line.get("audioAsset")
            if audio and audio not in manifest:
                manifest.append(audio)

    return {
        "v": 3,
        "lessonSchemaVersion": int(meta.get("lesson_schema_version") or 1),
        "deliveryMode": str(meta.get("delivery_mode") or "legacy_single"),
        "lessonId": str(meta.get("id") or lesson.path.stem),
        "classId": str(class_id or meta.get("class") or "demo"),
        "title": str(meta.get("title") or lesson.path.stem),
        "focus": [str(x) for x in (meta.get("focus") or [])],
        "review": [str(x) for x in (meta.get("review") or [])],
        "studentsToCheck": [str(x) for x in (meta.get("students_to_check")
                                             or meta.get("studentsToCheck") or [])],
        "activities": activities,
        "mediaManifest": sorted(manifest),
        **({"curriculum": meta["curriculum"]} if meta.get("curriculum") else {}),
        **({"sessionPlan": meta["session_plan"]} if meta.get("session_plan") else {}),
    }


def validate(run: dict[str, Any]) -> list[str]:
    """Validate against the real contracts, exactly as classroom-core will."""
    try:
        from bright_contracts import LessonRun
    except ImportError:  # pragma: no cover
        return ["bright_contracts not importable -- output was NOT schema-checked. "
                f"Expected it at {REPO_ROOT / 'packages' / 'contracts' / 'python'}"]
    try:
        from pydantic import ValidationError
    except ImportError:  # pragma: no cover
        return ["pydantic not installed -- output was NOT schema-checked (pip install pydantic)"]
    try:
        LessonRun.model_validate(run)
    except ValidationError as exc:
        return [
            "  ".join(str(part) for part in (".".join(str(p) for p in err["loc"]), err["msg"]))
            for err in exc.errors()
        ]
    return []


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lesson-compile", description="Compile lesson.md into a playable lesson_run.json"
    )
    parser.add_argument("lesson", help="path to a lesson.md")
    parser.add_argument("-o", "--out", help="output path (default: alongside the lesson)")
    parser.add_argument("--class-id", help="override the class id from the frontmatter")
    parser.add_argument("--assets", action="append", default=[],
                        help="directory that asset:// resolves against (repeatable)")
    parser.add_argument("--force", action="store_true",
                        help="write even if lint found problems (for work in progress)")
    parser.add_argument("--release", action="store_true",
                        help="enforce curriculum approval and autonomous release gates")
    parser.add_argument("--stdout", action="store_true", help="print the run instead of writing it")
    args = parser.parse_args(argv)

    path = Path(args.lesson)
    try:
        lesson = parse_lesson(path)
    except LessonSourceError as exc:
        print(f"{path}:{exc.line}: {exc.message}", file=sys.stderr)
        return 2
    except FileNotFoundError:
        print(f"{path}: no such file", file=sys.stderr)
        return 2

    roots = tuple(Path(p).resolve() for p in args.assets) or lesson_lint.DEFAULT_ASSET_ROOTS
    report = lesson_lint.lint(path, roots, release=args.release)
    if report.errors and not args.force:
        print(lesson_lint.render(report, sys.stdout.isatty(), quiet=False), file=sys.stderr)
        print("\nnot compiled: fix the problems above, or pass --force to write anyway",
              file=sys.stderr)
        return 1

    run = compile_lesson(lesson, class_id=args.class_id)
    errors = validate(run)
    if errors:
        print("the compiled run does not match PROTOCOL.md §4 -- this is a compiler bug, "
              "not your lesson:", file=sys.stderr)
        for error in errors:
            print(f"  · {error}", file=sys.stderr)
        return 3

    text = json.dumps(run, indent=2, ensure_ascii=False) + "\n"
    if args.stdout:
        sys.stdout.write(text)
        return 0

    # default: next to the source, same name -- so the pair is obvious in a folder
    out = Path(args.out) if args.out else path.with_name(f"{path.stem}.run.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(text, encoding="utf-8")
    print(
        f"{out}\n"
        f"  {len(run['activities'])} activities · "
        f"{sum(len(a.get('narration') or []) for a in run['activities'])} narration lines · "
        f"{len(run['mediaManifest'])} media files · "
        f"{len(text.encode('utf-8')) / 1024:.1f} KB\n"
        f"  validated against PROTOCOL.md §4 — loads in classroom-core as CORE_LESSON_RUN"
        + (f"\n  {len(report.warnings)} lint warning(s) — run lesson-lint to see them"
           if report.warnings else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
