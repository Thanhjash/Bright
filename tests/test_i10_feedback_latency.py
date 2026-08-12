"""I10 — interaction → visual feedback under 100 ms (NS-2, reflex tier).

The number is the product's promise: a child taps and the screen responds
before they can wonder whether it worked. It is asserted on the frame that
would actually be painted, not on when a React state setter ran.

Measured over several rounds and gated on the worst one, because a 60 ms
median with a 400 ms outlier is exactly what a room of children notices.
"""

from __future__ import annotations

import pytest

from harness import run_scenario

pytestmark = [pytest.mark.browser, pytest.mark.slow]

BUDGET_MS = 100


@pytest.mark.itest(id="I10", title="Interaction → visual feedback under 100 ms")
async def test_press_feedback_is_under_100ms(core, ui, tts):
    out = run_scenario(
        "i10_feedback_latency",
        {"uiOrigin": ui.origin, "coreHttp": core.http, "rounds": 3},
        timeout=300,
    )
    assert out.get("ok"), f"scenario failed: {out.get('error')}\nlog: {out.get('_log')}"

    samples = out["samples"]
    assert len(samples) >= 3, f"only {len(samples)} measurements"

    paints = [s["paintMs"] for s in samples]
    assert all(p is not None for p in paints), (
        f"a tap produced no visible press state at all: {samples}"
    )
    worst = max(paints)
    assert worst < BUDGET_MS, (
        f"slowest tap→painted-feedback was {worst:.0f}ms (budget {BUDGET_MS}ms). "
        f"all samples: {[round(p, 1) for p in paints]}"
    )

    # Context, not a gate: the graded reveal comes back from core.
    reveals = [s["revealMs"] for s in samples if s["revealMs"] is not None]
    assert reveals, "no answer was ever graded"
    assert max(reveals) < 1500, f"answer→reveal round trip {max(reveals)}ms: {reveals}"

    assert not out["pageErrors"], f"uncaught errors in the page: {out['pageErrors']}"
