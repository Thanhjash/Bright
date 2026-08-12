"""I1 — the sample lesson plays to the end with no agent. RELEASE GATE (NS-1).

The single most important test in the project. If this fails, the product's
central promise fails: a classroom in a school with no reliable internet must
still get its lesson.

"With the agent not running" is taken in its strongest form here: core is
started without `BRIGHT_AGENT`, so no agent object is ever constructed and
there is nothing to unplug. The test asserts that fact first (`/dev/agent/turn`
must refuse) so a future change that quietly wires an agent in cannot make this
test pass for the wrong reason.

The route walked is the one the tracker names, plus the failure branch, which
is the more valuable half: hook → vocabulary → question → answered **wrong** →
authored scaffold → next question → answered right → wrap → DONE.
"""

from __future__ import annotations

import time
import urllib.error

import pytest

from harness import BusClient

pytestmark = pytest.mark.slow


def _revealed(scene: dict) -> dict | None:
    return (scene.get("props") or {}).get("revealed")


@pytest.mark.itest(id="I1", title="Sample lesson plays start to finish with no agent (NS-1)", gate=True)
async def test_lesson_completes_with_no_agent(solo_core):
    # ── the agent really is absent ───────────────────────────────────────
    with pytest.raises(urllib.error.HTTPError) as exc:
        solo_core.agent_turn(timeout=15)
    assert exc.value.code == 503, "core claims an agent is wired; this is not the NS-1 configuration"

    lesson = solo_core.lesson()
    activity_ids = [a["id"] for a in lesson["activities"]]

    client = BusClient(solo_core.ws)
    await client.connect()
    snapshot = client.of_type("scene.snapshot")[0]["payload"]
    assert snapshot["scene"]["kind"] == "idle"

    solo_core.start_lesson(0)

    # ── hook → vocabulary → question ─────────────────────────────────────
    await client.wait_for_scene("text", timeout=20)
    await client.wait_for_scene("vocabulary", timeout=40)
    choice = await client.wait_for_scene("choice", timeout=60)
    assert choice["props"]["prompt"], "the question scene carries no prompt"
    q_meow_options = [o["id"] for o in choice["props"]["options"]]
    wrong = next(o for o in q_meow_options if o != "cat")

    # ── answer WRONG → graded, revealed, and scaffolded ──────────────────
    before = len(client.events)
    t0 = time.monotonic()
    await client.choose(wrong)
    reveal = await client.wait_for(
        "scene.update",
        timeout=15,
        since=before,
        predicate=lambda e: bool(_revealed(e["payload"])),
    )
    reveal_ms = (time.monotonic() - t0) * 1000
    assert _revealed(reveal["payload"])["chosenId"] == wrong
    assert _revealed(reveal["payload"])["correctId"] == "cat"
    assert reveal_ms < 1000, f"answer→reveal took {reveal_ms:.0f}ms; the reflex tier must be sub-second"

    state = solo_core.state()
    assert state["runner"]["lastOutcome"] == "wrong"

    # the authored `wrong` branch goes to the scaffold, not to the next question
    await client.wait_for(
        "lesson.position",
        timeout=25,
        predicate=lambda e: e["payload"]["activityIndex"] == activity_ids.index("help_meow"),
    )

    # ── second question, answered correctly ──────────────────────────────
    await client.wait_for(
        "lesson.position",
        timeout=40,
        predicate=lambda e: e["payload"]["activityIndex"] == activity_ids.index("q_legs"),
    )
    before = len(client.events)
    await client.choose("two")
    reveal2 = await client.wait_for(
        "scene.update",
        timeout=15,
        since=before,
        predicate=lambda e: bool(_revealed(e["payload"])),
    )
    assert _revealed(reveal2["payload"])["chosenId"] == "two"
    assert solo_core.state()["runner"]["lastOutcome"] == "correct"

    # ── the lesson reaches the end on its own ────────────────────────────
    done = await client.wait_for(
        "lesson.position", timeout=45, predicate=lambda e: e["payload"]["stage"] == "DONE"
    )
    assert done["payload"]["activityIndex"] >= len(activity_ids) - 1

    # ── the bus stayed honest for the whole lesson ───────────────────────
    client.assert_clean()
    assert client.closed_code is None, f"core closed the socket mid-lesson: {client.closed_code}"

    # ── the teacher actually spoke ───────────────────────────────────────
    spoken = client.spoken()
    assert len(spoken) >= 4, f"only {len(spoken)} narration lines for a 6-activity lesson"
    assert all(line.strip() for line in spoken)

    await client.close()


@pytest.mark.itest(id="I1", title="Sample lesson plays start to finish with no agent (NS-1)", gate=True)
async def test_no_llm_call_is_possible_without_an_agent(solo_core):
    """The NS-1 claim is *zero LLM calls*, not *few*.

    Core is the only process in the loop, it has no model configured, and every
    tier that could reach one is absent. Asserted structurally: the dev turn
    endpoint refuses, and the mode reflects having no agent rather than
    pretending to be healthy.
    """
    with pytest.raises(urllib.error.HTTPError) as exc:
        solo_core.agent_turn(timeout=15)
    assert exc.value.code == 503

    mode = solo_core.health()["mode"]
    assert mode == "OFFLINE", (
        f"core reports mode={mode} with no agent wired at all. "
        "PROTOCOL §7/§9.9: no agent means OFFLINE, and the stage must carry a badge."
    )
