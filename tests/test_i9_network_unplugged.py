"""I9 — unplug the network mid-lesson. Degrade, do not hang.

Phase 1 has exactly one outbound host: the model API. "Unplug the network"
therefore means that link, and the failure mode that matters is not a refused
connection — it is the polite one. A dropped route, a captive portal, a router
that stopped forwarding: TCP connects, the request goes out, and nothing ever
comes back. The client believes it is fine and waits forever.

That is what `blackhole()` does here: the connection is accepted and then
answered with silence. Anything that only survives ECONNREFUSED will hang on
this, and a hang in front of a class is worse than an error.

The risk register calls this "offline promise quietly dies". This test is the
thing that makes it noisy.
"""

from __future__ import annotations

import os
import time

import pytest

from harness import BusClient
from harness import llm_script as script

pytestmark = pytest.mark.slow


@pytest.mark.itest(id="I9", title="Network unplugged: degrades, never hangs")
async def test_turn_against_a_silent_network_is_bounded(core, llm, llm_link):
    """A blackholed link must not hold a turn open indefinitely."""
    core.start_lesson(0)
    llm.script([script.text("hi")])

    llm_link.blackhole()

    t0 = time.monotonic()
    result = core.agent_turn(timeout=90)
    elapsed = time.monotonic() - t0

    assert result["applied"] is False
    assert result["rejected"], "a turn into a black hole reported success"
    assert elapsed < 25, (
        f"the agent waited {elapsed:.1f}s on a silent network. "
        "A bounded timeout is the difference between degrading and hanging."
    )
    assert core.health()["status"] == "ok"
    core.control("pause")


@pytest.mark.itest(id="I9", title="Network unplugged: degrades, never hangs")
async def test_lesson_survives_the_network_going_away(core, llm, llm_link):
    lesson = core.lesson()
    activity_ids = [a["id"] for a in lesson["activities"]]

    client = BusClient(core.ws)
    await client.connect()
    core.start_lesson(0)
    await client.wait_for_scene("vocabulary", timeout=40)

    llm_link.blackhole()  # the cable comes out here

    choice = await client.wait_for_scene("choice", timeout=60)
    assert choice["props"]["options"]

    t0 = time.monotonic()
    await client.choose("cat")
    await client.wait_for(
        "scene.update",
        timeout=15,
        predicate=lambda e: bool((e["payload"].get("props") or {}).get("revealed")),
    )
    reflex_ms = (time.monotonic() - t0) * 1000
    assert reflex_ms < 1000, (
        f"grading took {reflex_ms:.0f}ms with the network down — the reflex tier "
        "is supposed to be independent of the agent entirely (NS-2)"
    )

    await client.wait_for(
        "lesson.position",
        timeout=45,
        predicate=lambda e: e["payload"]["activityIndex"] == activity_ids.index("q_legs"),
    )
    await client.choose("two")
    await client.wait_for(
        "lesson.position", timeout=60, predicate=lambda e: e["payload"]["stage"] == "DONE"
    )

    client.assert_clean()
    assert core.health()["status"] == "ok"
    await client.close()


@pytest.mark.itest(id="I9", title="Network unplugged: degrades, never hangs")
async def test_a_slow_network_does_not_stall_the_class(core, llm, llm_link):
    """Not down, just terrible — the case a naive timeout misses.

    The model answers eventually, but far outside the FULL budget. Core must
    still be serving, and the reflex tier must still be instant, while the turn
    is in flight.
    """
    import asyncio

    core.start_lesson(2)  # q_meow
    llm.script([script.slow(30, script.text("finally"))])

    turn = asyncio.create_task(asyncio.to_thread(core.agent_turn, None, 90))
    await asyncio.sleep(0.5)

    t0 = time.monotonic()
    outcome = core.interaction("interaction.choice", {"optionId": "cat"})
    reflex_ms = (time.monotonic() - t0) * 1000
    assert outcome["outcome"] == "correct"
    assert reflex_ms < 500, f"a slow agent turn blocked grading for {reflex_ms:.0f}ms"

    result = await turn
    assert result["applied"] is False
    assert core.health()["status"] == "ok"
    core.control("pause")


@pytest.mark.browser
@pytest.mark.itest(id="I9", title="Network unplugged: degrades, never hangs")
async def test_stage_survives_a_closed_link(core, ui, tts, proxy):
    """The projector's own link, closed under it.

    Everything above tests core's side of the seam. This tests the side a
    classroom actually looks at.
    """
    from harness import run_scenario

    core.control("resume")
    out = run_scenario(
        "i9_ui_offline",
        {
            "uiOrigin": ui.origin,
            "coreHttp": core.http,
            "linkControl": proxy.control_url,
            "blackholeWaitMs": int(os.environ.get("BRIGHT_I9_BLACKHOLE_MS", "70000")),
        },
        timeout=360,
    )
    globals()["_I9_UI_RESULT"] = out
    assert out.get("ok"), f"scenario failed: {out.get('error')}\nlog: {out.get('_log')}"

    cut = out["cut"]
    assert cut["connectionState"] != "open"
    assert cut["noticedInMs"] < 10000, f"took {cut['noticedInMs']}ms to notice a closed socket"
    assert cut["stillResponsive"], "the page stopped responding when the link went away"
    assert cut["evaluateMs"] < 5000, (
        f"the page took {cut['evaluateMs']}ms to answer while disconnected — hung, not degraded"
    )
    assert cut["noticeVisible"], (
        "the stage went quiet with no visible explanation; a frozen board with no "
        "message is the worst thing that can happen in front of a class"
    )
    assert cut["recoveredInMs"] < 45000

    # Recovered, and to where the class actually is — a fresh snapshot, not a
    # patch across the gap.
    assert out["uiScene"] == out["serverScene"], (
        f"after reconnecting the stage shows {out['uiScene']!r} while core is on "
        f"{out['serverScene']!r}"
    )
    assert out["uiIndex"] == out["serverIndex"]
    assert out["uiVersion"] >= out["serverVersion"] - 1
    assert not out["pageErrors"], f"uncaught errors in the page: {out['pageErrors']}"


@pytest.mark.browser
@pytest.mark.itest(id="I9", title="Network unplugged: degrades, never hangs")
async def test_stage_notices_a_link_that_went_silent(core, ui, tts, proxy):
    """The half-open link: bytes stop, the socket never closes.

    This is the failure that actually happens in a school — an access point
    that stops forwarding, a NAT entry that expires — and it is the one that
    produces the worst outcome available: a frozen board with a healthy-looking
    connection behind it and nothing on screen to say so.

    I9 exists to prove the seam is honest. A stage that keeps reporting `open`
    while nothing has arrived for twenty seconds is not honest.
    """
    out = globals().get("_I9_UI_RESULT")
    if out is None:
        pytest.skip("runs off the same browser session as the cut test")

    bh = out["blackhole"]
    assert bh["stillResponsive"], "the page hung when the link went silent"
    assert bh["noticedInMs"] is not None, (
        "the stage still reports connection.state='open' "
        f"{bh['waitedMs'] / 1000:.0f}s after every byte "
        f"stopped arriving (scene frozen on {bh['sceneWhileDead']!r}, no notice shown: "
        f"noticeVisible={bh['noticeVisible']}). There is no liveness check on the "
        "WebSocket, so a half-open link is indistinguishable from a quiet lesson."
    )
    assert bh["noticeVisible"], "the stage noticed but showed the class nothing"
    # MEASURED, and worth knowing: ~32 s, and it is not the client that notices.
    # The stage has no heartbeat of its own; it finds out only when the server's
    # own ping timeout closes the socket and that close reaches it. On a route
    # that also swallows the FIN, nothing in the client would ever fire.
    # The measured value is ~32 s and the budget is deliberately well clear of
    # it: the path that eventually fires is the server's own ping timeout
    # (20 s interval + 20 s grace), not anything on the client, so the number
    # moves with server settings rather than with anything under test.
    assert bh["noticedInMs"] < 60000, (
        f"the stage took {bh['noticedInMs'] / 1000:.0f}s to notice a dead link"
    )
