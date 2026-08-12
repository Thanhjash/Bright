"""I3 — reload the tab mid-activity. Resnapshot resumes; it does not restart.

Run in a real Chromium against the real Vite dev server, because the thing
being tested is the React lifecycle meeting the socket lifecycle — the exact
seam that produced "two WS connections, stage frozen" and that no fake-socket
unit test could see.

State is read from `window.__bright` (the app's own Zustand store), not from
the DOM, so the assertions are about what the app believes rather than what a
screenshot happens to show.
"""

from __future__ import annotations

import pytest

from harness import run_scenario

pytestmark = [pytest.mark.browser, pytest.mark.slow]


@pytest.mark.itest(id="I3", title="Reload mid-activity: resnapshot resumes the exact activity")
async def test_reload_resumes_the_same_activity(core, ui, tts):
    core.control("resume")
    out = run_scenario(
        "i3_reload",
        {"uiOrigin": ui.origin, "coreHttp": core.http},
        timeout=240,
    )
    assert out.get("ok"), f"scenario failed: {out.get('error')}\nlog: {out.get('_log')}"

    # One page load opens exactly one socket (the two-connection bug).
    assert out["connectionsForOnePageLoad"] == 1, (
        f"one page load opened {out['connectionsForOnePageLoad']} WebSocket connections; "
        "a second connection produces a false seq gap and freezes the stage"
    )

    # The reload did not restart the class.
    assert out["indexAfter"] == out["indexBefore"], (
        f"core's lesson position moved from {out['indexBefore']} to {out['indexAfter']} "
        "because a tab was reloaded"
    )

    # The board came back to the same activity, not to activity 0.
    assert out["awaitingSnapshot"] is False, "the UI never received a snapshot after reloading"
    assert out["uiSceneAfter"] == out["sceneBefore"] == "choice"
    assert out["uiIndexAfter"] == out["uiIndexBefore"], (
        f"after the reload the UI is on activity {out['uiIndexAfter']}, "
        f"it was on {out['uiIndexBefore']} — the lesson restarted"
    )
    assert out["promptAfter"] == out["promptBefore"], (
        "the question on the board changed across a reload: "
        f"{out['promptBefore']!r} → {out['promptAfter']!r}"
    )
    assert out["uiVersionAfter"] >= out["versionBefore"]

    # And the reload retired the old socket instead of stacking a second.
    assert out["clientsAfterReload"] == out["clientsBeforeReload"], (
        f"after reloading one tab core holds {out['clientsAfterReload']} connections "
        f"(it held {out['clientsBeforeReload']} before)"
    )

    assert not out["pageErrors"], f"uncaught errors in the page: {out['pageErrors']}"
    core.control("pause")
