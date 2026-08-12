"""LIVE tests — they hit the real endpoint.

Skipped unless both `BRIGHT_RUN_LIVE_TESTS=1` and `LLM_API_KEY` are set.
Run with:  BRIGHT_RUN_LIVE_TESTS=1 pytest -m live -s

These exist because two claims are load-bearing and cheap to regress:
  1. `"thinking": {"type": "disabled"}` as a TOP-LEVEL field actually
     suppresses reasoning. Nested, it silently does not, and the whole
     completion budget is burned returning empty content (docs/4-build/phase-1-plan.md §0).
  2. Constrained `action_id` tool calling returns an id from the enum.
"""

from __future__ import annotations

import json
import os

import httpx
import pytest

from bright_agent.base import Done, TextDelta, ToolCall, ToolResult
from bright_agent.direct import DirectAgent, LLMConfig, build_request_body
from bright_agent.tools import CHOOSE_NEXT

from .conftest import RecordingExecutor, make_ctx

pytestmark = [
    pytest.mark.live,
    pytest.mark.skipif(
        os.environ.get("BRIGHT_RUN_LIVE_TESTS") != "1"
        or not os.environ.get("LLM_API_KEY")
        or os.environ.get("LLM_API_KEY", "").startswith("tp-xxxx"),
        reason="live tests require explicit BRIGHT_RUN_LIVE_TESTS=1 and LLM_API_KEY",
    ),
]


@pytest.fixture
async def agent():
    a = DirectAgent(RecordingExecutor(), LLMConfig.from_env())
    try:
        yield a
    finally:
        await a.aclose()


async def test_thinking_disabled_suppresses_reasoning(agent, capsys):
    """The exact failure mode: a small max_tokens plus reasoning-on returns
    empty content. With thinking disabled we must get real content."""
    cfg = LLMConfig.from_env()
    assert cfg.disable_thinking, "LLM_DISABLE_THINKING must be true for this test"

    body = build_request_body(
        cfg, [{"role": "user", "content": "Say the single word: apple"}],
        stream=False, max_tokens=50,
    )
    assert body["thinking"] == {"type": "disabled"}  # top-level, not nested

    data = await agent.complete(body["messages"], max_tokens=50)
    msg = data["choices"][0]["message"]
    usage = data.get("usage", {})

    print("\n[live] thinking-disabled usage:", json.dumps(usage))
    print("[live] content:", repr(msg.get("content")))
    print("[live] reasoning_content:", repr(msg.get("reasoning_content")))

    assert not msg.get("reasoning_content"), "reasoning leaked despite thinking:disabled"
    assert msg.get("content", "").strip(), "empty content — the budget was burned on reasoning"
    assert usage.get("completion_tokens", 0) <= 50


async def test_thinking_nested_wrongly_is_not_how_it_works():
    """Documents the trap: `extra_body` is SDK sugar. Sent over raw HTTP as a
    literal field it is NOT the disable switch — the provider either ignores
    it or errors, and reasoning stays on."""
    cfg = LLMConfig.from_env()
    body = {
        "model": cfg.model,
        "messages": [{"role": "user", "content": "Say the single word: apple"}],
        "max_tokens": 32,
        "extra_body": {"thinking": {"type": "disabled"}},  # the wrong shape
    }
    async with httpx.AsyncClient(timeout=30) as c:
        r = await c.post(cfg.chat_url, json=body, headers=cfg.headers())
    print("\n[live] wrong-shape status:", r.status_code)
    if r.status_code == 200:
        msg = r.json()["choices"][0]["message"]
        print("[live] wrong-shape content:", repr(msg.get("content")))
        print("[live] wrong-shape reasoning:", repr(msg.get("reasoning_content"))[:200])
        # The point of the test: this shape does NOT disable reasoning.
        leaked = bool(msg.get("reasoning_content")) or not (msg.get("content") or "").strip()
        assert leaked, "extra_body-shaped thinking unexpectedly worked — re-read docs/4-build/phase-1-plan.md §0"
    else:
        assert r.status_code >= 400


async def test_tool_calling_returns_a_valid_action_id(agent, capsys):
    """Constrained multiple choice — the whole design (docs/3-design/architecture.md §3)."""
    ctx = make_ctx()
    legal = {a.id for a in ctx.available_actions}

    events = [ev async for ev in agent.turn(ctx)]
    calls = [e for e in events if isinstance(e, ToolCall)]
    text = "".join(e.text for e in events if isinstance(e, TextDelta))
    done = events[-1]

    print("\n[live] text:", repr(text))
    for c in calls:
        print("[live] tool_call:", c.name, c.arguments)
    print("[live] done:", done.reason, done.detail)
    print("[live] usage:", done.usage.model_dump(), f"latency={agent.last_latency_s:.2f}s")

    assert isinstance(done, Done)
    assert done.reason == "complete", f"turn failed: {done.detail}"

    chose = [c for c in calls if c.name == CHOOSE_NEXT]
    assert chose, f"model never chose an action; called {[c.name for c in calls]}"
    args = chose[-1].arguments
    assert args["action_id"] in legal
    assert int(args["state_version"]) == ctx.state_version
    assert all(isinstance(e, ToolResult) is False or e.ok for e in events)


async def test_prompt_cache_hits_across_two_turns(agent, capsys):
    """The system prompt is stable, so the second turn should report
    cached_tokens. Reports the number either way — it is a design finding,
    not a hard gate (the per-turn tool enum sits in the same prefix)."""
    ctx = make_ctx()
    usages = []
    for _ in range(2):
        done = [ev async for ev in agent.turn(ctx)][-1]
        usages.append(done.usage)
    for i, u in enumerate(usages, 1):
        print(f"\n[live] turn {i}: prompt={u.prompt_tokens} cached={u.cached_tokens} "
              f"completion={u.completion_tokens} rounds={u.rounds}")
    assert usages[0].prompt_tokens > 0
