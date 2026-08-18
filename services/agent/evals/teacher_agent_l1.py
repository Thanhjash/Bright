"""Layer 1 gate: same driver, two library units. No unit answer key in code."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import httpx

REPO = Path(__file__).resolve().parents[3]
LIBRARY = REPO / "content" / "library"
OBJECTIVE = re.compile(r"id:\s*`([a-z0-9-]+)`")
ASSET = re.compile(r"asset://[a-z0-9_./-]+", re.IGNORECASE)

UNITS = (
    {
        "unit_id": "gs3-u1-hello",
        "first": "that yellow one",
        "second": "apple",
    },
    {
        "unit_id": "gs3-u1-hello",
        "first": "the sky one",
        "second": "red",
    },
)


def _unit_files(unit_id: str) -> list[Path]:
    folder = LIBRARY / "units" / unit_id
    return [folder / "map.md", folder / "keys.md", folder / "practice.md"]


def _objectives(unit_id: str) -> set[str]:
    text = (LIBRARY / "units" / unit_id / "map.md").read_text(encoding="utf-8")
    return set(OBJECTIVE.findall(text))


def _assets(unit_id: str) -> set[str]:
    found: set[str] = set()
    for path in _unit_files(unit_id):
        found.update(ASSET.findall(path.read_text(encoding="utf-8")))
    return found


def _child_safe(line: str) -> bool:
    text = " ".join((line or "").split())
    if not text or len(text) > 220:
        return False
    bits = re.findall(r"[^.!?]+[.!?]", text)
    leftover = re.sub(r"[^.!?]+[.!?]\s*", "", text).strip()
    return bool(bits) and len(bits) <= 2 and not leftover


def _check_turn(unit_id: str, utterance: str, body: dict) -> str | None:
    if not body.get("ok") or not body.get("say"):
        return "no teacher say"
    if not _child_safe(str(body.get("say") or "")):
        return f"say is not child-safe: {body.get('say')!r}"
    reads = [str(path) for path in (body.get("reads") or [])]
    prefix = f"units/{unit_id}/"
    if not any(prefix in path for path in reads):
        return f"did not read or search the {unit_id} library"
    allowed_obj = _objectives(unit_id)
    evidence = body.get("evidence") or []
    for row in evidence:
        objective = str(row.get("objective_id") or "")
        if objective not in allowed_obj:
            return f"objective {objective!r} is not on the {unit_id} map"
    allowed_assets = _assets(unit_id)
    present = body.get("present") or {}
    slots = present.get("slots") if isinstance(present, dict) else None
    if isinstance(slots, dict):
        for value in slots.values():
            text = str(value or "")
            if text.startswith("asset://") and text not in allowed_assets:
                return f"presented {text} which is not in the {unit_id} library"
    blob = json.dumps(body, ensure_ascii=False).lower()
    if "goto" in blob or "propose_move" in blob:
        return "graph leaked"
    ev_blob = json.dumps(evidence, ensure_ascii=False).lower()
    raw = utterance.strip().lower()
    if " " in raw and raw in ev_blob:
        return "raw learner text in evidence"
    return None


def _drive_unit(client: httpx.Client, core: str, spec: dict) -> dict:
    unit_id = spec["unit_id"]
    started = client.post(
        f"{core}/teacher/session",
        json={
            "unitId": unit_id,
            "learnerId": "learner-1",
            "learnerName": "Minh",
            "open": False,
        },
    )
    started.raise_for_status()
    first = client.post(f"{core}/teacher/turn", json={"text": spec["first"]})
    first_body = first.json() if first.headers.get("content-type", "").startswith("application/json") else {}
    second = client.post(f"{core}/teacher/turn", json={"text": spec["second"]})
    second_body = second.json() if second.status_code == 200 else {"ok": False}
    error = None
    if first.status_code != 200:
        error = f"first turn HTTP {first.status_code}"
    else:
        error = _check_turn(unit_id, spec["first"], first_body)
    if error is None and second.status_code == 200:
        second_err = _check_turn(unit_id, spec["second"], second_body)
        if second_err:
            error = f"second: {second_err}"
        elif not (second_body.get("evidence") or first_body.get("evidence")):
            error = "no categorical evidence in the session"
    elif error is None:
        error = f"second turn HTTP {second.status_code}"
    return {
        "unitId": unit_id,
        "ok": error is None,
        "error": error,
        "first": first_body,
        "second": second_body,
    }


def main() -> int:
    core = os.environ.get("CORE_HTTP", "http://127.0.0.1:8004")
    timeout = float(os.environ.get("TEACHER_TURN_TIMEOUT_S", "90"))
    with httpx.Client(timeout=timeout) as client:
        deadline = time.monotonic() + 90
        health: dict = {}
        while time.monotonic() < deadline:
            try:
                health = client.get(f"{core}/health").json()
            except Exception:
                health = {}
            if health.get("status") == "ok":
                break
            time.sleep(1)
        else:
            print(json.dumps({"ok": False, "error": "core not ready", "health": health}))
            return 1
        reports = [_drive_unit(client, core, spec) for spec in UNITS]
    out = {"ok": all(item["ok"] for item in reports), "units": reports}
    print(json.dumps(out, ensure_ascii=False))
    return 0 if out["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
