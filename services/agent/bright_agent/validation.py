"""Hard guards on what the model is allowed to propose.

docs/design/architecture.md-architecture.md §3 — "Three hard rules for the tool layer" and
"One thing Hermes does that we must disable".

Two rules, both absolute:

1. A tool call that fails validation is **rejected, not repaired**.
   There is no retry, no reprompt, no second attempt. The turn ends with
   `Done(reason="error")` and classroom-core falls back to the
   `lesson_run` default. Thirty children are waiting.

2. Every rejection is logged as one structured record, with enough
   detail to replay it in an eval later. `REJECTION_LOG` keeps the
   in-process history so a test or the background summariser can read it
   without scraping logs.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Literal

from bright_contracts import TurnContext
from pydantic import BaseModel, Field

from .tools import CHOOSE_NEXT, RECORD_OBSERVATION, SAY, TOOL_NAMES

log = logging.getLogger("bright.agent.validation")

RejectionCode = Literal[
    "unknown_tool",
    "bad_arguments",
    "unknown_action_id",
    "stale_state_version",
    "missing_field",
    "empty_text",
    "no_available_actions",
]


class Rejection(BaseModel):
    """One refused proposal. This is eval material — keep it complete."""

    code: RejectionCode
    tool: str
    detail: str
    ts: float = Field(default_factory=time.time)
    # Everything needed to replay the decision offline:
    arguments: dict[str, Any] = Field(default_factory=dict)
    available_action_ids: list[str] = Field(default_factory=list)
    ctx_state_version: int | None = None
    lesson_id: str | None = None
    activity_index: int | None = None
    student_id: str | None = None

    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return f"{self.code}: {self.tool} — {self.detail}"


#: Bounded in-process ring of rejections. Read it in tests; ship it to the
#: eval set from classroom-core if you want durability.
REJECTION_LOG: list[Rejection] = []
_MAX_LOG = 500


def record_rejection(r: Rejection) -> Rejection:
    REJECTION_LOG.append(r)
    if len(REJECTION_LOG) > _MAX_LOG:
        del REJECTION_LOG[: len(REJECTION_LOG) - _MAX_LOG]
    log.warning(
        "agent proposal rejected code=%s tool=%s detail=%s args=%s "
        "available=%s ctx_state_version=%s lesson=%s activity=%s",
        r.code,
        r.tool,
        r.detail,
        r.arguments,
        r.available_action_ids,
        r.ctx_state_version,
        r.lesson_id,
        r.activity_index,
    )
    return r


def _reject(
    ctx: TurnContext,
    tool: str,
    args: dict[str, Any],
    code: RejectionCode,
    detail: str,
) -> Rejection:
    return record_rejection(
        Rejection(
            code=code,
            tool=tool,
            detail=detail,
            arguments=args,
            available_action_ids=[a.id for a in ctx.available_actions],
            ctx_state_version=ctx.state_version,
            lesson_id=ctx.lesson.lesson_id,
            activity_index=ctx.lesson.activity_index,
            student_id=ctx.student.id if ctx.student else None,
        )
    )


def validate_call(
    ctx: TurnContext, name: str, args: dict[str, Any]
) -> Rejection | None:
    """Validate one proposed tool call against this turn's context.

    Returns `None` if the call may be executed, otherwise a `Rejection`
    (already logged). Runs entirely inside the agent process — an illegal
    call never reaches the `ToolExecutor`.
    """
    if name not in TOOL_NAMES:
        return _reject(ctx, name, args, "unknown_tool", f"{name!r} is not one of {list(TOOL_NAMES)}")

    if not isinstance(args, dict):  # defensive: malformed JSON args
        return _reject(ctx, name, {}, "bad_arguments", "arguments did not parse to an object")

    if name == CHOOSE_NEXT:
        return _validate_choose_next(ctx, args)

    if name == SAY:
        text = args.get("text")
        if not isinstance(text, str) or not text.strip():
            return _reject(ctx, name, args, "empty_text", "classroom_say requires non-empty text")
        return None

    if name == RECORD_OBSERVATION:
        for field in ("student_id", "skill", "result", "evidence"):
            if not args.get(field):
                return _reject(ctx, name, args, "missing_field", f"missing {field!r}")
        if args["result"] not in ("correct", "near", "wrong", "silence"):
            return _reject(
                ctx, name, args, "bad_arguments", f"result={args['result']!r} is not a legal outcome"
            )
        return None

    # get_state / recall carry no state-mutating risk.
    return None


def _validate_choose_next(ctx: TurnContext, args: dict[str, Any]) -> Rejection | None:
    legal = {a.id for a in ctx.available_actions}
    if not legal:
        return _reject(
            ctx, CHOOSE_NEXT, args, "no_available_actions",
            "the model proposed an action but core offered none this turn",
        )

    action_id = args.get("action_id")
    if not isinstance(action_id, str) or not action_id:
        return _reject(ctx, CHOOSE_NEXT, args, "missing_field", "missing 'action_id'")
    if action_id not in legal:
        return _reject(
            ctx, CHOOSE_NEXT, args, "unknown_action_id",
            f"action_id={action_id!r} not in available_actions {sorted(legal)}",
        )

    if "state_version" not in args:
        return _reject(ctx, CHOOSE_NEXT, args, "missing_field", "missing 'state_version'")
    raw = args["state_version"]
    try:
        sv = int(raw)
    except (TypeError, ValueError):
        return _reject(
            ctx, CHOOSE_NEXT, args, "bad_arguments", f"state_version={raw!r} is not an integer"
        )
    if sv != ctx.state_version:
        # Anything other than an exact match is stale-or-invented. The board
        # has moved on; applying it would act on a screen that no longer exists.
        return _reject(
            ctx, CHOOSE_NEXT, args, "stale_state_version",
            f"state_version={sv} but the turn context is at {ctx.state_version}",
        )

    params = args.get("params")
    if params is not None and not isinstance(params, dict):
        return _reject(ctx, CHOOSE_NEXT, args, "bad_arguments", "params must be an object")

    action = next(a for a in ctx.available_actions if a.id == action_id)
    for required in action.params or []:
        if not (params or {}).get(required):
            return _reject(
                ctx, CHOOSE_NEXT, args, "missing_field",
                f"action {action_id!r} requires params.{required}",
            )
    return None


__all__ = [
    "Rejection",
    "RejectionCode",
    "REJECTION_LOG",
    "record_rejection",
    "validate_call",
]
