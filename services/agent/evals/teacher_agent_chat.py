"""Live chat with the teacher. Off-script turns, no expected banana line."""

from __future__ import annotations

import json
import os
import sys
import time

import httpx

# Things a child might actually type. None of these is a unit answer key.
LINES = (
    "hi i am minh",
    "what is that",
    "i dont know",
    "can you help me",
)


def main() -> int:
    core = os.environ.get("CORE_HTTP", "http://127.0.0.1:8004")
    timeout = float(os.environ.get("TEACHER_TURN_TIMEOUT_S", "90"))
    unit = os.environ.get("TEACHER_CHAT_UNIT", "gs3-u1-hello")
    with httpx.Client(timeout=timeout) as client:
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            try:
                health = client.get(f"{core}/health").json()
            except Exception:
                health = {}
            if health.get("status") == "ok":
                break
            time.sleep(1)
        else:
            print(json.dumps({"ok": False, "error": "core not ready"}))
            return 1
        started = client.post(
            f"{core}/teacher/session",
            json={
                "unitId": unit,
                "learnerId": "learner-1",
                "learnerName": "Minh",
                "open": True,
            },
        )
        started.raise_for_status()
        opening = (started.json() or {}).get("opening") or {}
        turns = [{"role": "teacher", "text": opening.get("say"), "present": opening.get("present")}]
        if not opening.get("say"):
            print(json.dumps({"ok": False, "error": "teacher did not open class", "turns": turns}))
            return 1
        for line in LINES:
            res = client.post(f"{core}/teacher/turn", json={"text": line})
            body = res.json() if res.status_code == 200 else {"ok": False, "error": res.text[:200]}
            turns.append({"role": "learner", "text": line})
            turns.append(
                {
                    "role": "teacher",
                    "text": body.get("say"),
                    "present": body.get("present"),
                    "reads": body.get("reads"),
                    "ok": body.get("ok"),
                    "error": body.get("error"),
                }
            )
            if res.status_code != 200 or not body.get("say"):
                print(json.dumps({"ok": False, "error": f"no reply to {line!r}", "turns": turns}, ensure_ascii=False))
                return 1
        says = [row["text"] for row in turns if row["role"] == "teacher"]
        unique = {str(text or "").strip().lower() for text in says}
        out = {
            "ok": True,
            "unitId": unit,
            "turns": turns,
            "asked": any("?" in str(text or "") for text in says),
            "not_a_tape": len(unique) >= 3,
        }
        if not out["not_a_tape"]:
            out["ok"] = False
            out["error"] = "teacher repeated the same line"
        print(json.dumps(out, ensure_ascii=False))
        return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
