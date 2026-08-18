"""The five tools the model may call, and the executor seam.

docs/archive/phase-1-plan.md §4 · docs/design/architecture.md-architecture.md §3 · NS-3.

Design rule (do not "improve" this): the agent **proposes within a
constrained option set**; it does not compose from a large primitive
vocabulary. `action_id` is a per-turn string enum built from
`ctx.available_actions`, so an invalid id is not merely discouraged —
with a provider that honours enums it is unrepresentable.

This module does NOT import classroom-core. Execution is delegated to an
injected `ToolExecutor`; that callable is the entire boundary.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from bright_contracts import TurnContext

# Names are stable across turns — only `choose_next`'s enum is volatile.
GET_STATE = "classroom_get_state"
CHOOSE_NEXT = "classroom_choose_next"
SAY = "classroom_say"
RECORD_OBSERVATION = "classroom_record_observation"
RECALL = "classroom_recall"

TOOL_NAMES = (GET_STATE, CHOOSE_NEXT, SAY, RECORD_OBSERVATION, RECALL)

#: Tools that end the turn once they succeed. The model picks ONE action.
TERMINAL_TOOLS = (CHOOSE_NEXT,)

#: Tools whose result signals a graded outcome (drives emotion, see act.py).
GRADING_TOOLS = (RECORD_OBSERVATION,)


# ------------------------------------------------------------- the seam


@runtime_checkable
class ToolExecutor(Protocol):
    """Injected by classroom-core. The only way the agent touches the world.

    Implementations must:
      * be idempotent enough to survive a duplicate call,
      * raise on failure (the agent converts a raise into a single
        `ToolResult(ok=False)` and then `Done(reason="error")` — it never
        retries),
      * return JSON-serialisable data.

    `classroom_choose_next` is validated by `validation.py` *before* it
    reaches here, so an executor never sees an illegal action_id or a
    stale state_version from this agent.
    """

    async def __call__(self, name: str, arguments: dict[str, Any]) -> Any:
        ...


# ------------------------------------------------------------- schemas


def _choose_next_schema(ctx: TurnContext) -> dict[str, Any]:
    action_ids = [a.id for a in ctx.available_actions]
    param_names = sorted({p for a in ctx.available_actions for p in (a.params or [])})
    params_desc = (
        "Extra arguments required by some actions: " + ", ".join(param_names)
        if param_names
        else "Usually omitted."
    )
    return {
        "type": "function",
        "function": {
            "name": CHOOSE_NEXT,
            # Labels live in the user message (prompt.render_turn), not here:
            # this description is inside the volatile tool block, and every
            # byte of it costs prompt cache on the turns where actions change.
            "description": "Choose exactly ONE action from the ACTIONS list. This ends your turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state_version": {
                        "type": "integer",
                        "description": (
                            "Must equal the state_version shown in this turn's "
                            f"context ({ctx.state_version}). A stale value is rejected."
                        ),
                    },
                    "action_id": {
                        "type": "string",
                        # The whole point of the design. Populated per turn.
                        "enum": action_ids,
                        "description": "One of the listed action ids. Nothing else is legal.",
                    },
                    "params": {
                        "type": "object",
                        "description": params_desc,
                        "additionalProperties": True,
                    },
                },
                "required": ["state_version", "action_id"],
                "additionalProperties": False,
            },
        },
    }


_GET_STATE_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": GET_STATE,
        "description": (
            "Re-read the classroom state and the currently legal actions. "
            "You already have this turn's state; call only if you think it moved."
        ),
        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
    },
}

_SAY_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": SAY,
        "description": (
            "Speak to the class. The only free-text channel. Keep it to one or "
            "two short sentences. May contain inline <|ACT {...}|> tokens."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "What the teacher says out loud."},
                "style": {
                    "type": "string",
                    "enum": ["neutral", "warm", "encouraging", "slow", "playful"],
                    "description": "Delivery hint for TTS. Optional.",
                },
            },
            "required": ["text"],
            "additionalProperties": False,
        },
    },
}

_RECORD_OBSERVATION_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RECORD_OBSERVATION,
        "description": (
            "Record what a student just demonstrated. The only write into "
            "student state. One skill per call."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "student_id": {"type": "string"},
                "skill": {
                    "type": "string",
                    "description": "Short snake_case skill key, e.g. food_vocab, polite_request.",
                },
                "result": {"type": "string", "enum": ["correct", "near", "wrong", "silence"]},
                "evidence": {
                    "type": "string",
                    "description": "One short sentence of what actually happened.",
                },
            },
            "required": ["student_id", "skill", "result", "evidence"],
            "additionalProperties": False,
        },
    },
}

_RECALL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": RECALL,
        "description": (
            "Search past observations and session summaries for this class. "
            "Use when you need history you were not given."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "k": {"type": "integer", "minimum": 1, "maximum": 10, "default": 3},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
}


def build_tools(ctx: TurnContext, *, include_recall: bool = True) -> list[dict[str, Any]]:
    """Build the per-turn tool list.

    Only `classroom_choose_next` varies between turns (its `action_id`
    enum). Keep the stable ones first so as much of the serialised prompt
    prefix as possible stays cacheable.

    If `ctx.available_actions` is empty, `choose_next` is omitted entirely
    rather than offered with an empty enum — an empty enum is a decoder
    trap.
    """
    tools: list[dict[str, Any]] = [_GET_STATE_SCHEMA, _SAY_SCHEMA, _RECORD_OBSERVATION_SCHEMA]
    if include_recall:
        tools.append(_RECALL_SCHEMA)
    if ctx.available_actions:
        tools.append(_choose_next_schema(ctx))
    return tools


__all__ = [
    "GET_STATE",
    "CHOOSE_NEXT",
    "SAY",
    "RECORD_OBSERVATION",
    "RECALL",
    "TOOL_NAMES",
    "TERMINAL_TOOLS",
    "GRADING_TOOLS",
    "ToolExecutor",
    "build_tools",
]
