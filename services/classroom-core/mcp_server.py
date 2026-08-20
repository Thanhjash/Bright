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
MUTATING_TOOLS = frozenset({
    "call_the_adult",
    "plan",
    "write_board",
    "show_image",
    "show_exercise",
    "play_clip",
    "say",
    "record_evidence",
})


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
        # A turn is scoped to the session and the learner it was opened for.
        # The activity/generation fields survive from the retired lesson-graph
        # player: they stay on the entry so the wire shape does not move, and
        # they are simply unset now that nothing walks a graph.
        entry = TurnEntry(
            turn_id=turn_id,
            executor=executor,
            expires_at=time.monotonic() + (ttl_s or self.default_ttl_s),
            state_version=int(self.core.store.state_version),
            decision_revision=int(getattr(self.core.store, "decision_revision", 0)),
            session_id=getattr(self.core, "session_id", None),
            activity_id=None,
            activity_generation=None,
            response_turn_id=None,
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
        if int(getattr(self.core.store, "decision_revision", 0)) != entry.decision_revision:
            raise TurnRejected("turn decision_revision is stale")
        if getattr(self.core, "session_id", None) != entry.session_id:
            raise TurnRejected("turn session is stale")
        if getattr(self.core, "student_id", None) != entry.student_id:
            # Single-learner scope. When evidence gains a subject (see the
            # roadmap in docs/STATE.md), attribution binds per response and this
            # process-level check stops being the authority.
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


# Order matters: a model reads tools/list as a narrative. Look things up,
# then change the room, and `say` LAST because it is the terminal tool --
# the turn ends when she speaks. record_evidence used to sit after it,
# which read as "there is something to do after you finish".
TOOLS: tuple[dict[str, Any], ...] = (
    {
        "name": "read_library",
        "description": (
            "Read one markdown file from the curriculum library. `path` is required "
            "and is a path relative to the library root, exactly as READ_NOW spells "
            "it, e.g. 'how-to-teach.md' or 'units/<unit>/map.md'."
        ),
        "inputSchema": _schema(
            {"path": {"type": "string", "minLength": 1, "maxLength": 256}},
            ["path"],
        ),
    },
    {
        "name": "search_library",
        "description": "Search markdown under the curriculum library. Returns paths, snippets, asset:// ids.",
        "inputSchema": _schema(
            {"query": {"type": "string", "minLength": 1, "maxLength": 256}},
            ["query"],
        ),
    },
    {
        "name": "recall_student",
        # The twelfth tool. docs/decisions/2026-08-20-the-room-knows-who.md.
        #
        # db.recall() -- FTS5 over memories_fts, bm25 re-weighted by recency --
        # has existed for days, reachable from a dev HTTP route and from nothing
        # she could call. A memory the teacher cannot query is a memory the
        # teacher does not have.
        #
        # There is no student_id argument ON PURPOSE. The subject is the learner
        # Core opened the session for; she cannot ask about another child
        # because the id is not hers to supply.
        "description": (
            "Look further into THIS learner's own record when SKILL_CARD and "
            "PAST are not enough -- what they were like on an earlier day, "
            "whether something has come up before. Returns notes Core wrote, "
            "most useful first. Finding nothing is normal: a child on their "
            "first day has no past, and you teach them anyway."
        ),
        "inputSchema": _schema(
            {
                "query": {
                    "type": "string",
                    "minLength": 2,
                    "description": "What you are looking for, e.g. an objective id or a word.",
                },
                "limit": {"type": "integer", "minimum": 1, "maximum": 8},
            },
            ["query"],
        ),
    },
    {
        "name": "read_board",
        "description": "See what is currently on the board: writing, pictures, and the last clip.",
        "inputSchema": _schema({}, []),
    },
    {
        "name": "write_board",
        "description": (
            "Put writing on the board FIRST, then talk about what is up there. "
            "To chalk while you speak instead, use say(board_text) -- same board, "
            "same limits, different moment. "
            "Only these draw as chalk: `#`, `##` or `###` headings; `-` or `1.` "
            "list items, with a space after the marker; **bold** and *italic*. "
            "Anything else prints as literal punctuation on the projector. "
            "Max 400 characters, 8 lines. No HTML or URLs. "
            "Usually called in the same message as say."
        ),
        "inputSchema": _schema(
            {"text": {"type": "string", "minLength": 1, "maxLength": 400}},
            ["text"],
        ),
    },
    {
        "name": "show_image",
        # Every argument used to be optional, so show_image({turn_id}) passed
        # validation and only failed at execute -- a wasted round-trip a child
        # waits through, handed free to any model that guesses. The picture is
        # the point of the tool: make it required, and make the pair case one
        # extra field instead of a second, invisible calling convention.
        "description": (
            "Put a picture on the board. `asset` is required and must be an "
            "asset:// id from the unit files. Add `second` only to stand two "
            "pictures side by side for a comparison. Usually called in the same "
            "message as say."
        ),
        "inputSchema": _schema(
            {
                "asset": {
                    "type": "string",
                    "minLength": 1,
                    "description": "asset:// id of the picture, from the unit files.",
                },
                "second": {
                    "type": "string",
                    "description": (
                        "asset:// id of a second picture, shown beside the first. "
                        "Omit it for a single picture."
                    ),
                },
            },
            ["asset"],
        ),
    },
    {
"name": "show_exercise",
        # FLAT, and it has to be. `content` used to be {"type": "object"} with
        # no properties. Measured 2026-08-19 against google/gemini-3.7-flash:
        # handed the exact payload verbatim in the prompt and told to send it,
        # the model called this tool with `content: {}` -- empty. A provider
        # translating an untyped object into a function declaration produces a
        # field with nothing in it, so there is nothing for the model to fill.
        #
        # That is exactly how the merged `teach` tool died (`board: {}`), and it
        # is why three separate prompt fixes -- literal examples in this
        # description, READ_NOW naming the skill, a standing line saying
        # announcing a task does not put it on the board -- all failed to
        # produce a single call across four live periods. It was never a
        # prompting problem.
        #
        # Every field is typed and top-level. Core's per-kind validators still
        # decide what each `kind` requires, and still refuse with a reason she
        # can act on -- the requiredness is pedagogy-shaped and stays out of the
        # wire, where a provider would only mangle it.
        "description": (
            "Find out what landed. This is the check after a choral round -- not "
            "a way to display something, which write_board and show_image "
            "already do. Usually called in the same message as say.\n"
            "The unit's exercises.md holds ready-made payloads -- read it and "
            "copy the fields across. Each kind needs different ones:\n"
            "choice: prompt + options (2-4) + correct_id. Add reveal=true only "
            "to show which was right, never who picked what.\n"
            "vocabulary: items (2-8).\n"
            "roleplay: environment + ai_role + student_role + target_phrases (1-5)."
        ),
        "inputSchema": _schema(
            {
                "kind": {
                    "type": "string",
                    "enum": ["choice", "vocabulary", "roleplay"],
                },
                "prompt": {
                    "type": "string",
                    "description": "choice only: the question, e.g. \"Who says hello?\"",
                },
                "options": {
                    "type": "array",
                    "description": (
                        "choice only: 2 to 4 things to pick between. Each needs "
                        "`id` plus `text` or `asset` -- a picture choice carries "
                        "no text at all."
                    ),
                    # `text` is NOT required, and saying it was made the authored
                    # payloads unsendable: ex.4's two items are picture choices,
                    # `id` + `asset` with no text, and both this tool and the
                    # file say to copy a block whole. Following that instruction
                    # produced a call the declared schema forbids -- a provider
                    # that hard-validates `required` rejects it outright, and one
                    # that does not invites the model to invent a caption for a
                    # picture. Same species as the `content: {}` bug: the schema
                    # describing a tool that does not exist.
                    #
                    # The real rule is "id, and at least one of text/asset",
                    # which this subset cannot spell. It stays where the other
                    # pedagogy-shaped requirements already live -- Core's
                    # _clean_media_item, which refuses with a reason she can act
                    # on -- and arrives here as prose.
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "asset": {"type": "string"},
                        },
                        "required": ["id"],
                    },
                },
                "correct_id": {
                    "type": "string",
                    "description": "choice only: the id of the right option.",
                },
                "items": {
                    "type": "array",
                    "description": (
                        "vocabulary only: 2 to 8 cards. Each needs `id` plus "
                        "`text` or `asset` -- a picture card carries no text."
                    ),
                    # Same correction as `options` above, for the same reason.
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "text": {"type": "string"},
                            "asset": {"type": "string"},
                        },
                        "required": ["id"],
                    },
                },
                "environment": {"type": "string", "description": "roleplay only: where it happens."},
                "ai_role": {"type": "string", "description": "roleplay only: who you play."},
                "student_role": {"type": "string", "description": "roleplay only: who they play."},
                "target_phrases": {
                    "type": "array",
                    "description": "roleplay only: 1 to 5 lines to practise.",
                    "items": {"type": "string"},
                },
                "reveal": {
                    "type": "boolean",
                    "description": (
                        "choice only: show which option was correct. Never shows "
                        "who chose what."
                    ),
                },
            },
            ["kind"],
        ),
    },
    {
        "name": "play_clip",
        "description": (
            "Play a short library audio clip. `transcript` is SPOKEN as the "
            "subtitle while it plays -- it does not appear on the board. To put "
            "words on the board, write_board. "
            "Usually called in the same message as say."
        ),
        "inputSchema": _schema(
            {
                "asset": {"type": "string", "minLength": 1, "maxLength": 256},
                "transcript": {"type": "string", "maxLength": 200},
            },
            ["asset"],
        ),
    },
    {
        "name": "plan",
        "description": (
            "Write or revise YOUR plan for this period -- what you mean to do "
            "next and why, in a few short lines. It is yours: the room stores "
            "it and hands it back to you every turn, and nothing in the room "
            "acts on it. Write one early in the period and revise it whenever "
            "the class makes you change your mind. Never a child's words."
        ),
        "inputSchema": _schema(
            {
                "plan": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 1200,
                }
            },
            ["plan"],
        ),
    },
    {
        "name": "record_evidence",
        "description": (
            "Record categorical evidence for exactly one named learner. Never "
            "include the learner's raw words, and never call this for a choral "
            "or unattributable response. "
            "mode is name, point, or ask — not off-topic, and not a substitute for outcome."
        ),
        "inputSchema": _schema(
            {
                "student_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "objective_id": {"type": "string", "minLength": 1, "maxLength": 128},
                "outcome": {
                    "type": "string",
                    "enum": ["correct", "wrong", "uncertain", "near"],
                },
                # "off-topic" was legal in the enum and refused unconditionally
                # in teacher_os -- a schema-legal value that always fails is a
                # landmine for a small model, which trusts an enum over the
                # prose beside it.
                "mode": {
                    "type": "string",
                    "enum": ["name", "point", "ask"],
                },
            },
            ["student_id", "objective_id", "outcome"],
        ),
    },
    {
        "name": "call_the_adult",
        # The eleventh tool, and NS-3 says that needs a decision doc:
        # docs/decisions/2026-08-19-she-can-call-the-adult.md
        #
        # NORTH-STAR §1 has listed five situations since the beginning where she
        # must stop teaching and hand the room over -- danger, a child in
        # distress, a disclosure, broken equipment, a class she cannot reach --
        # and `skills/escalate-to-the-adult/SKILL.md` tells her exactly how. She
        # has never been able to do it: `say` reaches the loudspeaker and the
        # board reaches the projector, and neither reaches the adult. Doctrine
        # with no hand attached is not a safety policy, it is a wish.
        "description": (
            "Stop teaching and hand the room to the adult. Use it for danger, a "
            "child in distress, anything a child discloses that worries you, "
            "equipment you have already retried once, or a class you cannot "
            "reach however you change the pacing. Read "
            "skills/escalate-to-the-adult/SKILL.md first -- it says what to say "
            "to the class while you wait. The adult sees this, the class does "
            "not; keep the class's own language for say."
        ),
        "inputSchema": _schema(
            {
                "reason": {
                    "type": "string",
                    "enum": [
                        "danger",
                        "distress",
                        "disclosure",
                        "equipment",
                        "cannot_reach_the_class",
                    ],
                },
                "detail": {
                    "type": "string",
                    "description": (
                        "One short line for the adult, in the school language, "
                        "saying what to do. Never a child's words, never a name. "
                        "At most 200 characters."
                    ),
                },
            },
            ["reason"],
        ),
    },
    {
        "name": "say",
        "description": "Speak one short non-evaluative teacher sentence to the learner.",
        "inputSchema": _schema(
            {
                "teacher_line": {
                    "type": "string",
                    "minLength": 1,
                    "maxLength": 220,
                },
                "board_text": {
                    "type": "string",
                    "maxLength": 400,
                    "description": (
                        "Chalk this WHILE you speak, in the same breath. Usually NOT "
                        "the same words as teacher_line -- you might say \"look at this "
                        "word together\" and write just the word. To put writing up "
                        "before you talk about it, use write_board instead. Omit it to "
                        "leave the board alone; most lines do not need the board."
                    ),
                },
                "closing": {
                    "type": "boolean",
                    "description": (
                        "True when this line ends the period. Say the goodbye first; "
                        "the room closes the lesson after the class has heard it. A "
                        "teacher ends her own lesson rather than running until "
                        "someone stops her."
                    ),
                },
                "wake_in_s": {
                    # `number`, not `integer`. A model emitting 8.0 -- ordinary
                    # for anything generating JSON -- was rejected at the
                    # protocol layer, which killed the WHOLE say: she went mute
                    # that turn, and because a protocol rejection never reaches
                    # TeacherOS.execute, the census could not see it happen.
                    "type": "number",
                    "description": (
                        "Set this when your next move should happen even if "
                        "nobody speaks -- the next round of a drill, or after a "
                        "clip has finished playing. The room hands you the turn "
                        "about then. About 5 to 180 seconds. Omit it when you "
                        "are only waiting for an answer; use awaiting_answer "
                        "for that."
                    ),
                },
                "awaiting_answer": {
                    "type": "boolean",
                    "description": (
                        "True when this line asks the class for something and you are "
                        "now waiting for them. The room stays quiet a few seconds and "
                        "then wakes you once, instead of leaving a child in silence."
                    ),
                },
            },
            ["teacher_line"],
        ),
    },
)
TOOLS_BY_NAME = {tool["name"]: tool for tool in TOOLS}

# Length bounds are Core's business, not the wire's.
#
# Measured 2026-08-19: the OpenRouter provider serving
# google/gemma-4-26b-a4b-it rejects the whole request with HTTP 422 --
# "mcp__bright_classroom__plan.parameters.properties.plan uses maxLength" --
# and that is the model family that ships to the miniPC. Gemini accepted the
# same schema all day, which is exactly the gate we wrote down after the merged
# `teach` tool failed: a schema feature the development model tolerates is not
# evidence the edge model will.
#
# Core still validates every bound, from these same dicts, in
# _validate_arguments -- so nothing is loosened. What changes is that the model
# is TOLD the limit in prose instead of being sent a keyword its provider may
# refuse. For a small model that is the better channel anyway: a sentence it
# reads beats a constraint it has to infer.
_WIRE_STRIPPED = ("maxLength", "minLength")


def _wire_property(spec: dict[str, Any]) -> dict[str, Any]:
    clean = {k: v for k, v in spec.items() if k not in _WIRE_STRIPPED}
    limit = spec.get("maxLength")
    if limit:
        note = f"At most {limit} characters."
        clean["description"] = (str(clean.get("description") or "").strip() + " " + note).strip()
    return clean


def wire_tools() -> list[dict[str, Any]]:
    """`tools/list` as the provider will accept it."""
    out: list[dict[str, Any]] = []
    for tool in TOOLS:
        schema = tool["inputSchema"]
        out.append(
            {
                **tool,
                "inputSchema": {
                    **schema,
                    "properties": {
                        name: _wire_property(spec)
                        for name, spec in schema["properties"].items()
                    },
                },
            }
        )
    return out


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
    python_types = {"string": str, "integer": int, "number": (int, float), "object": dict}
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
            return _rpc_result(request_id, {"tools": wire_tools()})
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
