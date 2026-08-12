#!/usr/bin/env python3
"""Self-test for the lesson toolchain.  ``python3 tools/lesson-lint/selftest.py``

Two claims are checked, and they are the only two that matter:

1. ``fixtures/broken-lesson.md`` contains one instance of every fault the linter
   knows about, and the linter finds all of them. A rule that stops firing is a
   rule that silently stops protecting a class.
2. The example lesson in ``content/lessons/example/`` lints clean, compiles, validates
   against PROTOCOL.md §4, and plays to the end for a class that never answers.

No pytest, no fixtures directory magic, no network. Exit 0 means the toolchain
is doing its job.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
BROKEN = HERE / "fixtures" / "broken-lesson.md"
LESSON = REPO_ROOT / "content" / "lessons" / "example" / "format-example.md"

# (activity id, a distinctive fragment of the message we expect)
EXPECTED_FAULTS = [
    ("",              "no 'id' in its settings"),
    ("",              "no 'class:'"),
    ("no_id_lesson_note", "not one of the nine emotions"),
    ("broken_choice", "share the id"),
    ("broken_choice", "does not exist"),
    ("broken_choice", "points at an activity that does not exist"),
    ("broken_choice", "is not one of the ids on this board"),
    ("broken_choice", "no 'wrong' branch"),
    ("broken_choice", "no 'silence' branch"),
    ("broken_choice", "no 'timeout' branch"),
    ("broken_choice", "can never be taken"),
    ("broken_choice", "branch says nothing"),
    ("silent_board",  "no narration"),
    ("silent_board",  "looks like a file path"),
    ("never_ends",    "never ends on its own"),
    ("never_ends",    "does not exist"),
    ("bad_scene",     "unknown scene kind"),
    ("orphan",        "nothing can ever reach this activity"),
    ("orphan",        "takes about"),
    ("",              "minutes, but the activities run"),
]


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, *args], capture_output=True, text=True, cwd=REPO_ROOT)


def main() -> int:
    failures: list[str] = []

    # 1 -- every rule still fires
    result = run(str(HERE / "lesson_lint.py"), str(BROKEN), "--json")
    if result.returncode != 1:
        failures.append(f"broken fixture should exit 1, got {result.returncode}\n{result.stderr}")
    report = json.loads(result.stdout)
    problems = report["problems"]
    for activity, fragment in EXPECTED_FAULTS:
        if not any(p["activity"] == activity and fragment in p["what"] for p in problems):
            failures.append(f"rule no longer fires: {activity or '<lesson>'} -- '{fragment}'")
    print(f"  broken fixture: {len(problems)} problems found, "
          f"{len(EXPECTED_FAULTS) - len([f for f in failures if 'no longer fires' in f])}"
          f"/{len(EXPECTED_FAULTS)} expected rules fired")

    # 2 -- the real lesson is clean, compiles, and plays
    result = run(str(HERE / "lesson_lint.py"), str(LESSON), "--strict", "--no-color")
    if result.returncode != 0:
        failures.append("the example lesson does not lint clean:\n" + result.stdout)
    print("  example lesson lints clean (--strict)")

    out = REPO_ROOT / "content" / "lessons" / "example" / "format-example.run.json"
    result = run(str(REPO_ROOT / "tools" / "lesson-compile" / "lesson_compile.py"),
                 str(LESSON), "-o", str(out))
    if result.returncode != 0:
        failures.append("the example lesson does not compile:\n" + result.stdout + result.stderr)
    print("  compiles and validates against PROTOCOL.md §4")

    result = run(str(REPO_ROOT / "tools" / "lesson-play" / "lesson_play.py"), str(out), "--json")
    played = json.loads(result.stdout) if result.stdout.strip() else {}
    for mode, stats in (played.get("modes") or {}).items():
        if stats["stalls"] or stats["unhandled"]:
            failures.append(f"playthrough '{mode}' stalls: {stats['stalls']}{stats['unhandled']}")
    print(f"  plays to the end in all {len(played.get('modes') or {})} class behaviours, no stalls")

    print()
    if failures:
        for failure in failures:
            print(f"✗ {failure}")
        return 1
    print("✓ toolchain self-test passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
