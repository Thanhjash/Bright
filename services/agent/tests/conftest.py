from __future__ import annotations

import json
from typing import Any, Iterable

import httpx
import pytest
from bright_contracts import (
    AvailableAction,
    LastInteraction,
    LessonPosition,
    RecalledMemory,
    Scene,
    StudentBrief,
    TurnContext,
)

from bright_agent.direct import DirectAgent, LLMConfig


def make_ctx(
    *,
    state_version: int = 88,
    actions: Iterable[AvailableAction] | None = None,
    student: bool = True,
    recalled: bool = True,
) -> TurnContext:
    if actions is None:
        actions = [
            AvailableAction(id="next_activity", label="advance to sentence_builder"),
            AvailableAction(id="repeat_activity", label="repeat vocabulary_grid"),
            AvailableAction(id="scaffold_down", label="drop to image support"),
            AvailableAction(id="call_student", label="call on a student", params=["student_id"]),
        ]
    return TurnContext(
        stateVersion=state_version,
        lesson=LessonPosition(
            lessonId="en-a1-market-01",
            classId="7A",
            activityIndex=2,
            activityCount=9,
            stage="PRACTICE",
            currentStudentId="s17" if student else None,
        ),
        scene=Scene(
            stateVersion=state_version,
            kind="choice",
            props={
                "prompt": "Which one is the apple?",
                "options": [
                    {"id": "o1", "text": "apple"},
                    {"id": "o2", "text": "banana"},
                ],
            },
        ),
        student=StudentBrief(id="s17", name="Minh", skills={"food_vocab": 0.82})
        if student
        else None,
        lastInteraction=LastInteraction(kind="choice", detail="picked banana", outcome="wrong"),
        availableActions=list(actions),
        recalled=[RecalledMemory(text="confused apple and banana", when="2026-08-04")]
        if recalled
        else None,
    )


# ------------------------------------------------------------ SSE fixtures


def sse(chunks: list[dict[str, Any]], *, done: bool = True) -> bytes:
    body = "".join(f"data: {json.dumps(c)}\n\n" for c in chunks)
    if done:
        body += "data: [DONE]\n\n"
    return body.encode()


def text_chunk(text: str) -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"content": text}, "finish_reason": None}],
    }


def tool_chunk(
    index: int = 0,
    *,
    call_id: str | None = None,
    name: str | None = None,
    arguments: str | None = None,
) -> dict[str, Any]:
    fn: dict[str, Any] = {}
    if name is not None:
        fn["name"] = name
    if arguments is not None:
        fn["arguments"] = arguments
    call: dict[str, Any] = {"index": index, "function": fn}
    if call_id is not None:
        call["id"] = call_id
        call["type"] = "function"
    return {
        "id": "c1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {"tool_calls": [call]}, "finish_reason": None}],
    }


def finish_chunk(reason: str = "stop", *, prompt: int = 700, completion: int = 40, cached: int = 250) -> dict[str, Any]:
    return {
        "id": "c1",
        "object": "chat.completion.chunk",
        "choices": [{"index": 0, "delta": {}, "finish_reason": reason}],
        "usage": {
            "prompt_tokens": prompt,
            "completion_tokens": completion,
            "total_tokens": prompt + completion,
            "prompt_tokens_details": {"cached_tokens": cached},
        },
    }


class FakeLLM:
    """Serves a scripted list of SSE bodies, one per round. Records requests."""

    def __init__(self, rounds: list[bytes], status: int = 200) -> None:
        self.rounds = list(rounds)
        self.status = status
        self.requests: list[dict[str, Any]] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(json.loads(request.content))
        if self.status >= 400:
            return httpx.Response(self.status, text="boom")
        body = self.rounds.pop(0) if self.rounds else sse([finish_chunk()])
        return httpx.Response(
            200, content=body, headers={"content-type": "text/event-stream"}
        )

    @property
    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler))


def make_agent(fake: FakeLLM, executor, **kw) -> DirectAgent:
    return DirectAgent(
        executor,
        LLMConfig(base_url="https://fake.test/v1", api_key="k", model="m", **kw),
        client=fake.client,
    )


class RecordingExecutor:
    """Stand-in for classroom-core. `results` maps tool name -> value or Exception."""

    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append((name, arguments))
        value = self.results.get(name, {"ok": True})
        if isinstance(value, Exception):
            raise value
        return value


@pytest.fixture
def ctx() -> TurnContext:
    return make_ctx()


@pytest.fixture(autouse=True)
def _clear_rejections():
    from bright_agent.validation import REJECTION_LOG

    REJECTION_LOG.clear()
    yield
    REJECTION_LOG.clear()
