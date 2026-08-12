"""Authenticated, turn-scoped MCP surface owned by Classroom Core.

This is a deliberately small implementation of MCP Streamable HTTP.  Bright
only needs the server half of ``initialize``, ``tools/list`` and ``tools/call``;
there is no private REST shortcut hiding behind the MCP configuration.

Every tool call carries an unguessable Core-issued ``turn_id``.  The registry
binds that capability to the exact state/activity generation and executor that
created it, expires it quickly, and deduplicates mutations.  Consequently a
late Hermes run can neither write into a newer activity nor another learner.
"""

from __future__ import annotations

import asyncio
import hmac
import json
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

ToolExecutor = Callable[[str, dict[str, Any]], Awaitable[Any]]

PROTOCOL_VERSION = "2025-06-18"
MUTATING_TOOLS = frozenset({"classroom_propose_move"})


class TurnRejected(RuntimeError):
    """The supplied capability is missing, stale, expired or out of scope."""


@dataclass(slots=True)
class TurnEntry:
    turn_id: str
    executor: ToolExecutor
    expires_at: float
    state_version: int
    decision_revision: int
    session_id: str | None
    activity_id: str | None
    activity_generation: int | None
    response_turn_id: str | None
    student_id: str | None
    moves: dict[str, str] = field(default_factory=dict)
    terminal_mutation: str | None = None
    mutations: dict[str, Any] = field(default_factory=dict)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    active_calls: set[asyncio.Task[Any]] = field(default_factory=set)


class TurnRegistry:
    """Short-lived capability registry for the Core↔Hermes MCP boundary."""

    def __init__(self, core: Any, *, default_ttl_s: float = 15.0) -> None:
        self.core = core
        self.default_ttl_s = default_ttl_s
        self._turns: dict[str, TurnEntry] = {}

    def register(
        self,
        turn_id: str,
        executor: ToolExecutor,
        *,
        student_id: str | None,
        moves: dict[str, str] | None = None,
        ttl_s: float | None = None,
    ) -> TurnEntry:
        if not turn_id or turn_id in self._turns:
            raise ValueError("turn_id must be non-empty and unique")
        runner = getattr(self.core, "runner", None)
        current = getattr(runner, "current", None)
        controller = getattr(self.core, "session_controller", None)
        assignment = None
        session_id = getattr(self.core, "session_id", None)
        if controller is not None and session_id:
            assignment = controller.assignments.current_for_activity(
                session_id,
                getattr(current, "id", ""),
                getattr(runner, "_generation", 0),
            )
        entry = TurnEntry(
            turn_id=turn_id,
            executor=executor,
            expires_at=time.monotonic() + (ttl_s or self.default_ttl_s),
            state_version=int(self.core.store.state_version),
            decision_revision=int(getattr(self.core.store, "decision_revision", 0)),
            session_id=session_id,
            activity_id=getattr(current, "id", None),
            activity_generation=getattr(runner, "_generation", None),
            response_turn_id=getattr(assignment, "response_turn_id", None),
            student_id=student_id,
            moves=dict(moves or {}),
        )
        self._turns[turn_id] = entry
        self.prune()
        return entry

    def retire(self, turn_id: str) -> None:
        entry = self._turns.pop(turn_id, None)
        if entry is None:
            return
        try:
            current = asyncio.current_task()
        except RuntimeError:  # valid for shutdown/maintenance outside a loop
            current = None
        for task in tuple(entry.active_calls):
            if task is not current and not task.done():
                task.cancel()

    def prune(self) -> None:
        now = time.monotonic()
        for key, entry in list(self._turns.items()):
            if entry.expires_at <= now:
                self._turns.pop(key, None)

    def _resolve(self, turn_id: str, *, validate_scope: bool = True) -> TurnEntry:
        self.prune()
        entry = self._turns.get(turn_id)
        if entry is None:
            raise TurnRejected("unknown or expired turn_id")
        if not validate_scope:
            return entry
        runner = getattr(self.core, "runner", None)
        current = getattr(runner, "current", None)
        if int(getattr(self.core.store, "decision_revision", 0)) != entry.decision_revision:
            raise TurnRejected("turn decision_revision is stale")
        if getattr(self.core, "session_id", None) != entry.session_id:
            raise TurnRejected("turn session is stale")
        if getattr(current, "id", None) != entry.activity_id:
            raise TurnRejected("turn activity is stale")
        if getattr(runner, "_generation", None) != entry.activity_generation:
            raise TurnRejected("turn activity generation is stale")
        controller = getattr(self.core, "session_controller", None)
        if controller is not None and entry.response_turn_id is not None:
            assignment = controller.assignments.current_for_activity(
                str(entry.session_id), str(entry.activity_id), int(entry.activity_generation or 0)
            )
            if assignment is None or assignment.response_turn_id != entry.response_turn_id:
                raise TurnRejected("turn response capability is stale")
        elif getattr(self.core, "student_id", None) != entry.student_id:
            # Legacy single-learner seam only. Autonomous attribution is bound
            # by responseTurnId above, never by this process-level field.
            raise TurnRejected("turn learner scope is stale")
        return entry

    async def invoke(self, name: str, arguments: dict[str, Any]) -> Any:
        turn_id = arguments.get("turn_id")
        if not isinstance(turn_id, str) or not turn_id:
            raise TurnRejected("turn_id is required")
        entry = self._resolve(turn_id, validate_scope=False)
        clean = dict(arguments)
        clean.pop("turn_id", None)

        # A model/tool transport may replay a mutation with a fresh JSON-RPC
        # id.  Dedupe on its canonical intent, not on transport metadata.
        dedupe_key = ""
        if name in MUTATING_TOOLS:
            dedupe_key = name + ":" + json.dumps(clean, sort_keys=True, separators=(",", ":"))
        task = asyncio.current_task()
        if task is not None:
            entry.active_calls.add(task)
        try:
            async with entry.lock:
                if dedupe_key and dedupe_key in entry.mutations:
                    return entry.mutations[dedupe_key]
                # Validate after the dedupe lookup: a successful choose_next moves
                # state by design, but an exact transport replay must return the
                # first result rather than apply again or masquerade as a new turn.
                self._resolve(turn_id)
                if name == "classroom_propose_move":
                    if entry.terminal_mutation is not None:
                        raise TurnRejected("terminal proposal already used")
                    move_id = str(clean.get("move_id") or "")
                    action_id = entry.moves.get(move_id)
                    if action_id is None:
                        raise TurnRejected("move_id was not offered for this turn")
                    clean["_action_id"] = action_id
                result = await entry.executor(name, clean)
                if dedupe_key:
                    entry.mutations[dedupe_key] = result
                    entry.terminal_mutation = dedupe_key
                return result
        finally:
            if task is not None:
                entry.active_calls.discard(task)


def _schema(properties: dict[str, Any], required: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "turn_id": {
                "type": "string",
                "description": "Exact BRIGHT TURN ID supplied in this turn's input.",
            },
            **properties,
        },
        "required": ["turn_id", *required],
        "additionalProperties": False,
    }


TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "classroom_propose_move",
        "description": "Choose one offered move and one short non-evaluative teacher line. This ends the turn.",
        "inputSchema": _schema(
            {
                "move_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "teacher_line": {"type": "string", "minLength": 1, "maxLength": 180},
            },
            ["move_id", "teacher_line"],
        ),
    },
)
TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}


def _validate_arguments(tool: dict[str, Any], arguments: dict[str, Any]) -> str | None:
    """Validate the intentionally-small JSON Schema subset used above."""
    schema = tool["inputSchema"]
    properties = schema["properties"]
    missing = [key for key in schema.get("required", []) if key not in arguments]
    if missing:
        return "missing required arguments: " + ", ".join(missing)
    unknown = sorted(set(arguments) - set(properties))
    if unknown and schema.get("additionalProperties") is False:
        return "unknown arguments: " + ", ".join(unknown)
    python_types = {"string": str, "integer": int, "object": dict}
    for key, value in arguments.items():
        rule = properties.get(key)
        if rule is None:
            continue
        expected = python_types.get(rule.get("type"))
        if expected is not None and (not isinstance(value, expected) or isinstance(value, bool)):
            return f"{key} must be {rule['type']}"
        if "enum" in rule and value not in rule["enum"]:
            return f"{key} is not an allowed value"
        if isinstance(value, int):
            if "minimum" in rule and value < rule["minimum"]:
                return f"{key} is below its minimum"
            if "maximum" in rule and value > rule["maximum"]:
                return f"{key} is above its maximum"
        if isinstance(value, str):
            if "minLength" in rule and len(value) < rule["minLength"]:
                return f"{key} is below its minimum length"
            if "maxLength" in rule and len(value) > rule["maxLength"]:
                return f"{key} is above its maximum length"
    return None


def _rpc_result(request_id: Any, result: Any) -> JSONResponse:
    return JSONResponse({"jsonrpc": "2.0", "id": request_id, "result": result})


def _rpc_error(request_id: Any, code: int, message: str) -> JSONResponse:
    return JSONResponse(
        {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
    )


def build_mcp_router(core_getter: Callable[[], Any], token: str) -> APIRouter:
    router = APIRouter()

    @router.post("/mcp")
    async def streamable_http(request: Request) -> Response:
        if not token:
            return _rpc_error(None, -32001, "MCP is disabled: BRIGHT_MCP_TOKEN is unset")
        supplied = request.headers.get("authorization", "")
        expected = f"Bearer {token}"
        if not hmac.compare_digest(supplied.encode(), expected.encode()):
            return JSONResponse({"error": "unauthorized"}, status_code=401)
        try:
            payload = await request.json()
        except Exception:
            return _rpc_error(None, -32700, "Parse error")
        if not isinstance(payload, dict) or payload.get("jsonrpc") != "2.0":
            return _rpc_error(payload.get("id") if isinstance(payload, dict) else None, -32600, "Invalid Request")

        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params") or {}
        if method == "notifications/initialized":
            return Response(status_code=202)
        if method == "initialize":
            requested = str(params.get("protocolVersion") or PROTOCOL_VERSION)
            version = requested if requested in {"2024-11-05", "2025-03-26", PROTOCOL_VERSION} else PROTOCOL_VERSION
            return _rpc_result(
                request_id,
                {
                    "protocolVersion": version,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "bright-classroom-core", "version": "2.0.0"},
                },
            )
        if method == "ping":
            return _rpc_result(request_id, {})
        if method == "tools/list":
            return _rpc_result(request_id, {"tools": list(TOOLS)})
        if method == "tools/call":
            if not isinstance(params, dict):
                return _rpc_error(request_id, -32602, "Invalid params")
            name = params.get("name")
            arguments = params.get("arguments") or {}
            if name not in TOOLS_BY_NAME or not isinstance(arguments, dict):
                return _rpc_error(request_id, -32602, "Unknown tool or invalid arguments")
            invalid = _validate_arguments(TOOLS_BY_NAME[str(name)], arguments)
            if invalid:
                return _rpc_error(request_id, -32602, invalid)
            try:
                result = await core_getter().turn_registry.invoke(str(name), arguments)
            except TurnRejected as exc:
                result = {"ok": False, "reason": str(exc)}
            except Exception as exc:  # fail closed at the protocol boundary
                result = {"ok": False, "reason": f"tool failed: {type(exc).__name__}"}
            ok = not isinstance(result, dict) or result.get("ok") is not False
            return _rpc_result(
                request_id,
                {
                    "content": [{"type": "text", "text": json.dumps(result, separators=(",", ":"))}],
                    "structuredContent": result,
                    "isError": not ok,
                },
            )
        return _rpc_error(request_id, -32601, "Method not found")

    return router


__all__ = ["TurnRegistry", "TurnRejected", "TOOLS", "build_mcp_router"]
