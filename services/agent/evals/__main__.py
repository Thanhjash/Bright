"""One command.

    python -m evals                          # replay cassettes, print the table
    python -m evals --live                   # hit the endpoint, re-record
    python -m evals --live --models mimo-v2.5-pro,mimo-v2.5 \
                    --variants baseline,static_schema,lean_tools,tier_c,degraded_prompt
    python -m evals --cache-probe --live     # the prefix-cache experiment
    python -m evals --failures               # what actually went wrong

Temperature is pinned to 0.0 for every cell so variants are comparable;
production runs 0.3. Streaming is on, because that is the production path.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
from pathlib import Path
from typing import Any

_AGENT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_AGENT_DIR))
# `services/agent/conftest.py` already puts packages/contracts/python on the
# path and loads the repo .env without overriding real env vars. Outside
# pytest nothing imports it for us, so do it here rather than duplicating the
# bootstrap (and the key stays in the environment, never in this file).
import conftest as _bootstrap  # noqa: E402,F401

from bright_agent.direct import LLMConfig  # noqa: E402
from bright_agent.tools import build_tools  # noqa: E402

from . import graders, report, variants  # noqa: E402
from .runner import run_suite  # noqa: E402
from .scenarios import CLASSES, all_scenarios  # noqa: E402

DEFAULT_MODELS = ("mimo-v2.5-pro",)
EVAL_TEMPERATURE = 0.0


def _config(model: str) -> LLMConfig:
    c = LLMConfig.from_env()
    c.model = model
    c.temperature = EVAL_TEMPERATURE
    return c


def _tools_for(variant: variants.Variant, scenario: Any) -> list[dict[str, Any]]:
    builder = variant.tools_builder
    return builder(scenario.ctx) if builder is not None else build_tools(scenario.ctx)


async def _run_cell(scenarios, variant, model, live, concurrency, quiet):
    cfg = _config(model)
    t0 = time.perf_counter()
    done = {"n": 0}

    def progress(_tr):
        done["n"] += 1
        if not quiet and live:
            print(f"\r  {model}/{variant.name}: {done['n']}/{len(scenarios)}", end="", file=sys.stderr)

    traces = await run_suite(scenarios, variant, cfg, live=live, concurrency=concurrency, on_progress=progress)
    if not quiet and live:
        print(f"\r  {model}/{variant.name}: {len(scenarios)}/{len(scenarios)} "
              f"in {time.perf_counter()-t0:.0f}s", file=sys.stderr)
    return [graders.grade(sc, tr, _tools_for(variant, sc)) for sc, tr in zip(scenarios, traces)]


# ----------------------------------------------------------- cache probe


async def cache_probe(models: list[str], variant_names: list[str]) -> str:
    """Does the tool block bust the prefix cache when actions change?

    Strictly sequential — concurrency destroys cache warmness, so this cannot
    live inside the scenario matrix. Four calls per (model, variant):

        A, A  (identical turn twice)      -> the ceiling
        A, B  (same turn, actions changed) -> what a real lesson does

    The number that matters is `cached` on the second call of the A->B pair.
    """
    from bright_contracts import AvailableAction

    from .runner import run_one
    from .scenarios import Scenario, ctx as make_ctx

    base_actions = [
        AvailableAction(id="next_activity", label="advance to sentence_builder"),
        AvailableAction(id="repeat_activity", label="repeat vocabulary_grid"),
        AvailableAction(id="scaffold_down", label="drop to image support"),
    ]
    changed_actions = [
        AvailableAction(id="open_explore", label="open EXPLORE on 'penguin'"),
        AvailableAction(id="start_roleplay", label="start market roleplay"),
        AvailableAction(id="end_lesson", label="finish the lesson"),
    ]
    props = {"prompt": "Which one is the apple?",
             "options": [{"id": "o1", "text": "apple"}, {"id": "o2", "text": "banana"}]}
    A = Scenario("cache_A", "tool_routing", make_ctx(props=props, actions=base_actions))
    B = Scenario("cache_B", "tool_routing", make_ctx(props=props, actions=changed_actions))

    lines = ["", "PREFIX CACHE — sequential, 4 calls per cell", "=" * 78,
             f"{'model':<14} {'variant':<15} {'pair':<12} {'prompt':>7} {'cached':>7} {'hit%':>6}"]
    for model in models:
        cfg = _config(model)
        for vname in variant_names:
            v = variants.get(vname)
            for label, (first, second) in (("A -> A", (A, A)), ("A -> B (acts changed)", (A, B))):
                usages = []
                for sc in (first, second):
                    tr, _ = await run_one(sc, v, cfg)
                    usages.append(tr.usage)
                u = usages[1]
                p, c = u.get("prompt_tokens", 0), u.get("cached_tokens", 0)
                lines.append(f"{model:<14} {vname:<15} {label:<22} {p:>7} {c:>7} "
                             f"{(100.0*c/p if p else 0):>5.0f}%")
    lines.append("=" * 78)
    return "\n".join(lines)


# ------------------------------------------------------------------ main


async def amain(args) -> int:
    scenarios = all_scenarios()
    if args.classes:
        keep = set(args.classes.split(","))
        scenarios = [s for s in scenarios if s.cls in keep]
    if args.sample:
        scenarios = scenarios[: args.sample]
    if args.only:
        scenarios = [s for s in scenarios if args.only in s.id]

    models = [m.strip() for m in (args.models or ",".join(DEFAULT_MODELS)).split(",") if m.strip()]
    vnames = [v.strip() for v in (args.variants or ",".join(variants.DEFAULT_VARIANTS)).split(",") if v.strip()]

    if args.cache_probe:
        if not args.live:
            print("--cache-probe requires --live (it measures the provider's cache).", file=sys.stderr)
            return 2
        print(await cache_probe(models, vnames))
        return 0

    if args.live and not os.environ.get("LLM_API_KEY"):
        print("LLM_API_KEY not set.", file=sys.stderr)
        return 2

    print(f"scenarios: {len(scenarios)}  "
          f"({', '.join(f'{c}={sum(1 for s in scenarios if s.cls==c)}' for c in CLASSES)})")
    print(f"models: {models}   variants: {vnames}   mode: {'LIVE' if args.live else 'replay'}   "
          f"temperature: {EVAL_TEMPERATURE}\n")

    matrix: list[tuple[str, str, Any, Any]] = []
    all_graded: dict[str, list[graders.Graded]] = {}

    for model in models:
        for vname in vnames:
            v = variants.get(vname)
            try:
                g = await _run_cell(scenarios, v, model, args.live, args.concurrency, args.quiet)
            except FileNotFoundError as exc:
                print(f"  skip {model}/{vname}: {exc}", file=sys.stderr)
                continue
            key = f"{model}|{vname}"
            all_graded[key] = g
            ms = report.class_metrics(g)
            matrix.append((model, vname, ms[CLASSES.index("tool_routing")], ms[-1]))
            if args.per_class:
                print(report.per_class_table(ms, f"\n{model} / {vname}  — {v.note}"))
                print()

    if not matrix:
        print("nothing ran.", file=sys.stderr)
        return 1

    print("\nSP-3 MATRIX")
    print(report.matrix_table(matrix))

    if args.failures:
        for key, g in all_graded.items():
            print(f"\n--- failures: {key}")
            print(report.failures(g))

    if args.json_out:
        payload = {
            key: {
                "metrics": [m.__dict__ for m in report.class_metrics(g)],
                "scenarios": [
                    {
                        "id": x.scenario.id, "cls": x.scenario.cls, "ok": x.ok,
                        "chosen": x.trace.chosen_action, "accept": sorted(x.scenario.accept),
                        "selection_ok": x.selection_ok, "args_ok": x.args_ok,
                        "hallucinated": x.hallucinated, "violations": x.violations,
                        "done": x.trace.done_reason, "said": x.trace.said[:200],
                        "usage": x.trace.usage, "latency_s": round(x.trace.latency_s, 3),
                    }
                    for x in g
                ],
            }
            for key, g in all_graded.items()
        }
        Path(args.json_out).write_text(json.dumps(payload, indent=1), encoding="utf-8")
        print(f"\nwrote {args.json_out}")

    worst = min(m[2].selection_accuracy for m in matrix)
    return 0 if worst >= report.KILL_THRESHOLD or not args.strict else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m evals", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", action="store_true", help="hit the real endpoint and re-record cassettes")
    ap.add_argument("--models", default=None, help="comma-separated (default mimo-v2.5-pro)")
    ap.add_argument("--variants", default=None, help=f"comma-separated from {sorted(variants.ALL)}")
    ap.add_argument("--classes", default=None, help="comma-separated subset of the five classes")
    ap.add_argument("--only", default=None, help="substring match on scenario id")
    ap.add_argument("--sample", type=int, default=0, help="first N scenarios only")
    ap.add_argument("--concurrency", type=int, default=6)
    ap.add_argument("--per-class", action="store_true", help="print the per-class table for every cell")
    ap.add_argument("--failures", action="store_true", help="list every failing scenario")
    ap.add_argument("--cache-probe", action="store_true", help="run the prefix-cache experiment instead")
    ap.add_argument("--json-out", default=None)
    ap.add_argument("--quiet", action="store_true")
    ap.add_argument("--strict", action="store_true", help="exit 1 if any cell trips the SP-3 kill criterion")
    args = ap.parse_args(argv)
    return asyncio.run(amain(args))


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
