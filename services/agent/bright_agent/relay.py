"""A brain that is a person, reached through two files.

NS-4 says the runtime is replaceable and the contract is not. This is another
runtime: it satisfies `TeacherAgent` exactly, and Core cannot tell the
difference. What is on the other side of it is not a model -- it is whoever is
reading `turn.json` and writing `moves.json`.

Why it exists, and why it is not the cassette this repo deleted:

  * A cassette is authored BEFORE the lesson and replayed regardless of what
    the class does. Here every move is written AFTER reading that turn's own
    input -- the child's actual words, the board, the evidence so far. Nothing
    is pre-recorded, and nothing repeats.
  * It is how you author and debug a lesson without spending model quota, and
    how you demonstrate the room when the network is dead -- which, in the
    deployment this is built for, is most days.
  * It is the only honest way to answer "can the room carry a whole interactive
    period?" separately from "is this particular model good enough to teach?"
    Those are different questions and they fail differently.

Never reachable by accident: `BRIGHT_AGENT=relay` has to be set on purpose, and
`run_profile=ideal_hosted` refuses it.

Protocol, one file each way, in `BRIGHT_RELAY_DIR`:

    turn.json    Core writes: {turn_id, input, waiting_since}
    moves.json   you write:   {turn_id, calls: [{name, arguments}, ...]}

`say` is terminal, exactly as it is for the model. Core executes the calls in
the order given, so the board lands before the voice.
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, AsyncIterator

from bright_contracts import TurnContext

from .base import AgentEvent, Done, ToolCall, ToolResult, TurnUsage
from .hermes import TEACHER_TOOLS, render_teacher_turn

# A person reads and types. That is slower than a model and must not be
# mistaken for a hang -- but it still ends, so a forgotten relay cannot wedge
# the room for ever.
WAIT_TIMEOUT_S = float(os.environ.get("BRIGHT_RELAY_TIMEOUT_S", "900"))
POLL_S = 0.4


class RelayAgent:
    """`TeacherAgent`, with a human where the model goes."""

    streams_text_as_voice = True
    supports_background_complete = False
    # Hermes executes tools server-side over MCP; this one executes in-process,
    # so Core hands it the same executor it gave the turn registry. Declared
    # rather than assumed, so the seam is greppable from both sides.
    wants_executor = True

    def __init__(self, executor: Any = None, directory: str | None = None) -> None:
        self.executor = executor
        self.dir = Path(directory or os.environ.get("BRIGHT_RELAY_DIR")
                        or ".runtime/teacher-agent/relay")
        self.dir.mkdir(parents=True, exist_ok=True)
        self.turn_id = ""

    def prepare_turn(self, turn_id: str) -> None:
        self.turn_id = turn_id

    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]:
        turn_id = self.turn_id or f"relay-{int(time.time())}"
        started = time.time()
        ask = self.dir / "turn.json"
        answer = self.dir / "moves.json"
        answer.unlink(missing_ok=True)
        ask.write_text(
            json.dumps(
                {
                    "turn_id": turn_id,
                    "waiting_since": time.strftime("%H:%M:%S"),
                    "input": render_teacher_turn(ctx, turn_id),
                },
                ensure_ascii=False,
                indent=1,
            ),
            encoding="utf-8",
        )

        calls = await self._await_moves(answer, turn_id)
        if calls is None:
            yield Done(reason="error", detail="relay produced no moves in time",
                       usage=TurnUsage(), elapsed_s=time.time() - started)
            return

        said = False
        for index, call in enumerate(calls):
            name = str(call.get("name") or "")
            arguments = dict(call.get("arguments") or {})
            if name not in TEACHER_TOOLS:
                yield Done(reason="error", detail=f"relay called forbidden tool {name!r}",
                           usage=TurnUsage(), elapsed_s=time.time() - started)
                return
            arguments["turn_id"] = turn_id
            call_id = f"{turn_id}-{index}"
            yield ToolCall(call_id=call_id, name=name, arguments=arguments)
            try:
                result = await self.executor(name, arguments)
            except Exception as exc:  # noqa: BLE001 -- an operational failure is Done, not a raise
                yield ToolResult(call_id=call_id, name=name, ok=False, error=repr(exc)[:200])
                continue
            ok = not (isinstance(result, dict) and result.get("ok") is False)
            yield ToolResult(
                call_id=call_id, name=name, ok=ok,
                result=result if ok else None,
                error=None if ok else str((result or {}).get("reason"))[:200],
            )
            if name == "say" and ok:
                said = True

        yield Done(
            reason="complete" if said else "no_action",
            detail=None if said else "relay never said anything",
            usage=TurnUsage(rounds=1),
            elapsed_s=time.time() - started,
        )

    async def _await_moves(self, answer: Path, turn_id: str) -> list[dict] | None:
        deadline = time.time() + WAIT_TIMEOUT_S
        while time.time() < deadline:
            if answer.exists():
                try:
                    body = json.loads(answer.read_text(encoding="utf-8"))
                except json.JSONDecodeError:
                    await asyncio.sleep(POLL_S)  # still being written
                    continue
                # A stale answer from the previous turn is not an answer.
                if str(body.get("turn_id") or "") == turn_id:
                    answer.unlink(missing_ok=True)
                    return list(body.get("calls") or [])
            await asyncio.sleep(POLL_S)
        return None
