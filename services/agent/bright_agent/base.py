"""The `TeacherAgent` seam.

This module is the entire insurance policy for the offline promise
(docs/archive/phase-1-plan.md §3). Everything model-related goes through
`TeacherAgent`. Swapping remote MiMo for a local model, or for Hermes,
must be a config change plus one class — never a refactor.

Keep this file implementation-agnostic: no httpx, no OpenAI vocabulary,
no classroom-core imports.
"""

from __future__ import annotations

from typing import Annotated, Any, AsyncIterator, Literal, Protocol, Union, runtime_checkable

from bright_contracts import ActPayload, TurnContext
from pydantic import BaseModel, Field

# --------------------------------------------------------------- events


class TurnUsage(BaseModel):
    """Token accounting for one `turn()`. Summed across tool-loop rounds."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    cached_tokens: int = 0
    total_tokens: int = 0
    rounds: int = 0

    def add(self, other: "TurnUsage") -> "TurnUsage":
        return TurnUsage(
            prompt_tokens=self.prompt_tokens + other.prompt_tokens,
            completion_tokens=self.completion_tokens + other.completion_tokens,
            cached_tokens=self.cached_tokens + other.cached_tokens,
            total_tokens=self.total_tokens + other.total_tokens,
            rounds=self.rounds + other.rounds,
        )


class TextDelta(BaseModel):
    """A chunk of teacher speech. May contain inline `<|ACT ...|>` tokens."""

    type: Literal["text_delta"] = "text_delta"
    text: str


class Act(BaseModel):
    """An out-of-band emotion/motion cue.

    Consumers that own the text stream should prefer the inline
    `<|ACT|>` token (PROTOCOL.md §5) so it stays ordered against audio;
    this event exists for consumers that do not parse text.
    """

    type: Literal["act"] = "act"
    act: ActPayload
    inline: str = ""  # the exact token that was (or would be) emitted inline


class ToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    call_id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolResult(BaseModel):
    type: Literal["tool_result"] = "tool_result"
    call_id: str
    name: str
    ok: bool
    result: Any = None
    error: str | None = None


DoneReason = Literal["complete", "no_action", "error"]


class Done(BaseModel):
    """Terminal event. Exactly one is emitted per `turn()`.

    `reason`:
      complete   — the model chose an action and/or spoke; core may apply it
      no_action  — the model produced nothing actionable; core continues the
                   lesson_run as if the agent were absent
      error      — anything failed. Core falls back to the lesson_run default.
                   **Never retried in front of a class** (docs/design/architecture.md §3).
    """

    type: Literal["done"] = "done"
    reason: DoneReason
    detail: str | None = None
    usage: TurnUsage = Field(default_factory=TurnUsage)


# Discriminated on `type` so consumers can parse an event off the wire with
# `TypeAdapter(AgentEvent).validate_python(...)`.
AgentEvent = Annotated[
    Union[TextDelta, Act, ToolCall, ToolResult, Done],
    Field(discriminator="type"),
]


# ---------------------------------------------------------------- agent


@runtime_checkable
class TeacherAgent(Protocol):
    """The one interface classroom-core knows about.

    Implementations: `DirectAgent` (Phase 1, OpenAI-compatible HTTP),
    `HermesAgent` (Phase 2), `LocalAgent` (Phase 3, same as DirectAgent
    with `base_url` pointed at OVMS / llama.cpp).

    Contract:
      * `turn()` yields events and always terminates with exactly one `Done`.
      * It never raises for an operational failure — failures become
        `Done(reason="error")`. A raise means a programming bug.
      * It performs at most one attempt per tool call. No retry loops.
      * It does not mutate classroom state; execution is delegated to the
        injected `ToolExecutor` owned by classroom-core.
    """

    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]:
        ...


__all__ = [
    "TurnUsage",
    "TextDelta",
    "Act",
    "ToolCall",
    "ToolResult",
    "Done",
    "DoneReason",
    "AgentEvent",
    "TeacherAgent",
]
