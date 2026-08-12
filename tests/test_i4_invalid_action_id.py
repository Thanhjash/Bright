"""I4 — an invalid `action_id` is rejected, falls back, and is never retried.

The design claim (architecture §3, tracker B3) is that the model proposes from
an option set core itself computed, and that anything else is thrown away
rather than repaired. "Never retried" is the half that is easy to lose: a
retry loop in front of thirty children is a silent stall, and it is exactly
the kind of thing that looks fine in a unit test where the model is a stub.

The scripted model here streams a *real* tool call over *real* SSE into the
*real* `DirectAgent`, so the rejection path that runs is the shipped one.

A positive control runs first. Without it, I4 and I5 would both pass on a
system where `classroom_choose_next` never works at all.
"""

from __future__ import annotations

import pytest

from harness import llm_script as script


def _legal(core):
    info = core.agent_actions()
    return info["stateVersion"], [a["id"] for a in info["availableActions"]]


@pytest.mark.itest(id="I4", title="Invalid action_id rejected, falls back, never retried")
async def test_valid_action_applies(core, llm):
    """Positive control: the machinery works when the proposal is legal."""
    core.start_lesson(0)
    version, actions = _legal(core)
    assert actions, "core offered the agent nothing to choose from"
    assert "next_activity" in actions

    index_before = core.state()["runner"]["index"]
    llm.script([script.tool_call("classroom_choose_next", {"state_version": version, "action_id": "next_activity"})])

    result = core.agent_turn()
    assert result["applied"] is True, f"a legal action was not applied: {result}"
    assert result["chose"] == "next_activity"
    assert result["rejected"] is None
    assert core.state()["runner"]["index"] == index_before + 1
    core.control("pause")


@pytest.mark.itest(id="I4", title="Invalid action_id rejected, falls back, never retried")
async def test_invalid_action_id_is_rejected_and_not_retried(core, llm):
    core.start_lesson(0)
    version, actions = _legal(core)
    assert "goto:a_room_that_does_not_exist" not in actions

    index_before = core.state()["runner"]["index"]
    scene_before = core.state()["snapshot"]["scene"]["kind"]
    llm.script(
        [
            script.tool_call(
                "classroom_choose_next",
                {"state_version": version, "action_id": "goto:a_room_that_does_not_exist"},
            )
        ]
    )

    result = core.agent_turn()

    assert result["applied"] is False, "an invented action_id was applied to the board"
    assert result["chose"] is None
    assert result["rejected"], "the turn reported no rejection for an illegal action_id"

    # validation.py rule 2: every rejection is logged as one structured record
    # with enough detail to replay it. The turn's own summary says only "agent
    # reported error", so the log is the only place the reason survives.
    log = core.tail(400)
    assert "unknown_action_id" in log, (
        "no structured rejection record was logged; nothing downstream can tell "
        f"why the proposal was refused. tail:\n{log[-1500:]}"
    )

    # SINGLE ATTEMPT. `max_rounds` is 3, so a repair loop would show up as 2-3
    # upstream calls. Exactly one means the turn ended on the rejection.
    assert llm.request_count() == 1, (
        f"the agent called the model {llm.request_count()} times for one rejected proposal — "
        "a retry loop in front of a class"
    )

    # FALLS BACK: the board did not move, and the authored lesson still owns it.
    after = core.state()
    assert after["runner"]["index"] == index_before
    assert after["snapshot"]["scene"]["kind"] == scene_before
    assert core.health()["status"] == "ok"
    core.control("pause")


@pytest.mark.itest(id="I4", title="Invalid action_id rejected, falls back, never retried")
async def test_lesson_survives_a_rejected_proposal(core, llm):
    """After the rejection the reflex tier must still be able to drive."""
    core.start_lesson(2)  # q_meow
    version, _ = _legal(core)
    llm.script([script.tool_call("classroom_choose_next", {"state_version": version, "action_id": "invent:nothing"})])
    core.agent_turn()

    outcome = core.interaction("interaction.choice", {"optionId": "cat"})
    assert outcome["outcome"] == "correct", f"grading broke after a rejected proposal: {outcome}"
    core.control("pause")
