"""V3 answer-station energy endpointing in Chromium."""

from __future__ import annotations

import pytest

from harness import run_scenario

pytestmark = [pytest.mark.browser]


@pytest.mark.itest(id="V3-VOICE", title="Answer-station endpoint outcomes")
def test_conservative_endpoint_outcomes(ui):
    out = run_scenario("v3_capture_endpoint", {"uiOrigin": ui.origin}, timeout=90)
    assert out.get("ok"), f"scenario failed: {out.get('error')}\nlog: {out.get('_log')}"
    assert out["cases"]["firstFrameResult"] is None
    assert out["cases"]["firstFrameHasSpeech"] is False
    assert out["cases"]["preDeadlineResult"] is None
    assert out["cases"]["silence"]["outcome"] == "no_speech"
    assert out["cases"]["isolatedNoise"]["outcome"] == "noise_only"
    assert out["cases"]["speech"]["outcome"] == "speech"
    assert out["cases"]["speech"]["reason"] == "end_silence"
    assert out["cases"]["hardCap"]["outcome"] == "speech"
    assert out["cases"]["hardCap"]["reason"] == "max_duration"
    assert not out["pageErrors"]
