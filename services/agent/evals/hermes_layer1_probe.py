"""Layer 1 live probe: pinned Hermes + one Core MCP tool + hosted provider.

This is not a product lesson and not CI. It answers one question: does the
provider, through Bright's Hermes sidecar, emit exactly one legal
``classroom_propose_move`` on healthy turns?

Run via ``scripts/hermes-layer1-probe.sh``. Do not print secrets, child text,
or raw tool arguments into the artifact.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sqlite3
import sys
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from fastapi import FastAPI
from fastapi.responses import JSONResponse
import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[3]
CORE_DIR = ROOT / "services" / "classroom-core"
AGENT_DIR = ROOT / "services" / "agent"
CONTRACTS = ROOT / "packages" / "contracts" / "python"
for path in (AGENT_DIR, CORE_DIR, CONTRACTS):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from bright_agent.base import Done, TextDelta, ToolCall, ToolResult  # noqa: E402
from bright_agent.hermes import HermesAgent, HermesConfig  # noqa: E402
from bright_contracts import (  # noqa: E402
    AvailableAction,
    LastInteraction,
    LessonPosition,
    Scene,
    StudentBrief,
    TurnContext,
)
from mcp_server import TurnRegistry, build_mcp_router  # noqa: E402
from state import StateStore  # noqa: E402

SENTINEL = "bright-layer1-not-for-storage"
LEGAL_MOVES = {
    "repeat_activity": "repeat_activity",
    "next_activity": "next_activity",
    "scaffold_down": "scaffold_down",
}


@dataclass
class ProbeCore:
    store: StateStore
    runner: Any
    student_id: str
    session_id: str | None
    turn_registry: TurnRegistry
    invocations: list[dict[str, str]]


def make_probe_core() -> ProbeCore:
    store = StateStore(mode="FULL")
    activity = SimpleNamespace(id="layer1-probe")
    runner = SimpleNamespace(current=activity, _generation=1)
    core = ProbeCore(
        store=store,
        runner=runner,
        student_id="s17",
        session_id=None,
        turn_registry=TurnRegistry(SimpleNamespace(), default_ttl_s=90.0),
        invocations=[],
    )
    # TurnRegistry reads attributes off the object it was constructed with.
    core.turn_registry.core = core

    async def execute(_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        move_id = str(arguments.get("move_id") or "")
        core.invocations.append({"move_id": move_id})
        return {"ok": True, "applied": False, "probe": True}

    core._execute = execute  # type: ignore[attr-defined]
    return core


def build_mcp_app(core: ProbeCore, token: str) -> FastAPI:
    app = FastAPI()
    app.include_router(build_mcp_router(lambda: core, token))

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok", "mode": "PROBE"}

    @app.post("/probe/register")
    async def register(body: dict[str, Any]) -> JSONResponse:
        turn_id = str(body.get("turn_id") or "")
        if not turn_id:
            return JSONResponse({"ok": False, "reason": "turn_id required"}, status_code=400)
        core.turn_registry.retire(turn_id)
        core.turn_registry.register(
            turn_id,
            core._execute,  # type: ignore[attr-defined]
            student_id=core.student_id,
            moves=LEGAL_MOVES,
            ttl_s=90.0,
        )
        return JSONResponse({"ok": True, "turn_id": turn_id, "moves": sorted(LEGAL_MOVES)})

    @app.get("/probe/invocations")
    async def invocations() -> dict[str, int]:
        return {"count": len(core.invocations)}

    return app


def make_ctx(*, outcome: str, detail: str) -> TurnContext:
    return TurnContext(
        stateVersion=1,
        lesson=LessonPosition(
            lessonId="layer1-probe",
            classId="probe",
            activityIndex=0,
            activityCount=1,
            stage="PRACTICE",
            currentStudentId="s17",
        ),
        scene=Scene(stateVersion=1, kind="choice", props={"prompt": "Which one?"}),
        student=StudentBrief(id="s17", name="Minh", skills={"food_vocab": 0.4}),
        lastInteraction=LastInteraction(kind="choice", detail=detail, outcome=outcome),
        availableActions=[
            AvailableAction(id="repeat_activity", label="repeat"),
            AvailableAction(id="next_activity", label="advance"),
            AvailableAction(id="scaffold_down", label="scaffold"),
        ],
        recalled=[],
    )


CASES: list[dict[str, str]] = [
    {"id": "correct-1", "kind": "live", "outcome": "correct"},
    {"id": "correct-2", "kind": "live", "outcome": "correct"},
    {"id": "wrong-1", "kind": "live", "outcome": "wrong"},
    {"id": "wrong-2", "kind": "live", "outcome": "wrong"},
    {"id": "near-1", "kind": "live", "outcome": "near"},
    {"id": "ambiguous-1", "kind": "live", "outcome": "uncertain"},
    {"id": "silence-1", "kind": "live", "outcome": "silence"},
    {"id": "repeat-1", "kind": "live", "outcome": "wrong"},
    {"id": "correct-3", "kind": "live", "outcome": "correct"},
    {"id": "wrong-3", "kind": "live", "outcome": "wrong"},
    {"id": "reconnect-1", "kind": "reconnect", "outcome": "correct"},
    {"id": "timeout-1", "kind": "timeout", "outcome": "wrong"},
]


def _scrubbed_row(case: dict[str, str], **fields: Any) -> dict[str, Any]:
    return {
        "id": case["id"],
        "kind": case["kind"],
        "outcome": case["outcome"],
        **fields,
    }


async def _register(core_url: str, token: str, turn_id: str) -> None:
    async with httpx.AsyncClient(timeout=5.0) as client:
        response = await client.post(
            f"{core_url}/probe/register",
            json={"turn_id": turn_id},
            headers={"authorization": f"Bearer {token}"},
        )
        response.raise_for_status()


async def _one_live_turn(
    agent: HermesAgent,
    core_url: str,
    token: str,
    case: dict[str, str],
) -> dict[str, Any]:
    turn_id = f"layer1-{case['id']}-{uuid.uuid4().hex[:8]}"
    await _register(core_url, token, turn_id)
    agent.prepare_turn(turn_id)
    ctx = make_ctx(outcome=case["outcome"], detail=SENTINEL)
    events: list[Any] = []
    started = time.perf_counter()
    try:
        async for event in agent.turn(ctx):
            events.append(event)
    except Exception as exc:  # noqa: BLE001 — probe boundary
        return _scrubbed_row(
            case,
            ok=False,
            finish="exception",
            tool_calls=0,
            legal=False,
            fallback=True,
            latency_s=round(time.perf_counter() - started, 3),
            detail=type(exc).__name__,
        )
    tool_calls = sum(1 for event in events if isinstance(event, ToolCall))
    results = [event for event in events if isinstance(event, ToolResult)]
    done = next((event for event in events if isinstance(event, Done)), None)
    text = "".join(event.text for event in events if isinstance(event, TextDelta))
    legal = bool(results) and all(event.ok for event in results)
    complete = done is not None and done.reason == "complete" and tool_calls == 1 and legal
    return _scrubbed_row(
        case,
        ok=complete,
        finish=done.reason if done else "missing_done",
        tool_calls=tool_calls,
        legal=legal,
        fallback=not complete,
        latency_s=round(agent.last_latency_s or (time.perf_counter() - started), 3),
        spoke=bool(text.strip()),
        detail=done.detail if done else None,
    )


async def run_turns(artifact_dir: Path) -> dict[str, Any]:
    core_url = os.environ["LAYER1_CORE_URL"].rstrip("/")
    token = os.environ["BRIGHT_MCP_TOKEN"]
    config = HermesConfig.from_env()
    if not config.api_key:
        config.api_key = os.environ.get("HERMES_API_KEY", "")
    agent = HermesAgent(config=config)
    rows: list[dict[str, Any]] = []
    artifact_dir.mkdir(parents=True, exist_ok=True)
    try:
        healthy = await agent.health()
        rows.append(
            {
                "id": "health",
                "kind": "health",
                "ok": bool(healthy),
                "finish": "complete" if healthy else "error",
                "tool_calls": 0,
                "legal": True,
                "fallback": not healthy,
                "latency_s": 0.0,
            }
        )
        for case in CASES:
            if case["kind"] == "live":
                await asyncio.sleep(0.4)
            if case["kind"] == "timeout":
                short = HermesConfig(
                    base_url=config.base_url,
                    api_key=config.api_key,
                    model=config.model,
                    request_timeout_s=0.05,
                    connect_timeout_s=0.05,
                )
                async with HermesAgent(config=short) as timed:
                    row = await _one_live_turn(timed, core_url, token, case)
                row["ok"] = row["finish"] != "missing_done"
                row["expected_failure"] = True
                rows.append(row)
                continue
            if case["kind"] == "reconnect":
                # A cancelled/timeout stream can still occupy Hermes'
                # max_concurrent_runs=1 slot for a moment.
                await asyncio.sleep(2.0)
                await agent.health()
                row = await _one_live_turn(agent, core_url, token, case)
                if str(row.get("detail") or "").startswith("HTTP 429"):
                    await asyncio.sleep(2.0)
                    row = await _one_live_turn(agent, core_url, token, case)
                    row["retried_after_429"] = True
                rows.append(row)
                continue
            rows.append(await _one_live_turn(agent, core_url, token, case))
    finally:
        await agent.aclose()
        (artifact_dir / "partial.json").write_text(
            json.dumps({"turns": rows}, indent=2) + "\n", encoding="utf-8"
        )

    live_healthy = [
        row
        for row in rows
        if row.get("kind") == "live" and not row.get("expected_failure")
    ]
    live_pass = all(row.get("ok") for row in live_healthy) if live_healthy else False
    failure_pass = all(
        row.get("ok") for row in rows if row.get("expected_failure") or row.get("kind") == "timeout"
    )
    leak = _scan_for_sentinel(Path(os.environ.get("HERMES_HOME", "")), artifact_dir)
    report = {
        "artifactVersion": 1,
        "mode": "hermes_layer1",
        "runtime": os.environ.get("HERMES_PINNED_VERSION", "manifest"),
        "startedAt": datetime.now(timezone.utc).isoformat(),
        "ok": bool(live_pass and failure_pass and not leak),
        "liveHealthyTurns": len(live_healthy),
        "liveHealthyPassed": sum(1 for row in live_healthy if row.get("ok")),
        "sentinelLeak": leak,
        "turns": rows,
    }
    artifact_dir.mkdir(parents=True, exist_ok=True)
    (artifact_dir / "result.json").write_text(
        json.dumps(report, indent=2) + "\n", encoding="utf-8"
    )
    return report


def _scan_for_sentinel(*roots: Path) -> bool:
    needle = SENTINEL.encode()
    for root in roots:
        if not root or not root.exists():
            continue
        if root.is_file():
            try:
                if needle in root.read_bytes():
                    return True
            except OSError:
                return True
            continue
        for path in root.rglob("*"):
            if not path.is_file() or path.suffix in {".lock", ".pid"}:
                continue
            if path.suffix in {".db", ".sqlite", ".sqlite3"}:
                try:
                    con = sqlite3.connect(path)
                    tables = con.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    ).fetchall()
                    for (name,) in tables:
                        if str(name).startswith("sqlite_"):
                            continue
                        for row in con.execute(f'SELECT * FROM "{name}"'):
                            blob = " ".join("" if value is None else str(value) for value in row)
                            if SENTINEL in blob:
                                return True
                except sqlite3.Error:
                    return True
                continue
            try:
                if needle in path.read_bytes():
                    return True
            except OSError:
                return True
    return False


async def serve_mcp() -> None:
    token = os.environ["BRIGHT_MCP_TOKEN"]
    host = os.environ.get("LAYER1_CORE_HOST", "127.0.0.1")
    port = int(os.environ.get("LAYER1_CORE_PORT", "18004"))
    core = make_probe_core()
    app = build_mcp_app(core, token)
    server = uvicorn.Server(
        uvicorn.Config(app, host=host, port=port, log_level="warning")
    )
    await server.serve()


def main() -> int:
    parser = argparse.ArgumentParser(description="Hermes Layer 1 provider probe")
    parser.add_argument("command", choices=("serve", "run"))
    parser.add_argument("--artifact-dir", default="")
    args = parser.parse_args()
    if args.command == "serve":
        asyncio.run(serve_mcp())
        return 0
    artifact = Path(args.artifact_dir) if args.artifact_dir else Path("tests/.artifacts/hermes-layer1")
    report = asyncio.run(run_turns(artifact))
    print(json.dumps({"ok": report["ok"], "liveHealthyPassed": report["liveHealthyPassed"], "liveHealthyTurns": report["liveHealthyTurns"], "sentinelLeak": report["sentinelLeak"]}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
