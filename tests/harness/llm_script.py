"""Builders for the scripted model's SSE output.

Kept separate from the server so a test reads as a sentence: "the model streams
a tool call whose arguments are split here" rather than a wall of chunk dicts.
"""

from __future__ import annotations

import json
from typing import Any


def text(*parts: str, finish: str = "stop") -> dict[str, Any]:
    """Plain content deltas, one SSE frame per part."""
    return {"chunks": [{"content": p} for p in parts], "finish": finish}


def split_text(body: str, at: int, finish: str = "stop") -> dict[str, Any]:
    """The same string, cut in two and sent as two separate SSE frames.

    Cutting *inside* an `<|ACT …|>` token is the whole point of I6: the two
    halves are physically in different frames on the wire, so a parser without
    tail retention sees `…<|A` and has to decide what to do with it.
    """
    return text(body[:at], body[at:], finish=finish)


def tool_call(
    name: str,
    arguments: dict[str, Any],
    *,
    call_id: str = "call_1",
    split_args_at: int | None = None,
    preamble: list[str] | None = None,
) -> dict[str, Any]:
    """One streamed tool call, optionally with its JSON arguments fragmented."""
    raw = json.dumps(arguments)
    chunks: list[dict[str, Any]] = [{"content": p} for p in (preamble or [])]
    if split_args_at is None:
        chunks.append({"tool": {"index": 0, "id": call_id, "name": name, "args": raw}})
    else:
        chunks.append({"tool": {"index": 0, "id": call_id, "name": name, "args": raw[:split_args_at]}})
        chunks.append({"tool": {"index": 0, "args": raw[split_args_at:]}})
    return {"chunks": chunks, "finish": "tool_calls"}


def hang() -> dict[str, Any]:
    """Accept the request and never answer it — an unplugged network."""
    return {"mode": "hang"}


def http_error(status: int = 500, message: str = "upstream exploded") -> dict[str, Any]:
    return {"mode": "error", "status": status, "message": message}


def slow(seconds: float, then: dict[str, Any] | None = None) -> dict[str, Any]:
    response = dict(then or text("ok"))
    response["delay_before_s"] = seconds
    return response
