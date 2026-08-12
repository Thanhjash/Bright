"""A scriptable, OpenAI-compatible chat-completions server.

This is "the agent" as far as `classroom-core` is concerned: core is started
with `BRIGHT_AGENT=1` and `LLM_BASE_URL` pointing here, so `DirectAgent` makes
real HTTP calls, over real SSE, into a server the test controls byte by byte.

That is what makes I4/I5/I6 honest integration tests rather than mocks:

* **I4** — emit a `classroom_choose_next` with an `action_id` core never
  offered, and watch the whole real rejection path run.
* **I5** — emit a real tool call carrying a stale `state_version`.
* **I6** — split `<|ACT {...}|>` across two SSE `data:` frames, which is
  physically impossible to do with a mocked client.
* **I2** — kill this process mid-lesson (by PID, never `pkill -f`).
* **I9** — set `mode: "hang"` and the socket accepts and never answers, which
  is what an unplugged network actually looks like to an HTTP client.

Run standalone:

    python fake_llm.py --port 8123
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

# ---------------------------------------------------------------- scripting

#: FIFO of scripted responses. The last one repeats once the queue drains, so a
#: test can set one response and not care how many turns are taken.
SCRIPT: list[dict[str, Any]] = []
REQUESTS: list[dict[str, Any]] = []
NONSTREAM_REQUESTS: list[dict[str, Any]] = []

DEFAULT_RESPONSE: dict[str, Any] = {
    "chunks": [{"content": "ok"}],
    "finish": "stop",
}

#: Non-streaming calls are infrastructure, not teaching turns: the health probe
#: (`agent_bridge.make_probe`) and the session summariser both use them. They
#: are answered from here and **never consume `SCRIPT`** -- otherwise a probe
#: firing on its 5-second timer would silently eat the response a test queued
#: for the turn it is about to take, and the test would fail for a reason that
#: has nothing to do with what it is testing.
NONSTREAM: dict[str, Any] = {"content": "ok", "status": 200, "delay_before_s": 0.0}


#: Tool arguments may contain `"__STATE_VERSION__"`; it is replaced with the
#: `state_version` this turn's context actually carries, read out of the tool
#: schema core sent. Without it a script cannot answer more than one turn --
#: the version moves every time the board does -- so multi-turn behaviour like
#: "the agent keeps choosing repeat_activity" could not be reproduced at all.
_VERSION_RE = re.compile(r"context \((\d+)\)")
VERSION_PLACEHOLDER = '"__STATE_VERSION__"'


def context_state_version(body: dict[str, Any]) -> int | None:
    for tool in body.get("tools") or []:
        fn = tool.get("function") or {}
        if fn.get("name") != "classroom_choose_next":
            continue
        desc = ((fn.get("parameters") or {}).get("properties") or {}).get(
            "state_version", {}
        ).get("description", "")
        match = _VERSION_RE.search(str(desc))
        if match:
            return int(match.group(1))
    return None


def legal_action_ids(body: dict[str, Any]) -> list[str]:
    for tool in body.get("tools") or []:
        fn = tool.get("function") or {}
        if fn.get("name") == "classroom_choose_next":
            props = (fn.get("parameters") or {}).get("properties") or {}
            return list((props.get("action_id") or {}).get("enum") or [])
    return []


def _fill(response: dict[str, Any], version: int | None) -> dict[str, Any]:
    """Substitute the placeholder inside tool-argument strings.

    Done per field, not by round-tripping the whole response through
    `json.dumps`: tool arguments are themselves a JSON *string*, so in the
    outer encoding the placeholder's quotes are escaped and a naive
    search-and-replace silently matches nothing. That failure mode is invisible
    -- the turn just gets rejected as `bad_arguments` -- and it is what the
    positive control in `test_i2_agent_fallbacks` exists to catch.
    """
    if version is None:
        return response
    out = json.loads(json.dumps(response))
    for step in out.get("chunks") or []:
        tool = step.get("tool")
        if tool and isinstance(tool.get("args"), str):
            tool["args"] = (
                tool["args"]
                .replace(VERSION_PLACEHOLDER, str(version))
                .replace("__STATE_VERSION__", str(version))
            )
        if isinstance(step.get("content"), str):
            step["content"] = step["content"].replace("__STATE_VERSION__", str(version))
    return out


def _chunk(delta: dict[str, Any], finish: str | None = None) -> str:
    payload = {
        "id": "fake-cmpl",
        "object": "chat.completion.chunk",
        "created": int(time.time()),
        "model": "fake-model",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }
    return f"data: {json.dumps(payload)}\n\n"


async def _render(response: dict[str, Any]):
    """Turn one scripted response into an SSE byte stream.

    A `chunks` entry is one of:

      {"content": "..."}                       a text delta
      {"reasoning": "..."}                     a reasoning_content delta
      {"tool": {...}}                          a tool_call delta fragment
      {"sleep": 0.4}                           a pause *inside* the stream
      {"raw": "data: ...\\n\\n"}               a literal frame, for pathologies

    A tool fragment is `{"index":0, "id":"c1", "name":"...", "args":"partial"}`.
    Splitting `args` across several fragments is exactly how a real provider
    streams tool calls, and is how the ACT-token-split case is reproduced.
    """
    delay = float(response.get("delay_before_s") or 0)
    if delay:
        await asyncio.sleep(delay)

    for step in response.get("chunks") or []:
        if "sleep" in step:
            await asyncio.sleep(float(step["sleep"]))
            continue
        if "raw" in step:
            yield step["raw"].encode()
            continue
        if "content" in step:
            yield _chunk({"content": step["content"]}).encode()
            continue
        if "reasoning" in step:
            yield _chunk({"reasoning_content": step["reasoning"]}).encode()
            continue
        if "tool" in step:
            t = step["tool"]
            fragment: dict[str, Any] = {"index": int(t.get("index", 0))}
            if t.get("id"):
                fragment["id"] = t["id"]
            fn: dict[str, Any] = {}
            if t.get("name"):
                fn["name"] = t["name"]
            if t.get("args") is not None:
                fn["arguments"] = t["args"]
            fragment["function"] = fn
            yield _chunk({"tool_calls": [fragment]}).encode()
            continue

    yield _chunk({}, finish=response.get("finish") or "stop").encode()
    usage = response.get("usage") or {
        "prompt_tokens": 1000,
        "completion_tokens": 20,
        "total_tokens": 1020,
    }
    yield (
        "data: "
        + json.dumps(
            {
                "id": "fake-cmpl",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": "fake-model",
                "choices": [],
                "usage": usage,
            }
        )
        + "\n\n"
    ).encode()
    yield b"data: [DONE]\n\n"


def create_app() -> FastAPI:
    app = FastAPI(title="fake-llm")

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "queued": len(SCRIPT), "requests": len(REQUESTS)}

    @app.post("/__script")
    async def set_script(request: Request) -> dict[str, Any]:
        body = await request.json()
        SCRIPT.clear()
        SCRIPT.extend(body.get("responses") or [])
        if body.get("nonStream"):
            NONSTREAM.update(body["nonStream"])
        if body.get("resetRequests", True):
            REQUESTS.clear()
            NONSTREAM_REQUESTS.clear()
        return {"ok": True, "queued": len(SCRIPT)}

    @app.get("/__requests")
    async def get_requests() -> dict[str, Any]:
        return {
            "count": len(REQUESTS),
            "requests": REQUESTS,
            "nonStreamCount": len(NONSTREAM_REQUESTS),
            "nonStream": NONSTREAM_REQUESTS,
        }

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def completions(request: Request):
        body = await request.json()

        if not body.get("stream"):
            NONSTREAM_REQUESTS.append({"ts": time.time(), "body": body})
            delay = float(NONSTREAM.get("delay_before_s") or 0)
            if delay:
                await asyncio.sleep(delay)
            status = int(NONSTREAM.get("status") or 200)
            if status >= 400:
                return JSONResponse(status_code=status, content={"error": {"message": "nope"}})
            return JSONResponse(
                content={
                    "id": "fake-cmpl",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": "fake-model",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": NONSTREAM.get("content", "ok")},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                }
            )

        version = context_state_version(body)
        REQUESTS.append(
            {
                "ts": time.time(),
                "body": body,
                "stateVersion": version,
                "legalActions": legal_action_ids(body),
            }
        )

        response = SCRIPT.pop(0) if len(SCRIPT) > 1 else (SCRIPT[0] if SCRIPT else DEFAULT_RESPONSE)
        response = _fill(response, version)

        mode = response.get("mode")
        if mode == "hang":
            # Accept, then never answer. This is what an unplugged network looks
            # like from the client side -- not a refused connection.
            async def never() :
                while True:
                    await asyncio.sleep(3600)
                    yield b""

            return StreamingResponse(never(), media_type="text/event-stream")

        if mode == "error":
            return JSONResponse(
                status_code=int(response.get("status") or 500),
                content={"error": {"message": response.get("message") or "fake upstream error"}},
            )

        return StreamingResponse(_render(response), media_type="text/event-stream")

    return app


app = create_app()


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    args = parser.parse_args()
    # A long keep-alive: core's httpx client pools connections, and a server
    # that hangs up on an idle one surfaces as `ReadError` on the next health
    # probe, which reads as "the agent died" and flaps the mode mid-test.
    uvicorn.run(
        app,
        host="127.0.0.1",
        port=args.port,
        log_level="warning",
        timeout_keep_alive=300,
    )


if __name__ == "__main__":
    main()
