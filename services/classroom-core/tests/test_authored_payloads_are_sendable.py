"""Every `show_exercise` payload a unit authors must actually be sendable.

Both the tool description and `exercises.md` itself tell her to copy a block
whole and send it -- "A block that has been retyped from memory is a wasted
round-trip a child sits through." That instruction is only honest if the blocks
satisfy the schema the provider is given AND the validators Core enforces.

They did not. `ex.4`'s two items are picture choices -- `id` + `asset`, no
`text` -- while the wire declared `required: ["id", "text"]` on every option.
A provider that hard-validates a function declaration rejects that call
outright; one that does not invites the model to invent a caption for a
picture. Core's own `_validate_arguments` could not see it either, because the
subset it implements does not descend into array items -- so the contradiction
sat between two files that each looked right alone.

This runs every authored block through both gates, so "never called" can never
again quietly mean "never callable".
"""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from mcp_server import wire_tools
from teacher_os import TeacherOS

ROOT = Path(__file__).resolve().parents[3]
UNITS = ROOT / "content" / "library" / "units"

_BLOCK = re.compile(r"```json\n(.*?)\n```", re.DOTALL)


def _authored_payloads() -> list[tuple[str, int, dict]]:
    """Every fenced JSON block in every unit's exercises.md, in file order."""
    found: list[tuple[str, int, dict]] = []
    for path in sorted(UNITS.glob("*/exercises.md")):
        text = path.read_text(encoding="utf-8")
        for index, raw in enumerate(_BLOCK.findall(text)):
            found.append((path.parent.name, index, json.loads(raw)))
    return found


PAYLOADS = _authored_payloads()


def _wire_schema() -> dict:
    return next(t for t in wire_tools() if t["name"] == "show_exercise")["inputSchema"]


def test_there_are_payloads_to_check() -> None:
    """A silent zero here would make every assertion below vacuously true."""
    assert PAYLOADS, f"no ```json blocks found under {UNITS}"


@pytest.mark.parametrize("unit,index,payload", PAYLOADS)
def test_payload_matches_the_schema_the_provider_is_given(
    unit: str, index: int, payload: dict
) -> None:
    """Descends into array items, which `_validate_arguments` deliberately does not.

    This is the check that was missing. The gap it covers is not hypothetical:
    it is the exact shape of the two bugs that kept show_exercise at zero calls
    for four periods -- an untyped `content: {}`, then a `required` naming a
    field half the authored blocks correctly omit.
    """
    schema = _wire_schema()
    properties = schema["properties"]

    # `turn_id` is on every tool and is the one field a block deliberately
    # omits -- exercises.md says so in its first sentence: "exactly the
    # arguments for show_exercise, minus turn_id". Core stamps it at call time.
    for key in schema.get("required", []):
        if key == "turn_id":
            continue
        assert key in payload, f"{unit} block {index}: missing required {key!r}"
    unknown = sorted(set(payload) - set(properties))
    assert not unknown, f"{unit} block {index}: fields not on the wire: {unknown}"

    for key, value in payload.items():
        rule = properties[key]
        if rule.get("type") != "array":
            continue
        assert isinstance(value, list), f"{unit} block {index}: {key} must be a list"
        item_rule = rule.get("items") or {}
        if item_rule.get("type") != "object":
            continue
        for entry in value:
            for needed in item_rule.get("required", []):
                assert needed in entry, (
                    f"{unit} block {index}: {key}[] entry {entry!r} omits {needed!r}, "
                    "which the wire schema declares required -- a provider will "
                    "refuse this call, and she was told to send the block whole"
                )


@pytest.mark.parametrize("unit,index,payload", PAYLOADS)
def test_core_accepts_the_payload_it_was_handed(
    unit: str, index: int, payload: dict
) -> None:
    """The other gate: Core's per-kind validators, run for real.

    Whatever a unit prints, Core must accept -- the same rule the ASSETS=
    round-trip test asserts for asset ids.
    """
    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id="sess-payload",
        store=SimpleNamespace(set_scene=lambda kind, props: {"kind": kind, "props": props}),
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
    )
    os_ = TeacherOS(core, unit_id=unit, learner_id="learner-1")

    got = asyncio.run(os_.execute("show_exercise", dict(payload)))
    assert got.get("ok") is True, (
        f"{unit} block {index} ({payload.get('kind')}): Core refused a payload its "
        f"own unit authored -- {got.get('reason')!r}"
    )
