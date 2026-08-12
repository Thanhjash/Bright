"""Variants — the fallback ladder of architecture.md §3, made measurable.

    Tier A  4 tools + available_actions      <- what ships (`baseline`)
    Tier B  drop to 2-3 tools                <- `lean_tools`
    Tier C  no tool calling at all           <- `tier_c`
    Tier D  no model in the loop             <- not measured; it is the floor

Plus two variants that isolate *why* a number is what it is:

* `static_schema` — the same tool surface, but `action_id` is a plain string
  and the enum lives only in the user message. This is the cache fix from the
  README's weakness #1. Because the enum is what the decoder constrains
  (probe_provider.py), the accuracy delta of this variant is the price of the
  cache win, stated in points.
* `degraded_prompt` — the shipped tool surface with the pedagogy stripped out
  of the system prompt. Stands in for a model that cannot follow a 350-token
  instruction. Together with the weaker model it brackets "how much of this is
  the model".
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from bright_contracts import TurnContext

from bright_agent.prompt import SYSTEM_PROMPT, render_turn
from bright_agent.tools import (
    CHOOSE_NEXT,
    RECORD_OBSERVATION,
    SAY,
    build_tools,
)

Mode = Literal["tools", "json"]


@dataclass(frozen=True)
class Variant:
    name: str
    mode: Mode
    system_prompt: str
    #: None == the shipped `build_tools`.
    tools_builder: Callable[[TurnContext], list[dict[str, Any]]] | None = None
    messages_builder: Callable[[TurnContext], list[dict[str, Any]]] | None = None
    note: str = ""


# ----------------------------------------------------- A: what ships today

BASELINE = Variant(
    "baseline", "tools", SYSTEM_PROMPT,
    note="Tier A: 5 tools, action_id enum inside the tool schema",
)


# ---------------------------------------- static tool block (the cache fix)


def _static_choose_next(ctx: TurnContext) -> dict[str, Any]:
    """`classroom_choose_next` with **no per-turn content**.

    Byte-identical on every turn, so the whole tool block stays in the
    cacheable prefix no matter how `available_actions` moves. The legal ids
    are already listed in the user message; this removes the duplicate.
    """
    return {
        "type": "function",
        "function": {
            "name": CHOOSE_NEXT,
            "description": "Choose exactly ONE action from the ACTIONS list. This ends your turn.",
            "parameters": {
                "type": "object",
                "properties": {
                    "state_version": {
                        "type": "integer",
                        "description": "Must equal the state_version shown in ACTIONS.",
                    },
                    # No enum. This is the entire difference from baseline.
                    "action_id": {
                        "type": "string",
                        "description": "One of the listed action ids, copied exactly.",
                    },
                    "params": {"type": "object", "additionalProperties": True},
                },
                "required": ["state_version", "action_id"],
                "additionalProperties": False,
            },
        },
    }


def _static_tools(ctx: TurnContext) -> list[dict[str, Any]]:
    tools = build_tools(ctx, include_recall=True)
    return [t for t in tools if t["function"]["name"] != CHOOSE_NEXT] + (
        [_static_choose_next(ctx)] if ctx.available_actions else []
    )


STATIC_SCHEMA = Variant(
    "static_schema", "tools", SYSTEM_PROMPT, tools_builder=_static_tools,
    note="baseline with the volatile enum lifted out of the tool block",
)


# ------------------------------------------------------- B: fewer tools


def _lean_tools(ctx: TurnContext) -> list[dict[str, Any]]:
    """Tier B: say + record_observation + choose_next.

    `classroom_get_state` is dropped because the turn context already carries
    the state, and `classroom_recall` because memory is pushed in by core.
    """
    keep = {SAY, RECORD_OBSERVATION, CHOOSE_NEXT}
    return [t for t in build_tools(ctx, include_recall=False) if t["function"]["name"] in keep]


LEAN_TOOLS = Variant(
    "lean_tools", "tools", SYSTEM_PROMPT, tools_builder=_lean_tools,
    note="Tier B: 3 tools; get_state and recall removed",
)


# --------------------------------------------------- C: no tool block at all

TIER_C_SYSTEM = (
    SYSTEM_PROMPT
    + """

OUTPUT FORMAT - you do not have tools. Reply with ONE JSON object and nothing else:
{"say": "<1-2 short sentences>", "action_id": "<exact id from ACTIONS>", "state_version": <the number in ACTIONS>,
 "observation": {"student_id": "...", "skill": "...", "result": "correct|near|wrong|silence", "evidence": "..."}}
"observation" is optional; omit it unless a named student showed something.
If ACTIONS lists none, omit "action_id" and "state_version"."""
)


def _tier_c_messages(ctx: TurnContext) -> list[dict[str, str]]:
    return [
        {"role": "system", "content": TIER_C_SYSTEM},
        {"role": "user", "content": render_turn(ctx)},
    ]


TIER_C = Variant(
    "tier_c", "json", TIER_C_SYSTEM,
    # An empty tool list means `build_request_body` omits `tools` entirely --
    # the whole ~650-token block disappears from the prompt.
    tools_builder=lambda ctx: [],
    messages_builder=_tier_c_messages,
    note="Tier C: no tools; one constrained JSON completion, parsed by us",
)


# ----------------------------------------------------- the degraded prompt

DEGRADED_SYSTEM = """\
You are a teacher of an English class in Vietnam. Pick one action and speak briefly."""

DEGRADED_PROMPT = Variant(
    "degraded_prompt", "tools", DEGRADED_SYSTEM,
    note="shipped tools, ~20-token system prompt: what the design is worth without the pedagogy",
)


# ------------------------------------------------- combined optimum (built later)


def _lean_static_tools(ctx: TurnContext) -> list[dict[str, Any]]:
    keep = {SAY, RECORD_OBSERVATION, CHOOSE_NEXT}
    base = [t for t in build_tools(ctx, include_recall=False) if t["function"]["name"] in keep]
    return [t for t in base if t["function"]["name"] != CHOOSE_NEXT] + (
        [_static_choose_next(ctx)] if ctx.available_actions else []
    )


LEAN_STATIC = Variant(
    "lean_static", "tools", SYSTEM_PROMPT, tools_builder=_lean_static_tools,
    note="lean_tools + static_schema: the maximum-cache, minimum-token tool variant",
)


ALL: dict[str, Variant] = {
    v.name: v
    for v in (BASELINE, STATIC_SCHEMA, LEAN_TOOLS, LEAN_STATIC, TIER_C, DEGRADED_PROMPT)
}

#: What a plain `python -m evals` runs.
DEFAULT_VARIANTS = ("baseline",)


def get(name: str) -> Variant:
    if name not in ALL:
        raise KeyError(f"unknown variant {name!r}; have {sorted(ALL)}")
    return ALL[name]


# ------------------------------------------------------- Tier C parsing


def parse_tier_c(text: str) -> tuple[dict[str, Any] | None, str | None]:
    """Pull the JSON object out of a Tier C completion.

    Tolerant of a ```json fence and of leading prose, because without a tool
    protocol there is nothing forcing the model to emit bare JSON — and
    `response_format` is not enforced on this endpoint (probe_provider.py).
    Returns (obj, error).
    """
    s = text.strip()
    if s.startswith("```"):
        s = s.split("\n", 1)[-1] if "\n" in s else s
        s = s.rsplit("```", 1)[0]
    start, depth, in_str, esc = s.find("{"), 0, False, False
    if start < 0:
        return None, "no JSON object in the completion"
    for i in range(start, len(s)):
        c = s[i]
        if esc:
            esc = False
            continue
        if c == "\\":
            esc = True
            continue
        if c == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                try:
                    obj = json.loads(s[start : i + 1])
                except json.JSONDecodeError as exc:
                    return None, f"undecodable JSON: {exc}"
                return (obj, None) if isinstance(obj, dict) else (None, "JSON was not an object")
    return None, "unterminated JSON object"


__all__ = ["Variant", "ALL", "DEFAULT_VARIANTS", "get", "parse_tier_c", "TIER_C_SYSTEM"]
