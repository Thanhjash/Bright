"""Execute one scenario x one variant — live, or replayed from a cassette.

**Cassettes are the reproducibility story.** A live pass records every raw SSE
response body to `evals/cassettes/<model>/<variant>.json`. Replay serves those
bytes back through `httpx.MockTransport`, so the *real* `DirectAgent` runs: the
same streaming parser, the same `validation.py`, the same executor seam. Only
the network is fake. That means:

  * re-running the table costs nothing and needs no key,
  * a grader change can be re-applied to old runs,
  * and a change to the agent's own parsing or validation shows up as a
    metric change on frozen model output, which is exactly what you want
    from a regression suite.

Latency is recorded during the live pass and replayed verbatim; it is measured
as **whole-turn wall clock** (what the class actually waits for), not
time-to-first-token.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import httpx
from bright_contracts import TurnContext

from bright_agent.base import Act, Done, TextDelta, ToolCall, ToolResult, TurnUsage
from bright_agent.direct import DirectAgent, LLMConfig
from bright_agent.tools import CHOOSE_NEXT, RECORD_OBSERVATION, SAY
from bright_agent.validation import REJECTION_LOG, Rejection, validate_call

from .scenarios import ExecutorSpec, Scenario
from .variants import Variant, parse_tier_c

CASSETTE_DIR = Path(__file__).resolve().parent / "cassettes"


# ------------------------------------------------------------------ trace


@dataclass
class Trace:
    """Everything one scenario run produced. The graders read only this."""

    scenario_id: str
    variant: str
    model: str
    text: str = ""
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    tool_results: list[dict[str, Any]] = field(default_factory=list)
    executor_calls: list[dict[str, Any]] = field(default_factory=list)
    rejections: list[dict[str, Any]] = field(default_factory=list)
    done_reason: str = "error"
    done_detail: str | None = None
    usage: dict[str, int] = field(default_factory=dict)
    latency_s: float = 0.0
    #: Tier C only: the object we parsed out of the completion.
    parsed: dict[str, Any] | None = None
    parse_error: str | None = None
    transport_error: str | None = None

    @property
    def chosen_action(self) -> str | None:
        for c in self.tool_calls:
            if c["name"] == CHOOSE_NEXT:
                v = c["arguments"].get("action_id")
                return v if isinstance(v, str) else None
        return None

    @property
    def said(self) -> str:
        """Everything the class would hear: `classroom_say` plus loose text.

        README weakness #3: the model usually speaks through the tool, so the
        TextDelta stream is often empty. Both paths reach the same TTS.
        """
        parts = [c["arguments"].get("text", "") for c in self.tool_calls if c["name"] == SAY]
        if self.text.strip():
            parts.append(self.text)
        return " ".join(p for p in parts if isinstance(p, str) and p.strip())

    @property
    def observations(self) -> list[dict[str, Any]]:
        return [c["arguments"] for c in self.tool_calls if c["name"] == RECORD_OBSERVATION]


# -------------------------------------------------------------- transports


class _Recorder(httpx.AsyncBaseTransport):
    """Passes requests through and keeps every response body verbatim."""

    def __init__(self, inner: httpx.AsyncBaseTransport) -> None:
        self.inner = inner
        self.responses: list[dict[str, Any]] = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        resp = await self.inner.handle_async_request(request)
        body = await resp.aread()
        await resp.aclose()
        self.responses.append({"status": resp.status_code, "body": body.decode("utf-8", "replace")})
        return httpx.Response(
            resp.status_code, content=body, headers={"content-type": "text/event-stream"}
        )


def _replay_transport(responses: list[dict[str, Any]]) -> httpx.MockTransport:
    """Serve recorded bodies in call order. A turn may span several rounds."""
    seq = list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        if not seq:
            raise RuntimeError("cassette exhausted: the agent made more calls than were recorded")
        r = seq.pop(0)
        return httpx.Response(
            r["status"],
            content=r["body"].encode(),
            headers={"content-type": "text/event-stream"},
        )

    return httpx.MockTransport(handler)


# --------------------------------------------------------------- executor


class _Executor:
    """Stand-in for classroom-core, driven by the scenario's ExecutorSpec."""

    def __init__(self, spec: ExecutorSpec) -> None:
        self.spec = spec
        self.calls: list[dict[str, Any]] = []

    async def __call__(self, name: str, arguments: dict[str, Any]) -> Any:
        self.calls.append({"name": name, "arguments": arguments})
        if name in self.spec.raises:
            raise RuntimeError(f"{name} failed: classroom-core rejected it")
        if name in self.spec.soft_errors:
            return self.spec.soft_errors[name]
        return self.spec.results.get(name, {"ok": True})


# ------------------------------------------------------------------- run


def _collect(trace: Trace, ev: Any) -> None:
    if isinstance(ev, TextDelta):
        trace.text += ev.text
    elif isinstance(ev, ToolCall):
        trace.tool_calls.append({"call_id": ev.call_id, "name": ev.name, "arguments": ev.arguments})
    elif isinstance(ev, ToolResult):
        trace.tool_results.append({"call_id": ev.call_id, "name": ev.name, "ok": ev.ok, "error": ev.error})
    elif isinstance(ev, Done):
        trace.done_reason = ev.reason
        trace.done_detail = ev.detail
        trace.usage = ev.usage.model_dump()
    elif isinstance(ev, Act):
        pass


async def _apply_tier_c(trace: Trace, ctx: TurnContext, executor: _Executor) -> None:
    """Tier C has no tool protocol, so we do the protocol ourselves.

    The parsed object is turned into the same tool calls the other variants
    make and pushed through the *same* `validate_call` and the *same*
    executor, so the graders cannot tell the difference. That is the point:
    the comparison must be about the decoding strategy, not the harness.
    """
    obj, err = parse_tier_c(trace.text)
    trace.parsed, trace.parse_error = obj, err
    if obj is None:
        trace.done_reason = "error"
        trace.done_detail = err
        return

    synthetic: list[tuple[str, dict[str, Any]]] = []
    if isinstance(obj.get("say"), str) and obj["say"].strip():
        synthetic.append((SAY, {"text": obj["say"]}))
    if isinstance(obj.get("observation"), dict):
        synthetic.append((RECORD_OBSERVATION, obj["observation"]))
    if obj.get("action_id") is not None:
        args: dict[str, Any] = {"action_id": obj.get("action_id")}
        if "state_version" in obj:
            args["state_version"] = obj["state_version"]
        if isinstance(obj.get("params"), dict):
            args["params"] = obj["params"]
        synthetic.append((CHOOSE_NEXT, args))

    trace.text = ""  # the JSON envelope is not speech; `said` comes from the say call
    for i, (name, args) in enumerate(synthetic):
        trace.tool_calls.append({"call_id": f"tierc_{i}", "name": name, "arguments": args})
        rej = validate_call(ctx, name, args)
        if rej is not None:
            trace.tool_results.append({"call_id": f"tierc_{i}", "name": name, "ok": False, "error": str(rej)})
            trace.done_reason = "error"
            trace.done_detail = str(rej)
            return
        try:
            result = await executor(name, args)
        except Exception as exc:  # noqa: BLE001
            trace.tool_results.append({"call_id": f"tierc_{i}", "name": name, "ok": False, "error": repr(exc)})
            trace.done_reason = "error"
            trace.done_detail = repr(exc)
            return
        trace.tool_results.append({"call_id": f"tierc_{i}", "name": name, "ok": True, "error": None})
        _ = result
    trace.done_reason = "complete" if synthetic else "no_action"


async def run_one(
    scenario: Scenario,
    variant: Variant,
    config: LLMConfig,
    *,
    recorded: list[dict[str, Any]] | None = None,
    recorded_latency: float | None = None,
) -> tuple[Trace, list[dict[str, Any]]]:
    """Run one cell. `recorded is not None` == replay, no network.

    Returns (trace, raw responses) so the caller can write a cassette.
    """
    trace = Trace(scenario.id, variant.name, config.model)
    executor = _Executor(scenario.executor)

    if recorded is not None:
        client = httpx.AsyncClient(transport=_replay_transport(recorded), timeout=5)
        recorder = None
    else:
        recorder = _Recorder(httpx.AsyncHTTPTransport(retries=0))
        client = httpx.AsyncClient(
            transport=recorder,
            timeout=httpx.Timeout(config.request_timeout_s, connect=config.connect_timeout_s),
        )

    agent = DirectAgent(
        executor,
        config,
        client=client,
        system_prompt=variant.system_prompt,
        tools_builder=variant.tools_builder,
        messages_builder=variant.messages_builder,
    )

    # REJECTION_LOG is a module-level ring, autouse-cleared only under pytest.
    # This harness is not pytest: snapshot the boundary explicitly or scenarios
    # contaminate each other.
    mark = len(REJECTION_LOG)
    t0 = time.perf_counter()
    try:
        async for ev in agent.turn(scenario.ctx):
            _collect(trace, ev)
        if variant.mode == "json" and trace.done_reason in ("complete", "no_action"):
            await _apply_tier_c(trace, scenario.ctx, executor)
    except Exception as exc:  # noqa: BLE001 - harness must never die on one cell
        trace.transport_error = repr(exc)
        trace.done_reason = "error"
        trace.done_detail = repr(exc)
    finally:
        await client.aclose()

    trace.latency_s = recorded_latency if recorded_latency is not None else time.perf_counter() - t0
    trace.executor_calls = executor.calls
    trace.rejections = [
        r.model_dump() if isinstance(r, Rejection) else dict(r) for r in REJECTION_LOG[mark:]
    ]
    del REJECTION_LOG[mark:]
    return trace, (recorder.responses if recorder else [])


# -------------------------------------------------------------- cassettes


def cassette_path(model: str, variant: str) -> Path:
    return CASSETTE_DIR / model.replace("/", "_") / f"{variant}.json"


def load_cassette(model: str, variant: str) -> dict[str, Any]:
    p = cassette_path(model, variant)
    if not p.is_file():
        return {}
    return json.loads(p.read_text(encoding="utf-8"))


def save_cassette(model: str, variant: str, data: dict[str, Any]) -> Path:
    p = cassette_path(model, variant)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")
    return p


# ------------------------------------------------------------------ suite


async def run_suite(
    scenarios: Iterable[Scenario],
    variant: Variant,
    config: LLMConfig,
    *,
    live: bool,
    concurrency: int = 6,
    on_progress: Any = None,
) -> list[Trace]:
    """One variant across the corpus. Live records a cassette; otherwise replay."""
    scenarios = list(scenarios)
    cassette = {} if live else load_cassette(config.model, variant.name)
    if not live and not cassette:
        raise FileNotFoundError(
            f"no cassette for model={config.model} variant={variant.name}. "
            f"Record one with --live (expected {cassette_path(config.model, variant.name)})."
        )

    sem = asyncio.Semaphore(concurrency)
    out: dict[str, Trace] = {}
    fresh: dict[str, Any] = {}

    async def one(sc: Scenario) -> None:
        async with sem:
            if live:
                trace, raw = await run_one(sc, variant, config)
                fresh[sc.id] = {"responses": raw, "latency_s": round(trace.latency_s, 3)}
            else:
                cell = cassette.get(sc.id)
                if cell is None:
                    trace = Trace(sc.id, variant.name, config.model,
                                  done_reason="error", done_detail="not in cassette")
                else:
                    trace, _ = await run_one(
                        sc, variant, config,
                        recorded=cell["responses"], recorded_latency=cell.get("latency_s"),
                    )
            out[sc.id] = trace
            if on_progress:
                on_progress(trace)

    await asyncio.gather(*(one(s) for s in scenarios))

    if live:
        save_cassette(config.model, variant.name, fresh)
    return [out[s.id] for s in scenarios]


__all__ = ["Trace", "run_one", "run_suite", "cassette_path", "load_cassette", "save_cassette"]
