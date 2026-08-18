"""Does this provider support grammar-constrained decoding?

docs/design/architecture.md §3 states a **hard requirement**: an invalid
`action_id` must be *impossible to emit*, not merely rejected. Today the
`enum` in the tool schema is a strong hint plus a hard reject
(README "Known weaknesses" #2). This script answers, reproducibly, whether
the Phase 1 endpoint closes that gap — because the answer decides the
Phase 3 serving layer (OVMS vs llama.cpp, architecture §3 / SP-2).

Method: **falsification, not acceptance.** A provider that silently ignores
an unknown field still returns HTTP 200 with a sensible answer, so "it
worked" proves nothing. Every probe therefore sets a constraint that
*contradicts* what the model would naturally say:

    prompt:     "What is 2+2? Answer in JSON."
    constraint: the only legal output is {"zqx": "purple_elephant"}

If the constraint is enforced by the decoder, the model **cannot** answer 4.
If we see `{"answer": 4}` the constraint was not applied to sampling.

Run:  .venv/bin/python -m evals.probe_provider [--model mimo-v2.5-pro]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from dataclasses import dataclass
from typing import Any

import httpx

# --------------------------------------------------------------- fixtures

#: A neutral question. Deliberately NOT an instruction to echo something --
#: an adversarial "output exactly this" prompt triggers a refusal on MiMo,
#: and a refusal is indistinguishable from an enforced constraint failing.
NEUTRAL_PROMPT = "What is 2+2? Answer in JSON."

#: Only one string is legal. The model wants to say 4.
CONST_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"zqx": {"type": "string", "const": "purple_elephant"}},
    "required": ["zqx"],
    "additionalProperties": False,
}

#: The shape `classroom_choose_next` actually uses: a one-member string enum.
ENUM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {"action_id": {"type": "string", "enum": ["zzz_gamma"]}},
    "required": ["action_id"],
    "additionalProperties": False,
}

#: The sentinel values that can ONLY appear if the decoder was constrained.
SENTINELS = ("purple_elephant", "zzz_gamma")


@dataclass
class Probe:
    name: str
    body: dict[str, Any]
    #: What the field claims to do, for the report.
    claim: str


def _probes(schema: dict[str, Any], label: str) -> list[Probe]:
    return [
        Probe(
            f"response_format=json_schema ({label})",
            {"response_format": {"type": "json_schema", "json_schema": {"name": "p", "schema": schema}}},
            "OpenAI structured outputs",
        ),
        Probe(
            f"response_format=json_schema strict ({label})",
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "p", "strict": True, "schema": schema},
                }
            },
            "OpenAI structured outputs, strict",
        ),
        Probe(f"guided_json ({label})", {"guided_json": schema}, "vLLM guided decoding"),
        Probe(
            f"tool arg enum ({label})",
            {
                "tools": [{"type": "function", "function": {"name": "pick", "parameters": schema}}],
                "tool_choice": {"type": "function", "function": {"name": "pick"}},
            },
            "tool-schema enum -- what bright_agent ships today",
        ),
    ]


EXTRA_PROBES = [
    Probe("guided_choice", {"guided_choice": list(SENTINELS)}, "vLLM guided choice"),
    Probe("guided_regex", {"guided_regex": "zzz_gamma"}, "vLLM guided regex"),
    Probe("guided_grammar", {"guided_grammar": 'root ::= "zzz_gamma"'}, "vLLM GBNF grammar"),
]


# ------------------------------------------------------------- execution


def _extract(message: dict[str, Any]) -> str:
    out = message.get("content") or ""
    if message.get("tool_calls"):
        out += json.dumps(message["tool_calls"])
    return out


def run_probe(
    client: httpx.Client, url: str, headers: dict[str, str], model: str, probe: Probe, *, thinking: bool
) -> dict[str, Any]:
    """One probe. `thinking=False` sends the top-level disable switch."""
    body: dict[str, Any] = {
        "model": model,
        # A nonce defeats any response cache in front of the model.
        "messages": [{"role": "user", "content": f"[{uuid.uuid4().hex[:8]}] {NEUTRAL_PROMPT}"}],
        "max_tokens": 80,
        "temperature": 0.0,
    }
    if not thinking:
        # TOP-LEVEL. See README "The `thinking` trap".
        body["thinking"] = {"type": "disabled"}
    body.update(probe.body)

    try:
        r = client.post(url, json=body, headers=headers)
    except httpx.HTTPError as exc:
        return {"probe": probe.name, "status": "transport", "verdict": "ERROR", "detail": repr(exc)}

    if r.status_code != 200:
        return {
            "probe": probe.name,
            "status": r.status_code,
            # A 400 means the field was *parsed*. That is itself information.
            "verdict": "REJECTED",
            "detail": r.text[:200],
        }

    got = _extract(r.json()["choices"][0]["message"])
    enforced = any(s in got for s in SENTINELS)
    return {
        "probe": probe.name,
        "status": 200,
        "verdict": "ENFORCED" if enforced else "IGNORED",
        "detail": got[:120],
    }


def probe_field_is_parsed(client: httpx.Client, url: str, headers: dict[str, str], model: str) -> list[str]:
    """Does the gateway *parse* these fields, or drop them unread?

    Sending a deliberately uncompilable schema separates the two: a server
    that builds a grammar must fail; a server that drops the field returns 200.
    """
    notes: list[str] = []
    cases = [
        (
            "response_format.json_schema with an invalid type",
            {"response_format": {"type": "json_schema", "json_schema": {"name": "p", "schema": {"type": "bogus_type"}}}},
        ),
        (
            "response_format.json_schema with an unparseable regex",
            {
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {
                        "name": "p",
                        "schema": {"type": "object", "properties": {"x": {"type": "string", "pattern": "(((("}}},
                    },
                }
            },
        ),
        ("guided_json set to a garbage string", {"guided_json": "!!! not a schema !!!"}),
    ]
    for label, extra in cases:
        body: dict[str, Any] = {
            "model": model,
            "messages": [{"role": "user", "content": "hi"}],
            "max_tokens": 16,
            "thinking": {"type": "disabled"},
        }
        body.update(extra)
        r = client.post(url, json=body, headers=headers)
        if r.status_code == 200:
            notes.append(f"  {label}: HTTP 200 -- field accepted unread (not compiled)")
        else:
            msg = ""
            try:
                msg = r.json()["error"]["message"][:150].replace("\n", " ")
            except Exception:  # noqa: BLE001
                msg = r.text[:150]
            notes.append(f"  {label}: HTTP {r.status_code} -- {msg}")
    return notes


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--model", default=None, help="defaults to $LLM_MODEL")
    ap.add_argument("--also-model", default=None, help="a second model to cross-check, e.g. mimo-v2.5")
    ap.add_argument("--json", action="store_true", help="emit machine-readable results")
    args = ap.parse_args(argv)

    base = os.environ.get("LLM_BASE_URL", "").rstrip("/")
    key = os.environ.get("LLM_API_KEY", "")
    if not base or not key:
        print("LLM_BASE_URL / LLM_API_KEY not set (repo .env is loaded by conftest).", file=sys.stderr)
        return 2

    url = f"{base}/chat/completions"
    headers = {"content-type": "application/json", "api-key": key, "authorization": f"Bearer {key}"}
    models = [m for m in (args.model or os.environ.get("LLM_MODEL", "mimo-v2.5-pro"), args.also_model) if m]

    probes = _probes(CONST_SCHEMA, "const") + _probes(ENUM_SCHEMA, "enum") + EXTRA_PROBES
    results: dict[str, Any] = {"base_url": base, "models": {}}

    with httpx.Client(timeout=90) as client:
        print("\nAvailable models:")
        try:
            for m in client.get(f"{base}/models", headers=headers).json().get("data", []):
                print(f"  {m.get('id')}")
        except Exception as exc:  # noqa: BLE001
            print(f"  (listing failed: {exc!r})")

        print("\nIs the constraint field parsed at all?")
        parse_notes = probe_field_is_parsed(client, url, headers, models[0])
        for n in parse_notes:
            print(n)
        results["parsed"] = parse_notes

        for model in models:
            # `thinking` is the one untested confound: some gateways skip the
            # grammar mask while a reasoning path is active. Test both.
            for thinking in (False, True):
                mode = "thinking ON" if thinking else "thinking disabled"
                print(f"\n{model} -- {mode}")
                print(f"  {'probe':44s} {'verdict':10s} output")
                rows = []
                for p in probes:
                    res = run_probe(client, url, headers, model, p, thinking=thinking)
                    rows.append(res)
                    print(f"  {res['probe']:44s} {res['verdict']:10s} {res['detail'][:70]!r}")
                results["models"][f"{model}|{mode}"] = rows

    enforced = [
        r["probe"]
        for rows in results["models"].values()
        for r in rows
        if r["verdict"] == "ENFORCED"
    ]
    print("\n" + "=" * 78)
    if enforced:
        print("VERDICT: grammar-constrained decoding IS available via:")
        for e in sorted(set(enforced)):
            print(f"  - {e}")
    else:
        print("VERDICT: NO grammar-constrained decoding on this endpoint.")
        print("  Every constraint was ignored by the sampler under falsification.")
        print("  architecture.md §3's hard requirement (an invalid action_id must be")
        print("  impossible to emit) is UNMET in Phase 1. Rejection is the only guarantee.")
    print("=" * 78)

    if args.json:
        print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
