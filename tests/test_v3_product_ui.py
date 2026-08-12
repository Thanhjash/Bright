from __future__ import annotations

import pytest

from harness import run_scenario

pytestmark = [pytest.mark.browser, pytest.mark.slow]


def test_stage_control_persistent_product_composition(core, ui, tts):
    out = run_scenario(
        "v3_product_ui",
        {"uiOrigin": ui.origin, "coreHttp": core.http},
        timeout=180,
    )
    assert out.get("ok"), f"scenario failed: {out.get('error')}\nlog: {out.get('_log')}"
    assert out["audioLeaseOwners"] == 1, "duplicate Stage acquired physical audio ownership"
    assert out["broadcastActivity"]["phase"] == "listening"
    assert out["broadcastActivity"]["assignmentId"] == "assignment-e2e"
    assert out["startEnabled"] is True
    assert out["rosterCount"] >= 1
    assert out["overflow1366"]["x"] is False
    assert out["overflow1024"]["x"] is False
    assert out["focusVisible"] is True
    assert not out["pageErrors"]
