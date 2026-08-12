"""`DirectAgent` — Phase 1 `TeacherAgent`, straight OpenAI-compatible HTTP.

No SDK. We control the request body ourselves because MiMo's
`thinking` field is non-standard and must appear **top-level**
(docs/4-build/phase-1-plan.md §0): `extra_body={"thinking": ...}` is Python-SDK sugar that the
SDK flattens; over raw HTTP a nested field silently leaves reasoning on
and the completion budget is burned returning empty content.

Phase 3's `LocalAgent` is this class with `base_url` pointed at OVMS or
llama.cpp.
"""

from __future__ import annotations

import json
import logging
import os
import time
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable

import httpx
from bright_contracts import TurnContext

from .act import ActEmitter
from .base import AgentEvent, Done, TextDelta, ToolCall, ToolResult, TurnUsage
from .prompt import SYSTEM_PROMPT, build_messages
from .tools import TERMINAL_TOOLS, ToolExecutor, build_tools
from .validation import Rejection, record_rejection, validate_call

log = logging.getLogger("bright.agent.direct")


def _truthy(raw: str | None, *, default: bool) -> bool:
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


@dataclass
class LLMConfig:
    """Everything provider-shaped. Read from the environment, never hardcoded."""

    base_url: str = "https://token-plan-sgp.xiaomimimo.com/v1"
    api_key: str = ""
    model: str = "mimo-v2.5-pro"
    #: MiMo-specific. Top-level `{"thinking": {"type": "disabled"}}`.
    disable_thinking: bool = True
    temperature: float = 0.3
    max_tokens: int = 400
    #: Hard ceiling on tool-loop rounds. The class is waiting; bounded means bounded.
    max_rounds: int = 3
    request_timeout_s: float = 20.0
    connect_timeout_s: float = 5.0
    extra_body: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_env(cls, env: dict[str, str] | None = None) -> "LLMConfig":
        e: Any = os.environ if env is None else env
        return cls(
            base_url=e.get("LLM_BASE_URL", cls.base_url).rstrip("/"),
            api_key=e.get("LLM_API_KEY", ""),
            model=e.get("LLM_MODEL", cls.model),
            disable_thinking=_truthy(e.get("LLM_DISABLE_THINKING"), default=True),
            temperature=float(e.get("LLM_TEMPERATURE", cls.temperature)),
            max_tokens=int(e.get("LLM_MAX_TOKENS", cls.max_tokens)),
            max_rounds=int(e.get("LLM_MAX_ROUNDS", cls.max_rounds)),
            request_timeout_s=float(e.get("LLM_TIMEOUT_S", cls.request_timeout_s)),
        )

    @property
    def chat_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/chat/completions"

    def headers(self) -> dict[str, str]:
        # The provider accepts either; sending both keeps a proxy swap cheap.
        return {
            "content-type": "application/json",
            "api-key": self.api_key,
            "authorization": f"Bearer {self.api_key}",
        }


def build_request_body(
    config: LLMConfig,
    messages: list[dict[str, Any]],
    *,
    tools: list[dict[str, Any]] | None = None,
    stream: bool = True,
    max_tokens: int | None = None,
) -> dict[str, Any]:
    """The exact JSON we POST. Kept separate so tests can assert its shape."""
    body: dict[str, Any] = {
        "model": config.model,
        "messages": messages,
        "temperature": config.temperature,
        "max_tokens": max_tokens if max_tokens is not None else config.max_tokens,
        "stream": stream,
    }
    if config.disable_thinking:
        # TOP-LEVEL. Not inside extra_body, not inside a nested options object.
        body["thinking"] = {"type": "disabled"}
    if tools:
        body["tools"] = tools
        body["tool_choice"] = "auto"
        # Single attempt per call: no parallel fan-out to un-repair later.
        body["parallel_tool_calls"] = False
    if stream:
        # Usage only arrives in the final chunk if we ask for it.
        body["stream_options"] = {"include_usage": True}
    body.update(config.extra_body)
    return body


# ------------------------------------------------------------- streaming


@dataclass
class _RoundResult:
    text: str = ""
    calls: list[ToolCall] = field(default_factory=list)
    parse_errors: dict[str, str] = field(default_factory=dict)
    raw_calls: list[dict[str, Any]] = field(default_factory=list)
    usage: TurnUsage = field(default_factory=TurnUsage)
    finish_reason: str | None = None
    error: str | None = None
    latency_s: float = 0.0


def _usage_from(payload: dict[str, Any]) -> TurnUsage:
    u = payload.get("usage") or {}
    details = u.get("prompt_tokens_details") or {}
    return TurnUsage(
        prompt_tokens=int(u.get("prompt_tokens") or 0),
        completion_tokens=int(u.get("completion_tokens") or 0),
        cached_tokens=int(details.get("cached_tokens") or u.get("cached_tokens") or 0),
        total_tokens=int(u.get("total_tokens") or 0),
        rounds=1,
    )


def _merge_tool_call_deltas(acc: dict[int, dict[str, Any]], deltas: list[dict[str, Any]]) -> None:
    """Streamed tool calls arrive fragmented; merge by `index`, concatenating
    the `arguments` string. Parse the JSON exactly once, at the end."""
    for d in deltas:
        idx = int(d.get("index") or 0)
        slot = acc.setdefault(idx, {"id": "", "name": "", "arguments": ""})
        if d.get("id"):
            slot["id"] = d["id"]
        fn = d.get("function") or {}
        if fn.get("name"):
            slot["name"] = fn["name"]
        if fn.get("arguments"):
            slot["arguments"] += fn["arguments"]


class DirectAgent:
    """`TeacherAgent` over an OpenAI-compatible endpoint.

    `executor` is injected by classroom-core. This module never imports it.
    """

    def __init__(
        self,
        executor: ToolExecutor,
        config: LLMConfig | None = None,
        *,
        client: httpx.AsyncClient | None = None,
        system_prompt: str = SYSTEM_PROMPT,
        include_recall: bool = True,
        tools_builder: Callable[[TurnContext], list[dict[str, Any]]] | None = None,
        messages_builder: Callable[[TurnContext], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.config = config or LLMConfig.from_env()
        self.executor = executor
        self.system_prompt = system_prompt
        self.include_recall = include_recall
        # Seams for `evals/` to swap the tool surface or the prompt without
        # forking the turn loop. Default None == the shipped behaviour, so
        # nothing about production changes. See evals/variants.py.
        self.tools_builder = tools_builder
        self.messages_builder = messages_builder
        self._own_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(
                self.config.request_timeout_s, connect=self.config.connect_timeout_s
            )
        )
        #: Usage of the most recent completed turn — for the health probe / cost logs.
        self.last_usage = TurnUsage()
        self.last_latency_s = 0.0

    async def aclose(self) -> None:
        if self._own_client:
            await self._client.aclose()

    async def __aenter__(self) -> "DirectAgent":
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.aclose()

    # ---------------------------------------------------------- the turn

    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]:
        """One teaching decision. Always terminates with exactly one `Done`."""
        messages = (
            self.messages_builder(ctx)
            if self.messages_builder is not None
            else build_messages(ctx, system=self.system_prompt)
        )
        tools = (
            self.tools_builder(ctx)
            if self.tools_builder is not None
            else build_tools(ctx, include_recall=self.include_recall)
        )
        emitter = ActEmitter()
        total = TurnUsage()
        started = time.perf_counter()
        spoke = False

        try:
            for _round in range(self.config.max_rounds):
                rr = _RoundResult()
                async for ev in self._stream_round(messages, tools, rr):
                    if isinstance(ev, TextDelta):
                        spoke = spoke or bool(ev.text.strip())
                    yield ev
                total = total.add(rr.usage)

                if rr.error:
                    yield self._done(ctx, "error", rr.error, total, started)
                    return

                if not rr.calls:
                    reason = "complete" if (spoke or rr.text.strip()) else "no_action"
                    if reason == "complete":
                        act = emitter.on_done()
                        if act:
                            yield act
                    yield self._done(ctx, reason, rr.finish_reason, total, started)
                    return

                messages.append(
                    {
                        "role": "assistant",
                        "content": rr.text or None,
                        "tool_calls": rr.raw_calls,
                    }
                )

                for call in rr.calls:
                    yield call
                    act = emitter.on_tool_call(call.name)
                    if act:
                        yield act

                    rejection = self._check(ctx, call, rr.parse_errors.get(call.call_id))
                    if rejection is not None:
                        yield ToolResult(
                            call_id=call.call_id,
                            name=call.name,
                            ok=False,
                            error=str(rejection),
                        )
                        # SINGLE ATTEMPT. No repair loop in front of a class.
                        yield self._done(ctx, "error", str(rejection), total, started)
                        return

                    try:
                        result = await self.executor(call.name, call.arguments)
                    except Exception as exc:  # noqa: BLE001 - operational, not a bug
                        log.warning(
                            "tool execution failed tool=%s args=%s err=%r",
                            call.name,
                            call.arguments,
                            exc,
                        )
                        yield ToolResult(
                            call_id=call.call_id, name=call.name, ok=False, error=repr(exc)
                        )
                        yield self._done(
                            ctx, "error", f"{call.name} failed: {exc!r}", total, started
                        )
                        return

                    yield ToolResult(
                        call_id=call.call_id, name=call.name, ok=True, result=result
                    )
                    act = emitter.on_tool_result(call.name, result)
                    if act:
                        yield act

                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call.call_id,
                            "name": call.name,
                            "content": json.dumps(result, default=str)[:2000],
                        }
                    )

                    if call.name in TERMINAL_TOOLS:
                        act = emitter.on_done()
                        if act:
                            yield act
                        yield self._done(ctx, "complete", None, total, started)
                        return

            yield self._done(
                ctx, "error", f"tool loop exceeded max_rounds={self.config.max_rounds}",
                total, started,
            )
        except Exception as exc:  # noqa: BLE001 - never let a raise reach core
            log.exception("DirectAgent.turn crashed")
            yield self._done(ctx, "error", f"agent crashed: {exc!r}", total, started)

    # ------------------------------------------------------------ helpers

    def _done(
        self,
        ctx: TurnContext,
        reason: str,
        detail: str | None,
        usage: TurnUsage,
        started: float,
    ) -> Done:
        self.last_usage = usage
        self.last_latency_s = time.perf_counter() - started
        log.info(
            "turn done reason=%s lesson=%s activity=%s latency=%.2fs "
            "prompt=%d cached=%d completion=%d rounds=%d detail=%s",
            reason,
            ctx.lesson.lesson_id,
            ctx.lesson.activity_index,
            self.last_latency_s,
            usage.prompt_tokens,
            usage.cached_tokens,
            usage.completion_tokens,
            usage.rounds,
            detail,
        )
        return Done(reason=reason, detail=detail, usage=usage)  # type: ignore[arg-type]

    def _check(
        self, ctx: TurnContext, call: ToolCall, parse_error: str | None
    ) -> Rejection | None:
        if parse_error:
            return record_rejection(
                Rejection(
                    code="bad_arguments",
                    tool=call.name,
                    detail=parse_error,
                    available_action_ids=[a.id for a in ctx.available_actions],
                    ctx_state_version=ctx.state_version,
                    lesson_id=ctx.lesson.lesson_id,
                    activity_index=ctx.lesson.activity_index,
                    student_id=ctx.student.id if ctx.student else None,
                )
            )
        return validate_call(ctx, call.name, call.arguments)

    # ------------------------------------------------------------ network

    async def _stream_round(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        out: _RoundResult,
    ) -> AsyncIterator[AgentEvent]:
        body = build_request_body(self.config, messages, tools=tools, stream=True)
        acc: dict[int, dict[str, Any]] = {}
        t0 = time.perf_counter()
        try:
            async with self._client.stream(
                "POST", self.config.chat_url, json=body, headers=self.config.headers()
            ) as resp:
                if resp.status_code >= 400:
                    detail = (await resp.aread())[:400].decode("utf-8", "replace")
                    out.error = f"HTTP {resp.status_code}: {detail}"
                    return
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    try:
                        chunk = json.loads(data)
                    except json.JSONDecodeError:
                        log.warning("undecodable SSE chunk skipped: %.120s", data)
                        continue
                    if chunk.get("usage"):
                        out.usage = _usage_from(chunk)
                    for choice in chunk.get("choices") or []:
                        delta = choice.get("delta") or {}
                        if choice.get("finish_reason"):
                            out.finish_reason = choice["finish_reason"]
                        # Reasoning is stripped here, before any text reaches
                        # the TTS chunker (PROTOCOL.md §5 parser rule 2).
                        if delta.get("reasoning_content"):
                            continue
                        content = delta.get("content")
                        if content:
                            out.text += content
                            yield TextDelta(text=content)
                        if delta.get("tool_calls"):
                            _merge_tool_call_deltas(acc, delta["tool_calls"])
        except httpx.HTTPError as exc:
            out.error = f"transport error: {exc!r}"
            return
        finally:
            out.latency_s = time.perf_counter() - t0

        if out.usage.rounds == 0:
            out.usage = TurnUsage(rounds=1)

        for idx in sorted(acc):
            slot = acc[idx]
            call_id = slot["id"] or f"call_{idx}"
            raw_args = slot["arguments"] or "{}"
            try:
                args = json.loads(raw_args)
                if not isinstance(args, dict):
                    raise ValueError("arguments must be a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                args = {}
                out.parse_errors[call_id] = f"unparseable arguments {raw_args!r}: {exc}"
            out.calls.append(ToolCall(call_id=call_id, name=slot["name"], arguments=args))
            out.raw_calls.append(
                {
                    "id": call_id,
                    "type": "function",
                    "function": {"name": slot["name"], "arguments": raw_args},
                }
            )

    # ------------------------------------------------- non-streaming helper

    async def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
    ) -> dict[str, Any]:
        """One blocking completion. Used by background jobs (session
        summaries) and by the live tests that inspect the raw response."""
        body = build_request_body(
            self.config, messages, tools=tools, stream=False, max_tokens=max_tokens
        )
        resp = await self._client.post(
            self.config.chat_url, json=body, headers=self.config.headers()
        )
        resp.raise_for_status()
        return resp.json()


__all__ = ["LLMConfig", "DirectAgent", "build_request_body"]
