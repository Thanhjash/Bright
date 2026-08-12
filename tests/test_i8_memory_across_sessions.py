"""I8 — run a session, end it, start another. The child is remembered.

"It remembers" is the claim that separates this from courseware, and until now
nothing had ever written and then read a real observation. The test runs the
whole loop across a **process restart**, so nothing can pass by still being in
memory:

    session 1   observations recorded while the class is graded
                session ends → summarize_session writes a durable note
    ── core process stops and starts again, same database ──
    session 2   the greeting turn is handed the child's name and the note,
                and the child hears it before the first activity

The assertions are made where they cannot be faked: on the prompt the model
actually received (read back from the scripted endpoint) and on the
`speech.say` that actually reached the bus.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from harness import ARTIFACTS, BusClient
from harness import llm_script as script

pytestmark = pytest.mark.slow

STUDENT_ID = "minh"
STUDENT_NAME = "Minh"
SUMMARY_JSON = json.dumps(
    {
        "summary": "Minh recognised the cat but hesitated on how many legs a bird has.",
        "weakPoints": ["counting_legs"],
        "nextFocus": ["counting_legs"],
    }
)


async def _wait_for_full(core, timeout: float = 40.0) -> str:
    deadline = time.monotonic() + timeout
    mode = core.health()["mode"]
    while time.monotonic() < deadline and mode != "FULL":
        await asyncio.sleep(0.5)
        mode = core.health()["mode"]
    return mode


@pytest.mark.itest(id="I8", title="Session 1 → session 2: the student is remembered")
async def test_memory_survives_the_bell(memory_core, llm):
    core = memory_core

    # ─────────────────────────── session 1 ───────────────────────────────
    llm.script([script.text("ok")], non_stream={"content": "ok"})
    assert await _wait_for_full(core) == "FULL", "the agent never came up; memory needs FULL"

    started = core.start_lesson(4, student_id=STUDENT_ID, student_name=STUDENT_NAME)  # q_legs
    session_1 = started["sessionId"]
    assert session_1

    core.interaction("interaction.choice", {"optionId": "two"})
    await asyncio.sleep(1.0)

    observations = core.state()
    assert observations["runner"]["lastOutcome"] == "correct"

    # Run to the end of the lesson so the session closes the way a class does.
    await asyncio.sleep(18)
    assert core.state()["runner"]["index"] >= 5

    # The summariser is a scheduled job; the dev route runs it now instead.
    llm.script([script.text("ok")], non_stream={"content": SUMMARY_JSON})
    summary = core.summarize(session_1)
    assert summary["ok"], f"session 1 left no summary: {summary}"

    # What session 1 wrote must be findable before we even restart.
    hits = core.recall("animal_vocab counting_legs")["results"]
    assert hits, "nothing recorded in session 1 is recallable"

    # ─────────────────────── the bell rings ──────────────────────────────
    core.restart_same_data()
    assert await _wait_for_full(core) == "FULL"

    # Memory outlived the process.
    hits = core.recall("animal_vocab counting_legs")["results"]
    assert hits, "recall returned nothing after a restart — memory did not persist"
    recalled_text = " ".join(h["text"] for h in hits)

    # ─────────────────────────── session 2 ───────────────────────────────
    client = BusClient(core.ws)
    await client.connect()

    greeting_text = "Hello again, Minh! Last time you were great with the cat."
    # `classroom_say` is the agent's voice and needs no state_version, which
    # matters here: the greeting turn happens *inside* `/dev/lesson/start`,
    # after core has already moved the lesson position, so no version this test
    # could read in advance would still be current.
    llm.script(
        [
            script.tool_call("classroom_say", {"text": greeting_text}),
            script.text("done"),
        ],
        non_stream={"content": "ok"},
    )

    core.start_lesson(0, student_id=STUDENT_ID)   # name comes from memory, not from us

    # ── the agent was TOLD who this is, and what happened last time ──────
    deadline = time.monotonic() + 20
    prompts: list[str] = []
    while time.monotonic() < deadline:
        prompts = llm.prompts()
        if prompts:
            break
        await asyncio.sleep(0.3)
    assert prompts, "session 2 never asked the agent anything — no greeting turn was taken"

    first = prompts[0]
    (ARTIFACTS / "i8-greeting-prompt.json").write_text(first)
    assert STUDENT_NAME in first or STUDENT_ID in first, (
        "the greeting prompt does not identify the student at all:\n" + first[:1200]
    )
    assert STUDENT_NAME in first, (
        "the agent was given the student id but not the name, so it cannot greet "
        f"anybody by name:\n{first[:1200]}"
    )
    assert any(word in first for word in ("cat", "counting_legs", "animal_vocab", "Minh recognised")), (
        "no prior-session content reached the greeting prompt; the agent has "
        f"nothing to remember with. recalled={recalled_text!r}\n{first[:1500]}"
    )

    # ── and the class actually heard it ──────────────────────────────────
    said = await client.wait_for(
        "speech.say", timeout=20, predicate=lambda e: STUDENT_NAME in (e["payload"].get("text") or "")
    )
    assert STUDENT_NAME in said["payload"]["text"]

    client.assert_clean()
    await client.close()
    core.control("pause")


@pytest.mark.itest(id="I8", title="Session 1 → session 2: the student is remembered")
async def test_a_turn_can_be_given_memory_and_a_restricted_option_set(memory_core, llm):
    """`/dev/agent/turn` takes `recallQuery` and `only`.

    Both are load-bearing for the greeting: memory has to be *injected* (the
    child is recognised before they have done anything to react to), and the
    option set has to be restricted (a greeting must never be able to skip the
    hook the author wrote).

    Asserted on the request the model received, because that is the only place
    that shows what the agent was actually allowed to know and to do.
    """
    core = memory_core
    assert await _wait_for_full(core) == "FULL"
    core.start_lesson(0, student_id=STUDENT_ID, student_name=STUDENT_NAME)

    # The agent writes something worth remembering.
    llm.script(
        [
            script.tool_call(
                "classroom_record_observation",
                {
                    "student_id": STUDENT_ID,
                    "skill": "animal_vocab",
                    "result": "wrong",
                    "evidence": "confused a bird with a fish",
                },
            ),
            script.text("noted"),
        ],
        non_stream={"content": "ok"},
    )
    wrote = core.agent_turn({"studentId": STUDENT_ID})
    assert wrote["observations"] == 1, f"the observation was not recorded: {wrote}"

    # A later turn asks for it, and is restricted to one action.
    llm.script([script.text("ok")], non_stream={"content": "ok"})
    core.agent_turn(
        {"studentId": STUDENT_ID, "recallQuery": "animal_vocab bird", "only": ["say_only"]}
    )

    requests = llm.requests()
    assert requests, "the restricted turn never reached the model"
    last = requests[-1]

    assert last["legalActions"] == ["say_only"], (
        f"`only` did not restrict the option set: the model was offered "
        f"{last['legalActions']}"
    )
    prompt = json.dumps(last["body"].get("messages") or [])
    assert "bird" in prompt and "animal_vocab" in prompt, (
        "`recallQuery` did not put the recalled observation into the prompt; "
        "memory that never reaches the model is not memory:\n" + prompt[-1500:]
    )
    core.control("pause")


@pytest.mark.itest(id="I8", title="Session 1 → session 2: the student is remembered")
async def test_a_slow_greeting_does_not_delay_the_class(memory_core, llm):
    """The greeting is bounded by `AGENT_GREETING_TIMEOUT_S`.

    A model having a bad day must cost the class a missing hello, not a lesson
    that will not start.
    """
    core = memory_core
    assert await _wait_for_full(core) == "FULL"

    llm.script([script.slow(60, script.text("eventually"))], non_stream={"content": "ok"})
    t0 = time.monotonic()
    started = core.start_lesson(0, student_id=STUDENT_ID, student_name=STUDENT_NAME)
    elapsed = time.monotonic() - t0

    assert started["ok"]
    assert elapsed < 20, (
        f"starting a lesson took {elapsed:.1f}s because the greeting turn hung. "
        "AGENT_GREETING_TIMEOUT_S is supposed to bound this."
    )
    assert core.state()["runner"]["running"], "the lesson never started"
    core.control("pause")
