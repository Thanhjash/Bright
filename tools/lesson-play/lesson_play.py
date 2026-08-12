#!/usr/bin/env python3
"""lesson-play -- play a compiled lesson_run.json to a log, with no LLM and no UI.

    python3 tools/lesson-play/lesson_play.py content/lessons/example/format-example.run.json

This is SP-0 step 4: *"play it through a stub runner; count every place it would
stall in a real class"*. It imports the **real** lesson runner from
``services/classroom-core`` (read-only) with a stub bus and no database, so what
you see here is what the class gets.

It plays the lesson five times over -- a class that answers everything correctly,
one that answers wrongly, one that near-misses, one that says nothing at all, and
one that does a bit of each -- and reports:

* every place the lesson would **stall** (nothing on screen advances it)
* every graded question where an outcome had **no authored recovery**
* **branch coverage**: which authored recoveries were never reached by any class

Timers are not slept through: ``durationS`` is accumulated as elapsed time, so a
20-minute lesson plays in under a second.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
CORE = REPO_ROOT / "services" / "classroom-core"
sys.path.insert(0, str(CORE))
sys.path.insert(0, str(REPO_ROOT / "packages" / "contracts" / "python"))

import config  # noqa: E402,F401  -- installs the bright_contracts import path
import runner as core_runner  # noqa: E402
from bright_contracts import LessonRun  # noqa: E402
from state import StateStore  # noqa: E402


class _NoSleep:
    """Stand-in for the ``asyncio`` module inside ``runner``: every ``sleep``
    is cancelled instead of waited on, so auto-advance timers never fire and the
    harness stays in control of the clock. Everything else is the real module."""

    def __getattr__(self, name: str) -> Any:
        return getattr(asyncio, name)

    async def sleep(self, delay: float, *args: Any, **kwargs: Any) -> None:
        raise asyncio.CancelledError


class StubBus:
    def __init__(self) -> None:
        self.events: list[tuple[str, Any]] = []

    def publish(self, event_type: str, payload: Any) -> None:
        self.events.append((event_type, payload))

    def drain(self) -> list[tuple[str, Any]]:
        out, self.events = self.events, []
        return out


@dataclass
class Playthrough:
    mode: str
    steps: list[str] = field(default_factory=list)
    transcript: list[str] = field(default_factory=list)
    seconds: float = 0.0
    stalls: list[str] = field(default_factory=list)
    unhandled: list[str] = field(default_factory=list)
    taken: set[str] = field(default_factory=set)


def _wrong_id(activity: Any, correct: list[str], fuzzy: list[str]) -> str | None:
    props = activity.props or {}
    for key in ("options", "items", "left", "tokens", "nodes"):
        for entry in props.get(key) or []:
            if isinstance(entry, dict):
                ident = str(entry.get("id", ""))
                if ident and ident not in correct and ident not in fuzzy:
                    return ident
    return None


def _payload(activity: Any, want: str) -> tuple[str, dict[str, Any]] | None:
    """Build the client event a child would send to produce ``want``."""
    expect = activity.expect
    if expect is None or expect.kind == "none":
        return None
    correct = expect.correct if isinstance(expect.correct, list) else (
        [expect.correct] if expect.correct else [])
    fuzzy = list(expect.accept_fuzzy or [])

    if want == "correct":
        value = correct[0] if correct else None
    elif want == "near":
        value = fuzzy[0] if fuzzy else None
    else:
        value = ("banana pencil elephant" if expect.kind == "speech"
                 else _wrong_id(activity, [str(c) for c in correct], [str(f) for f in fuzzy]))
    if value is None:
        return None

    key = {"choice": "optionId", "point": "targetId", "drag": "toId", "speech": "text"}[expect.kind]
    return expect.kind, {key: str(value), "studentId": "s04"}


async def play(lesson: LessonRun, mode: str, *, max_steps: int = 400) -> Playthrough:
    result = Playthrough(mode=mode)
    bus = StubBus()
    store = StateStore()
    run = core_runner.LessonRunner(bus, store, lesson, db=None, reveal_hold_s=0.0)

    core_runner.asyncio = _NoSleep()          # type: ignore[assignment]
    try:
        await run.start(0)
        seen_pairs: set[tuple[str, str]] = set()
        graded_seen = 0
        for _ in range(max_steps):
            activity = run.current
            if activity is None or run.finished:
                break
            result.steps.append(activity.id)
            result.seconds += float(activity.duration_s or 0)
            for event_type, payload in bus.drain():
                if event_type == "speech.say":
                    result.transcript.append(f"{activity.id}: {payload['text']}")

            graded = activity.expect is not None and activity.expect.kind != "none"
            by_outcome = {b.on: b for b in (activity.branches or [])}
            if mode == "mixed" and graded:
                want = ("correct", "wrong", "near", "silence")[graded_seen % 4]
                graded_seen += 1
            else:
                want = mode

            if not graded:
                if not activity.duration_s and "always" not in by_outcome:
                    result.stalls.append(
                        f"{activity.id}: nothing ends this activity (no durationS, "
                        f"nothing to answer, no 'always' branch)"
                    )
                if "always" in by_outcome:
                    result.taken.add(f"{activity.id}:always")
                before = run.index
                await run._advance_default()
                await run.drain()
                if run.index == before and not run.finished:
                    result.stalls.append(f"{activity.id}: did not advance")
                    break
                continue

            # A graded activity. `silence` mode answers nothing; PROTOCOL §9.4
            # says which outcome that produces.
            if want == "silence":
                outcome = "timeout" if activity.duration_s else "silence"
                if outcome not in by_outcome and "always" not in by_outcome:
                    result.unhandled.append(
                        f"{activity.id}: nobody answers -> '{outcome}', and there is no "
                        f"'{outcome}' branch; the lesson skips ahead with no help"
                    )
                result.taken.add(f"{activity.id}:{outcome}")
                await run._apply_outcome(outcome)
                await run.drain()
                continue

            built = _payload(activity, want)
            if built is None:                  # e.g. 'near' with no acceptFuzzy
                result.taken.add(f"{activity.id}:correct")
                await run._apply_outcome("correct")
                await run.drain()
                continue
            kind, payload = built
            outcome = await run.handle_interaction(kind, payload)
            await run.drain()
            if outcome is None:
                result.stalls.append(
                    f"{activity.id}: a '{kind}' answer was not graded at all "
                    f"(expect.kind is '{activity.expect.kind}')"
                )
                break
            result.taken.add(f"{activity.id}:{outcome}")
            if outcome not in by_outcome and "always" not in by_outcome:
                result.unhandled.append(
                    f"{activity.id}: answer graded '{outcome}', no '{outcome}' branch"
                )
            pair = (activity.id, outcome)
            if pair in seen_pairs:             # same question, same answer, twice
                break
            seen_pairs.add(pair)
        for event_type, payload in bus.drain():
            if event_type == "speech.say":
                result.transcript.append(f"(end): {payload['text']}")
    finally:
        core_runner.asyncio = asyncio          # type: ignore[assignment]
        await run.stop()
    return result


def all_branches(lesson: LessonRun) -> list[str]:
    return [f"{a.id}:{b.on}" for a in lesson.activities for b in (a.branches or [])]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="lesson-play", description="Play a lesson_run.json with no LLM and report stalls")
    parser.add_argument("run", help="path to a compiled lesson_run.json")
    parser.add_argument("--transcript", action="store_true",
                        help="print everything the avatar says on the correct path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    lesson = LessonRun.model_validate(json.loads(Path(args.run).read_text(encoding="utf-8")))
    modes = ("correct", "near", "wrong", "silence", "mixed")
    results = {mode: asyncio.run(play(lesson, mode)) for mode in modes}

    taken: set[str] = set()
    for result in results.values():
        taken |= result.taken
    authored = all_branches(lesson)
    never = [b for b in authored if b not in taken]

    if args.json:
        print(json.dumps({
            "lesson": lesson.lesson_id,
            "modes": {m: {"steps": len(r.steps), "minutes": round(r.seconds / 60, 1),
                          "stalls": r.stalls, "unhandled": r.unhandled}
                      for m, r in results.items()},
            "branches": {"authored": len(authored), "reached": len(authored) - len(never),
                         "never_reached": never},
        }, indent=2, ensure_ascii=False))
        return 1 if any(r.stalls for r in results.values()) else 0

    print(f"{lesson.title}  ({lesson.lesson_id})  {len(lesson.activities)} activities\n")
    for mode, result in results.items():
        label = {"correct": "a class that gets everything right",
                 "near": "a class that almost gets it",
                 "wrong": "a class that gets everything wrong",
                 "silence": "a class that says nothing at all",
                 "mixed": "a mixed class (right, wrong, near, silent in turn)"}[mode]
        print(f"  {label:38} {len(result.steps):>3} steps  {result.seconds / 60:>4.1f} min")
        for stall in result.stalls:
            print(f"      ✗ STALL  {stall}")
        for gap in result.unhandled:
            print(f"      ✗ {gap}")
    print()
    print(f"  branch coverage: {len(authored) - len(never)}/{len(authored)} authored branches "
          f"were reached by one of those classes")
    dead, missed = [], []
    for branch in never:
        activity_id, _, outcome = branch.rpartition(":")
        activity = next((a for a in lesson.activities if a.id == activity_id), None)
        timed = activity is not None and bool(activity.duration_s)
        if (outcome == "silence" and timed) or (outcome == "timeout" and activity is not None
                                                and not timed):
            dead.append(branch)
        else:
            missed.append(branch)
    if dead:
        print(f"      · {len(dead)} no-answer branch(es) cannot fire as written. Which one is")
        print("        live depends on the timing (PROTOCOL §9.4): with durationS set, nobody")
        print("        answering is reported as 'timeout'; without it, as 'silence'. The other")
        print("        one is harmless, and becomes live if the timing is ever changed:")
        for branch in dead:
            print(f"          {branch}")
    for branch in missed:
        print(f"      ! not exercised by these classes: {branch}"
              f"  (reachable, but only for a class that changes its behaviour mid-lesson)")

    stalled = sum(len(r.stalls) + len(r.unhandled) for r in results.values())
    print()
    if stalled:
        print(f"✗ {stalled} place(s) where the lesson would stop or leave a child without help")
    else:
        print("✓ no stalls: every path through this lesson reaches the end, "
              "including the class that never answers")

    if args.transcript:
        print("\n--- what the avatar says (correct path) ---")
        for line in results["correct"].transcript:
            print(f"  {line}")
    return 1 if stalled else 0


if __name__ == "__main__":
    raise SystemExit(main())
