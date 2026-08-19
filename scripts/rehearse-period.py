#!/usr/bin/env python3
"""Drive a scripted pupil through a whole period, and score the PERIOD.

This is a rehearsal harness, not a test of her judgement. It never asserts that
she made the right teaching move -- it asserts that the machinery carried her
moves, and it reports what a whole lesson actually used.

The distinction matters because the failure this was written for is invisible
per turn: on 2026-08-19 she taught a three-lesson unit in six turns, played none
of the ten authored recordings, showed one picture, and marked every single
response correct. Every individual turn looked fine.

Nothing in this file may tell her what to teach. Every pupil line is something a
child could say.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

CORE = "http://127.0.0.1:8004"


def _get(path: str, timeout: float = 10.0):
    with urllib.request.urlopen(CORE + path, timeout=timeout) as r:
        return json.load(r)


def _post(path: str, payload: dict, timeout: float = 240.0):
    req = urllib.request.Request(
        CORE + path, data=json.dumps(payload).encode(),
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def pupil_lines(path: str) -> list[str]:
    out = []
    for raw in open(path, encoding="utf-8"):
        line = raw.rstrip("\n")
        if line.strip().startswith("#"):
            continue
        out.append(line.strip())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pupil", default="scripts/pupils/lesson1.txt")
    ap.add_argument("--limit", type=int, default=0, help="stop after N utterances")
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args()

    status = _get("/teacher/status")
    if not status.get("sessionOpen"):
        print("no open period -- open the room first (the Stage claims the audio lease)")
        return 2

    lines = pupil_lines(args.pupil)
    if args.limit:
        lines = lines[: args.limit]

    turns, silent, errors = 0, 0, 0
    latencies: list[float] = []
    for line in lines:
        t0 = time.time()
        try:
            body = _post("/teacher/turn", {"text": line})
        except Exception as exc:  # noqa: BLE001
            errors += 1
            print(f"  bé ▸ {line!r}  !! {exc}")
            continue
        latencies.append(time.time() - t0)
        turns += 1
        said = (body.get("say") or "").strip()
        if not said:
            silent += 1
        if body.get("error"):
            errors += 1
        if not args.quiet:
            print(f"\n  bé ▸ {line or '(im lặng)'}   ({latencies[-1]:.1f}s)")
            print(f"  cô ◂ {said or '(im lặng)'}")

    period = (_get("/teacher/status") or {}).get("period") or {}
    outcomes = period.get("outcomes") or {}
    total_ev = period.get("evidenceRows") or 0
    latencies.sort()
    p50 = latencies[len(latencies) // 2] if latencies else 0.0

    # Period-level properties. Each one is a thing a real lesson has and the
    # 2026-08-19 failure did not.
    checks = {
        "played a recording": len(period.get("clips") or []) >= 1,
        "put up an exercise": len(period.get("exercises") or []) >= 1,
        "changed the picture": len(period.get("images") or []) >= 3,
        "opened a skill": any(
            p.startswith("skills/") and p != "skills/index.md"
            for p in period.get("reads") or []
        ),
        "read the key before judging": (
            total_ev == 0
            or any(p.endswith("keys.md") for p in period.get("reads") or [])
        ),
        "marking is not degenerate": not (total_ev >= 4 and len(outcomes) == 1),
        "she spoke every turn": silent == 0,
        "no turn errored": errors == 0,
    }

    print("\n" + "=" * 72)
    print(f"PERIOD REPORT   turns={turns}  p50={p50:.1f}s  "
          f"unit={period.get('unit') or '?'}  minutes={period.get('minutes', 0)}")
    print("=" * 72)
    print(f"  reads      {', '.join(period.get('reads') or []) or '-'}")
    print(f"  clips      {', '.join(period.get('clips') or []) or '-'}")
    print(f"  images     {', '.join(period.get('images') or []) or '-'}")
    print(f"  exercises  {', '.join(period.get('exercises') or []) or '-'}")
    print(f"  objectives {', '.join(period.get('objectives') or []) or '-'}")
    print(f"  outcomes   {json.dumps(outcomes, sort_keys=True)}")
    print(f"  modes      {json.dumps(period.get('modes') or {}, sort_keys=True)}")
    print()
    for name, passed in checks.items():
        print(f"  {'PASS' if passed else 'FAIL'}  {name}")
    failed = [n for n, ok in checks.items() if not ok]
    print()
    print(f"{len(checks) - len(failed)}/{len(checks)} period properties hold")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
