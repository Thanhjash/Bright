"""Hermes API adapter for Bright's :class:`TeacherAgent` seam.

Hermes owns its model loop and executes tools server-side through the Bright
classroom MCP server.  This adapter owns only HTTP, Responses SSE parsing and
translation into Bright's implementation-neutral agent events.

The classroom hot path is intentionally stateless at the Hermes Responses
layer (``store: false``).  Classroom Core supplies fresh authoritative state
on every turn, so a cancelled or incomplete Hermes response can never become
the parent of the next turn.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from typing import Any

import httpx
from bright_contracts import TurnContext

from .act import ActEmitter
from .base import AgentEvent, Done, TextDelta, ToolCall, ToolResult, TurnUsage
from .prompt import SYSTEM_PROMPT, render_turn
from .tools import TOOL_NAMES, ToolExecutor

log = logging.getLogger("bright.agent.hermes")

HERMES_SYSTEM_PROMPT = SYSTEM_PROMPT.replace(
    "- classroom_say is your voice: 1-2 short sentences a beginner can follow. Say something before you act.",
    "- Your plain assistant text is your voice: use 1-2 short sentences a beginner can follow. Never call classroom_say.",
)


class HermesProtocolError(RuntimeError):
    """Hermes returned a malformed or prematurely-ended Responses stream."""


@dataclass(frozen=True, slots=True)
class HermesSSEEvent:
    event: str
    data: dict[str, Any]


@dataclass(slots=True)
class HermesConfig:
    """Connection settings for the local Hermes API sidecar."""

    base_url: str = "http://127.0.0.1:8642"
    api_key: str = ""
    model: str = "bright-classroom"
    request_timeout_s: float = 20.0
    connect_timeout_s: float = 1.0
    session_key: str = ""

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "HermesConfig":
        source: Any = os.environ if env is None else env
        defaults = cls()
        return cls(
            base_url=source.get("HERMES_API_URL", defaults.base_url).rstrip("/"),
            api_key=source.get("HERMES_API_KEY", ""),
            model=source.get("HERMES_API_MODEL", defaults.model),
            request_timeout_s=float(
                source.get("HERMES_API_TIMEOUT_S", defaults.request_timeout_s)
            ),
            connect_timeout_s=float(
                source.get("HERMES_CONNECT_TIMEOUT_S", defaults.connect_timeout_s)
            ),
            session_key=source.get("HERMES_SESSION_KEY", ""),
        )

    @property
    def responses_url(self) -> str:
        return f"{self.base_url}/v1/responses"

    def headers(self) -> dict[str, str]:
        headers = {
            "accept": "text/event-stream",
            "content-type": "application/json",
            "authorization": f"Bearer {self.api_key}",
        }
        if self.session_key:
            headers["X-Hermes-Session-Key"] = self.session_key
        return headers


async def iter_sse_events(lines: AsyncIterable[str]) -> AsyncIterator[HermesSSEEvent]:
    """Parse an SSE line stream without weakening malformed Hermes payloads.

    Comments and unknown fields are legal SSE and ignored.  A dispatched event
    must contain a JSON object; malformed JSON and non-object payloads are
    protocol failures rather than silently disappearing agent output.
    """

    event_name = "message"
    data_lines: list[str] = []

    async def dispatch() -> HermesSSEEvent | None:
        nonlocal event_name, data_lines
        if not data_lines:
            event_name = "message"
            return None
        raw = "\n".join(data_lines)
        current_name = event_name
        event_name = "message"
        data_lines = []
        if raw == "[DONE]":
            return None
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HermesProtocolError(f"invalid SSE JSON for {current_name!r}: {exc}") from exc
        if not isinstance(payload, dict):
            raise HermesProtocolError(f"SSE data for {current_name!r} is not an object")
        wire_type = payload.get("type")
        if isinstance(wire_type, str) and current_name == "message":
            current_name = wire_type
        return HermesSSEEvent(current_name, payload)

    async for line in lines:
        if line == "":
            item = await dispatch()
            if item is not None:
                yield item
            continue
        if line.startswith(":"):
            continue
        field, separator, value = line.partition(":")
        if separator and value.startswith(" "):
            value = value[1:]
        if field == "event":
            event_name = value
        elif field == "data":
            data_lines.append(value)

    item = await dispatch()
    if item is not None:
        yield item


def build_hermes_input(ctx: TurnContext, turn_id: str) -> str:
    """Render one authoritative, self-contained classroom turn."""

    return (
        f"BRIGHT TURN ID: {turn_id}\n"
        "Every classroom MCP call in this turn MUST include this exact turn_id.\n\n"
        f"{render_turn(ctx)}"
    )


def build_hermes_request(
    config: HermesConfig,
    ctx: TurnContext,
    turn_id: str,
    *,
    stream: bool = True,
) -> dict[str, Any]:
    """Build the exact Responses request; kept public for contract tests."""

    return {
        "model": config.model,
        "instructions": HERMES_SYSTEM_PROMPT,
        "input": build_hermes_input(ctx, turn_id),
        "stream": stream,
        "store": False,
    }


def _raw_tool_name(name: str) -> str:
    """Map Hermes' MCP-prefixed wire name back to Bright's stable tool name."""

    for candidate in TOOL_NAMES:
        if name == candidate or name.endswith(f"__{candidate}"):
            return candidate
    return name


def _arguments(item: dict[str, Any]) -> dict[str, Any]:
    raw = item.get("arguments", "{}")
    if isinstance(raw, dict):
        return raw
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError) as exc:
        raise HermesProtocolError(f"invalid function arguments: {raw!r}") from exc
    if not isinstance(value, dict):
        raise HermesProtocolError("function arguments are not an object")
    return value


def _tool_output(item: dict[str, Any]) -> Any:
    output = item.get("output")
    if isinstance(output, list):
        text = "".join(
            str(block.get("text") or "")
            for block in output
            if isinstance(block, dict) and block.get("type") in ("input_text", "output_text")
        )
        if text:
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
    return output


def _usage(response: dict[str, Any]) -> TurnUsage:
    usage = response.get("usage") or {}
    return TurnUsage(
        prompt_tokens=int(usage.get("input_tokens") or 0),
        completion_tokens=int(usage.get("output_tokens") or 0),
        total_tokens=int(usage.get("total_tokens") or 0),
        rounds=1,
    )


class HermesAgent:
    """Bright ``TeacherAgent`` backed by a separately-running Hermes gateway.

    ``executor`` is accepted for factory compatibility with the current Core
    seam, but deliberately unused: Hermes executes classroom tools server-side
    through MCP.  This class itself cannot mutate classroom state.
    """

    # Unlike DirectAgent, its text deltas are the sole adaptive voice source.
    # Core uses this marker to avoid duplicating legacy tool-driven speech.
    streams_text_as_voice = True

    def __init__(
        self,
        executor: ToolExecutor | None = None,
        config: HermesConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.executor = executor
        self.config = config or HermesConfig.from_env()
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                self.config.request_timeout_s,
                connect=self.config.connect_timeout_s,
            )
        )
        self.last_usage = TurnUsage()
        self.last_latency_s = 0.0
        self.last_response_id: str | None = None
        self.last_turn_id: str | None = None
        self._prepared_turn_id: str | None = None

    def prepare_turn(self, turn_id: str) -> None:
        """Accept the one Core-issued capability for the next request.

        Standalone adapter tests may omit this and receive a local random id;
        production Core always prepares and registers the exact same id before
        opening the Hermes stream.
        """
        if not turn_id or self._prepared_turn_id is not None:
            raise RuntimeError("a Hermes turn is already prepared")
        self._prepared_turn_id = turn_id

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    async def __aenter__(self) -> "HermesAgent":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]:
        turn_id = self._prepared_turn_id or f"bright-{uuid.uuid4().hex}"
        self._prepared_turn_id = None
        self.last_turn_id = turn_id
        body = build_hermes_request(self.config, ctx, turn_id)
        started = time.perf_counter()
        usage = TurnUsage()
        response_id: str | None = None
        terminal = False
        produced = False
        calls: dict[str, tuple[str, dict[str, Any]]] = {}
        emitter = ActEmitter()

        try:
            async with self._client.stream(
                "POST",
                self.config.responses_url,
                json=body,
                headers=self.config.headers(),
            ) as response:
                if response.status_code >= 400:
                    detail = (await response.aread())[:400].decode("utf-8", "replace")
                    yield self._done("error", f"HTTP {response.status_code}: {detail}", usage, started)
                    return
                content_type = response.headers.get("content-type", "").lower()
                if "text/event-stream" not in content_type:
                    raise HermesProtocolError(f"expected text/event-stream, got {content_type!r}")

                async for event in iter_sse_events(response.aiter_lines()):
                    kind = event.data.get("type") or event.event
                    if kind == "response.created":
                        envelope = event.data.get("response") or {}
                        response_id = str(envelope.get("id") or "") or None
                    elif kind == "response.output_text.delta":
                        delta = event.data.get("delta")
                        if not isinstance(delta, str):
                            raise HermesProtocolError("response.output_text.delta has no string delta")
                        if delta:
                            produced = True
                            yield TextDelta(text=delta)
                    elif kind == "response.output_item.added":
                        item = event.data.get("item") or {}
                        if item.get("type") == "function_call":
                            call_id = str(item.get("call_id") or item.get("id") or "")
                            if not call_id:
                                raise HermesProtocolError("function_call has no call_id")
                            name = _raw_tool_name(str(item.get("name") or ""))
                            args = _arguments(item)
                            calls[call_id] = (name, args)
                            produced = True
                            yield ToolCall(call_id=call_id, name=name, arguments=args)
                            act = emitter.on_tool_call(name)
                            if act:
                                yield act
                        elif item.get("type") == "function_call_output":
                            call_id = str(item.get("call_id") or "")
                            name, _ = calls.get(call_id, ("unknown", {}))
                            result = _tool_output(item)
                            ok = item.get("status") == "completed"
                            yield ToolResult(
                                call_id=call_id,
                                name=name,
                                ok=ok,
                                result=result if ok else None,
                                error=None if ok else str(result),
                            )
                            if ok:
                                act = emitter.on_tool_result(name, result)
                                if act:
                                    yield act
                    elif kind == "response.completed":
                        terminal = True
                        envelope = event.data.get("response") or {}
                        usage = _usage(envelope)
                        response_id = str(envelope.get("id") or response_id or "") or None
                        act = emitter.on_done()
                        if act:
                            yield act
                        yield self._done("complete" if produced else "no_action", None, usage, started)
                        self.last_response_id = response_id
                        return
                    elif kind == "response.failed":
                        terminal = True
                        envelope = event.data.get("response") or {}
                        usage = _usage(envelope)
                        error = envelope.get("error") or event.data.get("error") or {}
                        detail = error.get("message") if isinstance(error, dict) else str(error)
                        yield self._done("error", detail or "Hermes response failed", usage, started)
                        return

            if not terminal:
                raise HermesProtocolError("Hermes stream ended without a terminal event")
        except asyncio.CancelledError:
            # Leaving httpx's stream context closes the client connection.
            # Hermes treats that disconnect as an interrupt; never translate a
            # deliberate Core cancellation into a normal Done event.
            raise
        except (httpx.HTTPError, HermesProtocolError) as exc:
            log.warning("Hermes turn failed: %s", exc)
            yield self._done("error", str(exc), usage, started)
        except Exception as exc:  # noqa: BLE001 - operational failure boundary
            log.exception("HermesAgent.turn crashed")
            yield self._done("error", f"agent crashed: {exc!r}", usage, started)

    def _done(
        self,
        reason: str,
        detail: str | None,
        usage: TurnUsage,
        started: float,
    ) -> Done:
        self.last_usage = usage
        self.last_latency_s = time.perf_counter() - started
        return Done(reason=reason, detail=detail, usage=usage)  # type: ignore[arg-type]

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """Compatibility helper for Core health probes and summaries.

        Tools are intentionally ignored: Hermes' API-server toolset is fixed by
        the classroom profile, not installed from client request fields.
        """

        del tools, max_tokens
        instructions = "\n\n".join(
            str(message.get("content") or "")
            for message in messages
            if message.get("role") == "system"
        )
        input_messages = [message for message in messages if message.get("role") != "system"]
        body: dict[str, Any] = {
            "model": self.config.model,
            "input": input_messages or "ping",
            "stream": False,
            "store": False,
        }
        if instructions:
            body["instructions"] = instructions
        response = await self._client.post(
            self.config.responses_url,
            json=body,
            headers={**self.config.headers(), "accept": "application/json"},
        )
        response.raise_for_status()
        payload = response.json()
        text_parts: list[str] = []
        for item in payload.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for block in item.get("content") or []:
                if isinstance(block, dict) and block.get("type") == "output_text":
                    text_parts.append(str(block.get("text") or ""))
        text = "".join(text_parts)
        usage = payload.get("usage") or {}
        return {
            "id": payload.get("id"),
            "object": "chat.completion",
            "model": payload.get("model", self.config.model),
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": text},
                    "finish_reason": "stop" if payload.get("status") == "completed" else "error",
                }
            ],
            "usage": {
                "prompt_tokens": int(usage.get("input_tokens") or 0),
                "completion_tokens": int(usage.get("output_tokens") or 0),
                "total_tokens": int(usage.get("total_tokens") or 0),
            },
        }


__all__ = [
    "HermesAgent",
    "HermesConfig",
    "HermesProtocolError",
    "HermesSSEEvent",
    "build_hermes_input",
    "build_hermes_request",
    "iter_sse_events",
]
