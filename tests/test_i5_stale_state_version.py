"""I5 — a decision made against state that has moved on is discarded.

The failure this prevents is silent by construction: the agent thinks for two
seconds, the child answers in one, and the agent's now-obsolete instruction
lands on a board that has already changed. Nothing throws. The class simply
sees the wrong thing.

Two shapes are exercised: a stale version the agent invented, and — the real
one — a version that was correct when the turn began and went out of date
because the classroom moved underneath it.
"""

from __future__ import annotations

import asyncio

import pytest

from harness import BusClient
from harness import llm_script as script


@pytest.mark.itest(id="I5", title="Stale state_version rejected, board not touched")
async def test_stale_state_version_is_rejected(core, llm):
    core.start_lesson(0)
    info = core.agent_actions()
    version = info["stateVersion"]
    action = "next_activity"
    assert action in [a["id"] for a in info["availableActions"]]

    index_before = core.state()["runner"]["index"]
    llm.script(
        [script.tool_call("classroom_choose_next", {"state_version": version - 5, "action_id": action})]
    )

    result = core.agent_turn()

    assert result["applied"] is False, "an action carrying a stale state_version reached the board"
    assert result["chose"] is None
    assert result["rejected"]
    assert core.state()["runner"]["index"] == index_before
    assert "stale_state_version" in core.tail(400), "the stale rejection was not logged"
    assert llm.request_count() == 1, "a stale version triggered a retry"
    core.control("pause")


@pytest.mark.itest(id="I5", title="Stale state_version rejected, board not touched")
async def test_version_that_goes_stale_during_the_turn_is_rejected(core, llm):
    """The realistic race: correct when the model was asked, wrong when it answered.

    The scripted model pauses mid-turn; the test moves the classroom during
    that pause, exactly as a child answering would. The proposal must land on
    the floor, not on the board.
    """
    core.start_lesson(2)  # q_meow — a question the class can answer
    version = core.agent_actions()["stateVersion"]

    response = script.tool_call(
        "classroom_choose_next", {"state_version": version, "action_id": "repeat_activity"}
    )
    # Answer arrives while the model is still "thinking".
    response["chunks"].insert(0, {"sleep": 1.5})
    llm.script([response])

    import asyncio

    turn = asyncio.create_task(asyncio.to_thread(core.agent_turn))
    await asyncio.sleep(0.6)
    core.interaction("interaction.choice", {"optionId": "cat"})   # the class moves on
    result = await turn

    assert core.state()["stateVersion"] > version, "the test failed to move the state at all"
    assert result["applied"] is False, (
        "a decision made against a board that has since changed was applied anyway"
    )
    assert result["rejected"]
    core.control("pause")


@pytest.mark.itest(id="I5", title="Stale state_version rejected, board not touched")
async def test_every_graded_answer_moves_the_state_version(speech_drag_core):
    """The staleness check is only as good as the version it compares.

    A decision is discarded when `state_version` no longer matches. That
    protection is worth nothing for an answer kind that grades without moving
    the version: the board has changed, the agent's decision was computed for
    the previous answer, and the numbers still agree — so it is applied to a
    classroom that has moved on.

    `runner._reveal` bumps the version for `choice` and for `vocabulary/point`,
    and does nothing for `speech` or `drag`. Both are graded here over the
    **real WebSocket path** a classroom uses, against a lesson in
    `tests/fixtures/` that asks for them — the sample lesson only ever asks a
    `choice`, so these two have never run end to end.

    The distinction matters and this test keeps it: over the socket, a speech
    answer moves the version *incidentally*, because the handler sets the
    subtitle overlay before grading. A drag answer moves nothing at all.
    """
    core = speech_drag_core
    client = BusClient(core.ws)
    await client.connect()

    results: dict[str, tuple[int, int, str]] = {}

    # ── speech ───────────────────────────────────────────────────────────
    core.start_lesson(0)  # say_cat, expect.kind == 'speech'
    await client.wait_for_scene("vocabulary", timeout=20)
    state = core.state()
    before = state["stateVersion"]
    position = state["snapshot"]["lesson"]
    await client.send("student.speech.final", {
        "text": "cat",
        "confidence": 0.9,
        "utteranceId": "i5-speech-answer",
        "activityId": position["activityId"],
        "activityGeneration": position["activityGeneration"],
    })
    await asyncio.sleep(1.0)
    results["speech"] = (before, core.state()["stateVersion"], core.state()["runner"]["lastOutcome"])
    core.control("pause")

    # ── drag ─────────────────────────────────────────────────────────────
    core.start_lesson(2)  # drag_cat, expect.kind == 'drag'
    await client.wait_for_scene("matching", timeout=20)
    before = core.state()["stateVersion"]
    await client.send("interaction.drag", {"fromId": "cat", "toId": "meow"})
    await asyncio.sleep(1.0)
    results["drag"] = (before, core.state()["stateVersion"], core.state()["runner"]["lastOutcome"])
    core.control("pause")
    await client.close()

    for kind, (_, _, outcome) in results.items():
        assert outcome == "correct", f"the {kind} answer was not graded at all: {results[kind]}"

    blind = [k for k, (b, a, _) in results.items() if a <= b]
    assert not blind, (
        "these answer kinds grade without moving `state_version`: "
        + ", ".join(f"{k} ({results[k][0]} → {results[k][1]})" for k in blind)
        + ". An agent decision computed before such an answer still validates as "
        "current and is applied to a board that has already moved. "
        "`runner._reveal` bumps the version only for `choice` and "
        "`vocabulary/point`; the `speech` path escapes it only because the "
        "socket handler happens to set the subtitle overlay first."
    )


@pytest.mark.itest(id="I5", title="Stale state_version rejected, board not touched")
async def test_a_choice_answer_does_move_the_state_version(core):
    """Control for the test above: the kind that works, works."""
    core.start_lesson(2)  # q_meow, expect.kind == 'choice'
    before = core.state()["stateVersion"]
    core.interaction("interaction.choice", {"optionId": "cat"})
    after = core.state()["stateVersion"]
    assert after > before, f"even `choice` no longer bumps the version: {before} → {after}"
    core.control("pause")
