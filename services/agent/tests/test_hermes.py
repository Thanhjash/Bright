"""Hermes adapter contract tests — pure MockTransport, never a live gateway."""

from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any

import httpx
import pytest

from bright_agent.base import Done, TextDelta, ToolCall, ToolResult
from bright_agent.hermes import (
    HermesAgent,
    HermesConfig,
    HermesProtocolError,
    build_hermes_request,
    iter_sse_events,
)

from .conftest import make_ctx


def frame(event: str, payload: dict[str, Any]) -> bytes:
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n".encode()


def stream_body(*events: tuple[str, dict[str, Any]]) -> bytes:
    return b"".join(frame(event, payload) for event, payload in events)


def created(response_id: str = "resp_test") -> tuple[str, dict[str, Any]]:
    return (
        "response.created",
        {
            "type": "response.created",
            "response": {"id": response_id, "status": "in_progress"},
        },
    )


def completed(response_id: str = "resp_test") -> tuple[str, dict[str, Any]]:
    return (
        "response.completed",
        {
            "type": "response.completed",
            "response": {
                "id": response_id,
                "status": "completed",
                "usage": {"input_tokens": 31, "output_tokens": 7, "total_tokens": 38},
            },
        },
    )


async def collect(agent: HermesAgent):
    return [event async for event in agent.turn(make_ctx())]


def make_agent(handler) -> HermesAgent:
    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return HermesAgent(
        config=HermesConfig(
            base_url="https://hermes.test",
            api_key="secret",
            model="classroom",
        ),
        client=client,
    )


def test_request_is_streaming_and_never_stored():
    body = build_hermes_request(HermesConfig(model="classroom"), make_ctx(), "turn-123")
    assert body["stream"] is True
    assert body["store"] is False
    assert body["model"] == "classroom"
    assert "turn-123" in body["input"]
    assert "tools" not in body, "Hermes tools come from its profile, never the client request"
    assert "instructions" not in body, "the live prompt is server-owned and cannot drift per request"


def test_headers_never_enable_hermes_conversation_chaining():
    config = HermesConfig.from_env({"HERMES_SESSION_KEY": "must-be-ignored"})
    assert "X-Hermes-Session-Key" not in config.headers()


def test_config_reads_environment_and_keeps_safe_defaults():
    defaults = HermesConfig.from_env({})
    assert defaults.base_url == "http://127.0.0.1:8642"
    configured = HermesConfig.from_env(
        {
            "HERMES_API_URL": "http://127.0.0.1:9999/",
            "HERMES_API_KEY": "k",
            "HERMES_API_MODEL": "local-gemma",
            "HERMES_API_TIMEOUT_S": "7",
            "HERMES_CONNECT_TIMEOUT_S": "0.5",
        }
    )
    assert configured.responses_url == "http://127.0.0.1:9999/v1/responses"
    assert configured.api_key == "k"
    assert configured.model == "local-gemma"
    assert configured.request_timeout_s == 7
    assert configured.connect_timeout_s == 0.5


async def test_health_uses_gateway_endpoint_without_model_completion():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"status": "ok"})

    agent = make_agent(handler)
    assert await agent.health() is True
    assert len(seen) == 1
    assert seen[0].method == "GET"
    assert seen[0].url.path == "/health"
    assert seen[0].headers["authorization"] == "Bearer secret"
    await agent.aclose()


async def test_sse_parser_supports_multiline_data_and_comments():
    async def lines() -> AsyncIterator[str]:
        for line in (
            ": keepalive",
            "event: response.output_text.delta",
            'data: {"type":"response.output_text.delta",',
            'data: "delta":"hello"}',
            "",
        ):
            yield line

    events = [event async for event in iter_sse_events(lines())]
    assert len(events) == 1
    assert events[0].event == "response.output_text.delta"
    assert events[0].data["delta"] == "hello"


async def test_sse_parser_rejects_bad_json():
    async def lines() -> AsyncIterator[str]:
        yield "event: response.created"
        yield "data: {not-json}"
        yield ""

    with pytest.raises(HermesProtocolError, match="invalid SSE JSON"):
        _ = [event async for event in iter_sse_events(lines())]


async def test_only_committed_proposal_teacher_line_becomes_voice():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer secret"
        body = json.loads(request.content)
        assert body["store"] is False
        call = {
            "type": "response.output_item.added",
            "item": {
                "id": "fc_1",
                "type": "function_call",
                "status": "in_progress",
                "name": "mcp__bright_classroom__classroom_propose_move",
                "call_id": "call_1",
                "arguments": json.dumps(
                    {
                        "turn_id": "ignored-here",
                        "move_id": "next_activity",
                        "teacher_line": "Let's try the next one.",
                    }
                ),
            },
        }
        result = {
            "type": "response.output_item.added",
            "item": {
                "type": "function_call_output",
                "status": "completed",
                "call_id": "call_1",
                "output": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "result": '{"ok":true,"applied":"next_activity"}',
                                "structuredContent": {
                                    "ok": True,
                                    "applied": "next_activity",
                                },
                            }
                        ),
                    }
                ],
            },
        }
        content = stream_body(
            created(),
            (
                "response.output_text.delta",
                {"type": "response.output_text.delta", "delta": "UNTRUSTED PRE-COMMIT TEXT"},
            ),
            ("response.output_item.added", call),
            ("response.output_item.added", result),
            completed(),
        )
        return httpx.Response(200, content=content, headers={"content-type": "text/event-stream"})

    agent = make_agent(handler)
    agent.prepare_turn("ignored-here")
    events = await collect(agent)
    assert [event.text for event in events if isinstance(event, TextDelta)] == [
        "Let's try the next one."
    ]
    call = next(event for event in events if isinstance(event, ToolCall))
    assert call.name == "classroom_propose_move"
    assert call.arguments["move_id"] == "next_activity"
    result = next(event for event in events if isinstance(event, ToolResult))
    assert result.name == "classroom_propose_move"
    assert result.ok is True
    assert result.result["applied"] == "next_activity"
    done = events[-1]
    assert isinstance(done, Done) and done.reason == "complete"
    assert done.usage.prompt_tokens == 31
    assert done.usage.completion_tokens == 7
    assert done.usage.total_tokens == 38
    assert agent.last_response_id == "resp_test"


async def test_completed_response_status_cannot_override_rejected_inner_mcp_result():
    def handler(request: httpx.Request) -> httpx.Response:
        call = {
            "type": "response.output_item.added",
            "item": {
                "id": "fc_rejected",
                "type": "function_call",
                "status": "in_progress",
                "name": "mcp__bright_classroom__classroom_propose_move",
                "call_id": "call_rejected",
                "arguments": json.dumps(
                    {
                        "turn_id": "turn-rejected",
                        "move_id": "advance",
                        "teacher_line": "Let's continue.",
                    }
                ),
            },
        }
        output = {
            "type": "response.output_item.added",
            "item": {
                "type": "function_call_output",
                "status": "completed",
                "call_id": "call_rejected",
                "output": [
                    {
                        "type": "input_text",
                        "text": json.dumps(
                            {
                                "result": '{"ok":false,"reason":"stale turn"}',
                                "structuredContent": {"ok": False, "reason": "stale turn"},
                            }
                        ),
                    }
                ],
            },
        }
        return httpx.Response(
            200,
            content=stream_body(created(), ("response.output_item.added", call), ("response.output_item.added", output), completed()),
            headers={"content-type": "text/event-stream"},
        )

    agent = make_agent(handler)
    agent.prepare_turn("turn-rejected")
    events = await collect(agent)
    assert not any(isinstance(event, TextDelta) for event in events)
    result = next(event for event in events if isinstance(event, ToolResult))
    assert result.ok is False
    assert "stale turn" in (result.error or "")
    assert isinstance(events[-1], Done)
    assert events[-1].reason == "error"


async def test_completed_envelope_recovers_fast_terminal_tool_callback_race():
    arguments = {
        "turn_id": "turn-envelope",
        "move_id": "advance",
        "teacher_line": "Let us continue.",
    }
    output = [
        {
            "type": "function_call",
            "name": "mcp__bright_classroom__classroom_propose_move",
            "call_id": "call-envelope",
            "arguments": json.dumps(arguments),
        },
        {
            "type": "function_call_output",
            "call_id": "call-envelope",
            "output": [
                {
                    "type": "input_text",
                    "text": json.dumps(
                        {"structuredContent": {"ok": True, "applied": False}}
                    ),
                }
            ],
        },
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        terminal = completed()[1]
        terminal["response"]["output"] = output
        return httpx.Response(
            200,
            content=stream_body(created(), ("response.completed", terminal)),
            headers={"content-type": "text/event-stream"},
        )

    agent = make_agent(handler)
    agent.prepare_turn("turn-envelope")
    events = await collect(agent)
    assert [event.text for event in events if isinstance(event, TextDelta)] == [
        "Let us continue."
    ]
    assert isinstance(events[-1], Done) and events[-1].reason == "complete"


async def test_response_without_exactly_one_proposal_fails_closed():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=stream_body(
                created(),
                (
                    "response.output_text.delta",
                    {"type": "response.output_text.delta", "delta": "Do not speak this."},
                ),
                completed(),
            ),
            headers={"content-type": "text/event-stream"},
        )

    agent = make_agent(handler)
    agent.prepare_turn("turn")
    events = await collect(agent)
    assert not any(isinstance(event, TextDelta) for event in events)
    assert events[-1].reason == "error"
    assert "exactly one" in (events[-1].detail or "")


async def test_second_proposal_makes_whole_response_invalid_and_speaks_nothing():
    def call(number: int) -> tuple[str, dict[str, Any]]:
        return (
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call",
                    "name": "classroom_propose_move",
                    "call_id": f"call_{number}",
                    "arguments": json.dumps(
                        {
                            "turn_id": "turn",
                            "move_id": f"move_{number}",
                            "teacher_line": f"Line {number}",
                        }
                    ),
                },
            },
        )

    def output(number: int) -> tuple[str, dict[str, Any]]:
        return (
            "response.output_item.added",
            {
                "type": "response.output_item.added",
                "item": {
                    "type": "function_call_output",
                    "status": "completed",
                    "call_id": f"call_{number}",
                    "output": [
                        {
                            "type": "input_text",
                            "text": json.dumps(
                                {"structuredContent": {"ok": True, "applied": f"move_{number}"}}
                            ),
                        }
                    ],
                },
            },
        )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=stream_body(created(), call(1), call(2), output(1), output(2), completed()),
            headers={"content-type": "text/event-stream"},
        )

    agent = make_agent(handler)
    agent.prepare_turn("turn")
    events = await collect(agent)
    assert not any(isinstance(event, TextDelta) for event in events)
    assert events[-1].reason == "error"


async def test_http_error_is_one_done_error_without_retry():
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(503, text="not ready")

    events = await collect(make_agent(handler))
    assert requests == 1
    assert events[-1].reason == "error"
    assert "503" in (events[-1].detail or "")


async def test_wrong_content_type_is_a_protocol_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "completed"})

    events = await collect(make_agent(handler))
    assert events[-1].reason == "error"
    assert "text/event-stream" in (events[-1].detail or "")


async def test_stream_without_terminal_event_is_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=stream_body(created()),
            headers={"content-type": "text/event-stream"},
        )

    events = await collect(make_agent(handler))
    assert events[-1].reason == "error"
    assert "without a terminal event" in (events[-1].detail or "")


class BlockingStream(httpx.AsyncByteStream):
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.closed = asyncio.Event()
        self.release = asyncio.Event()

    async def __aiter__(self) -> AsyncIterator[bytes]:
        yield frame(*created())
        self.started.set()
        await self.release.wait()

    async def aclose(self) -> None:
        self.closed.set()


async def test_cancelling_turn_closes_the_stream_and_reraises_cancelled():
    stream = BlockingStream()

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, stream=stream, headers={"content-type": "text/event-stream"})

    task = asyncio.create_task(collect(make_agent(handler)))
    await asyncio.wait_for(stream.started.wait(), timeout=1)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    await asyncio.wait_for(stream.closed.wait(), timeout=1)


async def test_live_complete_is_disabled_without_consuming_the_single_gateway_slot():
    requests = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal requests
        requests += 1
        return httpx.Response(500)

    with pytest.raises(RuntimeError, match="live Hermes profile"):
        await make_agent(handler).complete([{"role": "user", "content": "probe"}])
    assert requests == 0
