#!/usr/bin/env python3
"""Sit in the teacher's chair: read the turn she would read, make her moves.

    ./scripts/relay-teach.py read           # what the room is asking of her now
    ./scripts/relay-teach.py play moves.json
    ./scripts/relay-teach.py say "Hello!" --board "# Hello" --image asset://... --wake 8

Only useful with BRIGHT_AGENT=relay. Everything the moves touch is the real
room: the same tool surface, the same refusals, the same board, the same
evidence ledger, the same census. The only thing that is not a model is the
thing choosing the moves.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

RELAY = Path(os.environ.get("BRIGHT_RELAY_DIR") or ".runtime/teacher-agent/relay")


def _wait_for_turn(timeout: float) -> dict | None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        ask = RELAY / "turn.json"
        if ask.exists():
            try:
                return json.loads(ask.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                pass
        time.sleep(0.3)
    return None


def cmd_read(args) -> int:
    body = _wait_for_turn(args.wait)
    if body is None:
        print("no turn is waiting (is the room open, and BRIGHT_AGENT=relay?)")
        return 2
    if args.json:
        print(json.dumps(body, ensure_ascii=False, indent=1))
        return 0
    print(f"── turn {body['turn_id']}  (waiting since {body.get('waiting_since')}) " + "─" * 20)
    print(body["input"])
    return 0


def _send(calls: list[dict], wait: float) -> int:
    body = _wait_for_turn(wait)
    if body is None:
        print("no turn is waiting")
        return 2
    (RELAY / "moves.json").write_text(
        json.dumps({"turn_id": body["turn_id"], "calls": calls}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"sent {len(calls)} call(s) for {body['turn_id']}: "
          + ", ".join(c["name"] for c in calls))
    return 0


def cmd_play(args) -> int:
    calls = json.loads(Path(args.file).read_text(encoding="utf-8"))
    if isinstance(calls, dict):
        calls = calls.get("calls") or []
    return _send(calls, args.wait)


def cmd_say(args) -> int:
    calls: list[dict] = []
    for path in args.read or []:
        calls.append({"name": "read_library", "arguments": {"path": path}})
    if args.image:
        arguments = {"asset": args.image}
        if args.second:
            arguments["second"] = args.second
        calls.append({"name": "show_image", "arguments": arguments})
    if args.clip:
        calls.append({"name": "play_clip",
                      "arguments": {"asset": args.clip, "transcript": args.transcript or ""}})
    if args.exercise:
        calls.append({"name": "show_exercise",
                      "arguments": json.loads(Path(args.exercise).read_text(encoding="utf-8"))})
    if args.plan:
        calls.append({"name": "plan", "arguments": {"plan": args.plan}})
    if args.evidence:
        objective, outcome, mode = args.evidence.split(":")
        calls.append({"name": "record_evidence", "arguments": {
            "student_id": args.student, "objective_id": objective,
            "outcome": outcome, "mode": mode}})
    say: dict = {"teacher_line": args.line}
    if args.board:
        say["board_text"] = args.board
    if args.wake:
        say["wake_in_s"] = args.wake
    if args.awaiting:
        say["awaiting_answer"] = True
    if args.closing:
        say["closing"] = True
    calls.append({"name": "say", "arguments": say})
    return _send(calls, args.wait)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wait", type=float, default=180.0)
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("read", help="print the turn input she would read")
    r.add_argument("--json", action="store_true")
    r.set_defaults(func=cmd_read)

    p = sub.add_parser("play", help="send a JSON file of calls")
    p.add_argument("file")
    p.set_defaults(func=cmd_play)

    s = sub.add_parser("say", help="build one move on the command line")
    s.add_argument("line")
    s.add_argument("--board")
    s.add_argument("--image")
    s.add_argument("--second")
    s.add_argument("--clip")
    s.add_argument("--transcript")
    s.add_argument("--exercise", help="path to a show_exercise payload")
    s.add_argument("--plan")
    s.add_argument("--evidence", help="objective:outcome:mode")
    s.add_argument("--student", default="learner-1")
    s.add_argument("--read", action="append")
    s.add_argument("--wake", type=int)
    s.add_argument("--awaiting", action="store_true")
    s.add_argument("--closing", action="store_true")
    s.set_defaults(func=cmd_say)

    args = ap.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
