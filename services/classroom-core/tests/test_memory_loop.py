"""The memory loop, end to end: a child is observed, summarised, and recognised.

Definition of success #3 in the north star is "students are addressed by name,
and the lesson remembers what they struggled with last week". That sentence is
a loop with four joints -- write an observation, close a session, summarise it,
recall it into next week's prompt -- and each joint has silently failed at some
point. So the load-bearing test here plays two whole sessions and asserts on
what actually reached the second one's prompt.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from conftest import ScriptedAgent, choose, wire

from agent_bridge import (
    SessionSummarizer,
    build_agent_seam,
    build_turn_context,
    default_recall_query,
    deterministic_summary,
    extract_json,
    skill_estimates,
)
from app import Core

# What the summariser's model is scripted to reply. It names the skill key on
# purpose: that is what makes a summary findable by the same query that finds
# the observations under it.
SUMMARY_JSON = (
    '{"summary": "Mai chose the dog when asked which animal says meow, so her '
    'animal_vocab listening is not secure yet.", '
    '"weakPoints": ["animal sounds"], "nextFocus": ["cat versus dog"]}'
)


def teach(ctx: Any) -> list[tuple[str, Any]]:
    """A plausible turn: greet or react, note it down, then decide.

    Chooses `say_only` every time, which is legal both in the restricted
    greeting turn and in a full mid-lesson turn.
    """
    who = ctx.student.name if ctx.student else "everyone"
    calls: list[tuple[str, Any]] = [("classroom_say", {"text": f"Hello {who}!"})]
    if ctx.student and ctx.last_interaction:
        calls.append(
            (
                "classroom_record_observation",
                {
                    "student_id": ctx.student.id,
                    "skill": "animal_vocab",
                    "result": ctx.last_interaction.outcome,
                    "evidence": "picked the dog for the meow question",
                },
            )
        )
    calls.append(
        (
            "classroom_choose_next",
            {
                "action_id": "say_only",
                "state_version": ctx.state_version,
                "params": {"text": "Listen once more."},
            },
        )
    )
    return calls


def with_summariser(core: Core, agent: ScriptedAgent) -> None:
    """Wire the background half of the seam, as app.py does at startup."""
    core.set_agent_seam(build_agent_seam(core, agent))


async def play_a_session(core: Core, *, student_id: str, student_name: str | None = None) -> str:
    """Start, get one question wrong, run to the end of the lesson."""
    await core.start_lesson(index=1, student_id=student_id, student_name=student_name)
    session_id = core.session_id
    assert session_id is not None

    await core.runner.handle_interaction("choice", {"optionId": "z"})
    await core.runner.drain()

    await asyncio.sleep(0.25)          # let the deferred branch fire
    await core.runner.drain()
    # Two skips with no await between them: a5 arms a silence timer on entry
    # and we do not want it racing the walk to the end.
    await core.runner.control("skip")
    await core.runner.control("skip")
    await core.runner.drain()
    return session_id


# ---------------------------------------------------------- writing it down


async def test_observations_are_attributed_to_the_session_student(core: Core):
    """A row with a NULL student is a row recall can never find again."""
    await core.start_lesson(index=1, student_id="s01", student_name="Mai")
    session_id = core.session_id

    await core.runner.handle_interaction("choice", {"optionId": "z"})
    await core.runner.drain()

    rows = core.db.list_observations(session_id=session_id)
    assert rows, "the runner records every graded interaction"
    assert {r["student_id"] for r in rows} == {"s01"}
    assert rows[0]["skill"] == "animal_vocab"       # lesson.focus[0]


async def test_raw_speech_is_not_persisted_or_recalled(core: Core):
    # The tiny fixture's speech activity is a5 at index 4.
    await core.start_lesson(index=4, student_id="s01", student_name="Mai")
    secret = "my private transcript zebra seven"
    await core.runner.handle_interaction(
        "speech", {"text": secret, "studentId": "s01", "confidence": 0.9}
    )
    await core.runner.drain()

    rows = core.db.list_observations(student_id="s01")
    assert rows
    assert all(secret not in (row["evidence"] or "") for row in rows)
    assert core.db.recall("private transcript zebra", student_id="s01") == []
    assert secret not in (core.store.scene.overlay.subtitle or "")


def test_hosted_context_pseudonymizes_and_withholds_recall(core: Core):
    core.db.upsert_student("s01", "Mai")
    core.db.record_observation("s01", "animal_vocab", "wrong", "named the dog")
    ctx = build_turn_context(
        core,
        student_id="s01",
        recall_query="animal_vocab",
        context_policy="hosted-minimal",
    )
    assert ctx.student is not None
    assert ctx.student.id == "current_student"
    assert ctx.student.name == "the current student"
    assert not ctx.recalled


async def test_the_agent_records_observations_during_a_real_turn(core: Core):
    """`classroom_record_observation` must land rows, not just return ok."""
    agent = wire(core, teach)
    await core.start_lesson(index=1, student_id="s01", student_name="Mai")
    session_id = core.session_id

    await core.runner.handle_interaction("choice", {"optionId": "z"})
    await core.runner.drain()

    rows = core.db.list_observations(session_id=session_id)
    from_agent = [r for r in rows if r["evidence"] == "choice -> wrong"]
    assert len(from_agent) == 1, rows
    assert all("picked the dog" not in (r["evidence"] or "") for r in rows)
    assert from_agent[0]["student_id"] == "s01"
    assert from_agent[0]["result"] == "wrong"
    assert agent.started >= 1


async def test_a_new_student_is_created_on_lesson_start(core: Core):
    assert core.db.get_student("s09") is None
    await core.start_lesson(index=0, student_id="s09", student_name="Linh")
    assert core.db.get_student("s09")["name"] == "Linh"


async def test_starting_again_does_not_overwrite_a_known_name(core: Core):
    await core.start_lesson(index=0, student_id="s01", student_name="Mai")
    await core.end_session()
    await core.start_lesson(index=0, student_id="s01")     # no name this time
    assert core.db.get_student("s01")["name"] == "Mai"


# ------------------------------------------------------------ summarising


async def test_summarize_session_writes_a_real_row(core: Core):
    agent = wire(core, teach, reply=SUMMARY_JSON)
    with_summariser(core, agent)
    session_id = await play_a_session(core, student_id="s01", student_name="Mai")

    assert core.session_id is None, "the lesson ending closed the session"
    written = await core.jobs.summarize_session(session_id)

    assert written is not None
    row = core.db.get_session_summary(session_id)
    assert "animal_vocab" in row["summary"]
    assert row["weakPoints"] == ["animal sounds"]
    assert row["nextFocus"] == ["cat versus dog"]


async def test_the_summary_updates_the_skill_estimate(core: Core):
    agent = wire(core, teach, reply=SUMMARY_JSON)
    with_summariser(core, agent)
    session_id = await play_a_session(core, student_id="s01", student_name="Mai")
    await core.jobs.summarize_session(session_id)

    skills = core.db.get_student("s01")["skills"]
    assert "animal_vocab" in skills
    assert skills["animal_vocab"] == pytest.approx(0.0), "every attempt was wrong"


async def test_a_session_with_nothing_in_it_is_not_summarised(core: Core):
    agent = wire(core, teach, reply=SUMMARY_JSON)
    with_summariser(core, agent)
    session_id = core.db.start_session(student_id="s01")

    assert await core.jobs.summarize_session(session_id) is None
    assert core.db.get_session_summary(session_id) is None


async def test_a_broken_summariser_still_leaves_a_usable_trace(core: Core):
    """NS-1 applies to memory too.

    If the model is unreachable when the bell rings, next week's greeting must
    still have something to remember. Worse prose beats no row.
    """
    agent = wire(core, teach, complete_error=RuntimeError("no route to host"))
    with_summariser(core, agent)
    session_id = await play_a_session(core, student_id="s01", student_name="Mai")

    await core.jobs.summarize_session(session_id)

    row = core.db.get_session_summary(session_id)
    assert row is not None
    assert "Mai" in row["summary"] and "animal_vocab" in row["summary"]
    assert row["weakPoints"] == ["animal_vocab"]


async def test_an_unparseable_reply_falls_back_rather_than_writing_junk(core: Core):
    agent = wire(core, teach, reply="Sure! Here are my thoughts about Mai.")
    with_summariser(core, agent)
    session_id = await play_a_session(core, student_id="s01", student_name="Mai")

    await core.jobs.summarize_session(session_id)

    assert "Sure!" not in core.db.get_session_summary(session_id)["summary"]


# --------------------------------------------------------------- the loop


async def test_the_memory_loop_closes_across_two_sessions(core: Core):
    """Session 1 happens, is summarised, and shows up in session 2's prompt.

    This is the whole product promise in one test.
    """
    agent = wire(core, teach, reply=SUMMARY_JSON)
    with_summariser(core, agent)

    # --- session 1 -------------------------------------------------------
    first = await play_a_session(core, student_id="s01", student_name="Mai")
    observations = core.db.list_observations(session_id=first)
    assert len(observations) >= 2
    assert {o["student_id"] for o in observations} == {"s01"}

    await core.jobs.summarize_session(first)
    assert core.db.get_session_summary(first) is not None

    # --- session 2 -------------------------------------------------------
    turns_before = len(agent.contexts)
    await core.start_lesson(index=1, student_id="s01")
    second = core.session_id
    assert second != first
    assert len(agent.contexts) == turns_before, "private learner memory must not create public startup speech"
    private = build_turn_context(core, student_id="s01", recall_query="animal_vocab")
    assert private.student is not None
    assert private.student.name == "Mai", "the child is recognised, not re-registered"
    assert private.recalled, "session 1 remains available to a scoped teaching turn"

    remembered = " ".join(m.text for m in private.recalled)
    assert "animal_vocab" in remembered
    assert any(
        "not secure yet" in m.text for m in private.recalled
    ), f"the session summary itself should surface, got: {remembered}"


async def test_recall_reaches_the_turn_context_at_all(core: Core):
    """Regression: this path was dead.

    `Database.recall` returns `RecalledMemory` objects; `build_turn_context`
    called `.get("text")` on them, raised `AttributeError` on every single
    call, swallowed it, logged "recall failed" and left `recalled` as `None`.
    Memory had therefore never once reached a prompt.
    """
    core.db.record_observation("s01", "animal_vocab", "wrong", "chose dog for meow")

    ctx = build_turn_context(core, student_id="s01", recall_query="animal_vocab")

    assert ctx.recalled, "recall must produce memories, not swallow an exception"
    assert "chose dog for meow" in ctx.recalled[0].text


async def test_recall_is_strictly_isolated_to_this_student(core: Core):
    core.db.record_observation("s02", "animal_vocab", "correct", "another child entirely")
    core.db.record_observation("s01", "animal_vocab", "wrong", "chose dog for meow")

    mine = build_turn_context(core, student_id="s01", recall_query="animal_vocab")
    assert all("another child" not in m.text for m in mine.recalled)

    # A child with no history gets no learner memory; another child's note is
    # never a safe fallback.
    theirs = build_turn_context(core, student_id="s03", recall_query="animal_vocab")
    assert not theirs.recalled


async def test_the_session_summary_always_gets_a_slot(core: Core):
    """Otherwise `summarize_session` is a job nobody ever reads.

    bm25 rewards short documents, so raw observation rows out-rank the
    paragraph written about them. Measured on the first live two-session run:
    the summary ranked 4th of 3.
    """
    session_id = core.db.start_session(student_id="s01")
    for i in range(6):
        core.db.record_observation(
            "s01", "animal_vocab", "wrong", f"attempt {i} chose dog", session_id
        )
    core.db.write_session_summary(
        session_id, "Mai is not secure on animal_vocab listening yet.", ["sounds"], ["cat vs dog"]
    )

    ctx = build_turn_context(core, student_id="s01", recall_query="animal_vocab")

    assert len(ctx.recalled) == 3
    assert "not secure" in ctx.recalled[0].text, [m.text for m in ctx.recalled]
    assert any("attempt" in m.text for m in ctx.recalled), "episodes still come through"


async def test_recall_can_be_asked_for_one_tier(core: Core):
    session_id = core.db.start_session(student_id="s01")
    core.db.record_observation("s01", "animal_vocab", "wrong", "chose dog", session_id)
    core.db.write_session_summary(session_id, "animal_vocab needs review", [], [])

    only_summaries = core.db.recall("animal_vocab", k=5, kind="summary")
    assert [m.text for m in only_summaries] == ["animal_vocab needs review"]

    everything = core.db.recall("animal_vocab", k=5)
    assert len(everything) == 2


async def test_recall_survives_a_store_without_tiers(core: Core):
    """The blend is an optimisation, not a dependency."""

    class Flat:
        def recall(self, query, k=5, student_id=None):
            return [{"text": f"flat hit for {query}", "when": "2026-01-01"}]

        def get_student(self, _student_id):
            return None

    real, core.db = core.db, Flat()
    try:
        ctx = build_turn_context(core, student_id="s01", recall_query="animal_vocab")
    finally:
        core.db = real
    assert ctx.recalled and "flat hit" in ctx.recalled[0].text


async def test_the_default_recall_query_covers_skills_and_prose(core: Core):
    query = default_recall_query(core)
    assert "animal_vocab" in query, "matches observation skill keys exactly"
    assert "Tiny" in query, "and the plain words a model's summary would use"


# ------------------------------------------------------- greeting by name


async def test_class_start_does_not_publish_private_name_or_memory(core: Core):
    agent = wire(core, teach, reply=SUMMARY_JSON)
    with_summariser(core, agent)
    first = await play_a_session(core, student_id="s01", student_name="Mai")
    await core.jobs.summarize_session(first)

    sub = core.bus.subscribe(role="stage")
    turns_before = len(agent.contexts)
    await core.start_lesson(index=1, student_id="s01")
    frames = [sub.queue.get_nowait() for _ in range(sub.queue.qsize())]
    rendered = str(frames)
    assert len(agent.contexts) == turns_before
    assert "Mai" not in rendered
    assert "not secure" not in rendered


async def test_private_memory_is_loaded_only_when_a_scoped_turn_requests_it(core: Core):
    agent = wire(core, teach, reply=SUMMARY_JSON)
    with_summariser(core, agent)
    first = await play_a_session(core, student_id="s01", student_name="Mai")
    await core.jobs.summarize_session(first)

    turns_before = len(agent.contexts)
    await core.start_lesson(index=1, student_id="s01")
    assert len(agent.contexts) == turns_before
    ctx = build_turn_context(core, student_id="s01", recall_query="animal_vocab")
    assert ctx.student.name == "Mai"
    assert ctx.recalled


async def test_relabelling_cannot_widen_what_is_legal(core: Core):
    """A label is prose. Only an id is a permission."""
    wire(core, choose("next_activity"))
    await core.runner.start(1)

    result = await core.agent_driver.take_turn(
        only=("say_only",), relabel={"say_only": "do whatever you like"}
    )

    assert result.applied is False
    assert core.runner.index == 1


async def test_startup_agent_cannot_skip_the_authored_hook(core: Core):
    """There is no startup agent turn; authored instruction starts directly."""
    agent = wire(core, choose("next_activity"))
    await core.start_lesson(index=1, student_id="s01", student_name="Mai")

    assert agent.contexts == []
    assert core.runner.index == 1, "startup did not advance past the authored hook"


async def test_no_greeting_without_a_student(core: Core):
    agent = wire(core, teach)
    await core.start_lesson(index=1)
    assert agent.started == 0


async def test_no_greeting_when_the_mode_is_not_full(core: Core):
    agent = wire(core, teach)
    core.modes.forced_mode = None
    core.modes.apply("OFFLINE", "test")

    await core.start_lesson(index=1, student_id="s01", student_name="Mai")

    assert agent.started == 0
    assert core.runner.index == 1, "and the lesson started anyway"


async def test_a_hanging_greeting_does_not_hold_up_the_class(core: Core):
    wire(core, teach, delay=5.0)
    await core.start_lesson(index=1, student_id="s01", student_name="Mai")
    assert core.runner.running is True and core.runner.index == 1


# ------------------------------------------------------- the mid-turn view


async def test_re_reading_state_mid_turn_keeps_the_student(core: Core):
    """`classroom_get_state` used to rebuild a context with no student in it,
    so a model that double-checked itself lost the child it was talking to."""

    def peek(ctx: Any) -> list[tuple[str, Any]]:
        return [("classroom_get_state", {})]

    core.db.record_observation("s01", "animal_vocab", "wrong", "chose dog for meow")
    agent = wire(core, peek)
    await core.start_lesson(index=1, student_id="s01", student_name="Mai")
    assert agent.results == [], "startup may not expose private state to an agent"
    ctx = build_turn_context(core, student_id="s01", recall_query="animal_vocab")
    assert ctx.student.name == "Mai"
    assert ctx.recalled


# ------------------------------------------------------------- small parts


def test_skill_estimates_are_counted_not_invented():
    observations = [
        {"skill": "animal_vocab", "result": "correct"},
        {"skill": "animal_vocab", "result": "near"},
        {"skill": "animal_vocab", "result": "wrong"},
        {"skill": "listening_a1", "result": "correct"},
        {"skill": "", "result": "correct"},              # unattributed: ignored
        {"skill": "animal_vocab", "result": "banana"},   # not an outcome: ignored
    ]
    assert skill_estimates(observations) == {"animal_vocab": 0.5, "listening_a1": 1.0}


def test_skill_estimates_of_nothing_is_nothing():
    assert skill_estimates([]) == {}


@pytest.mark.parametrize(
    "raw",
    [
        '{"summary": "s"}',
        '```json\n{"summary": "s"}\n```',
        'Sure, here you go:\n{"summary": "s"}\nHope that helps!',
    ],
)
def test_extract_json_tolerates_fences_and_prose(raw: str):
    assert extract_json(raw) == {"summary": "s"}


@pytest.mark.parametrize("raw", ["", "no json here", "{not json}", "[1,2]"])
def test_extract_json_refuses_what_it_cannot_read(raw: str):
    assert extract_json(raw) is None


@pytest.mark.parametrize(
    "raw,expected",
    [
        # Exactly what MiMo returned live: valid object, missing final brace.
        ('{"summary": "s", "weakPoints": ["a"], "nextFocus": ["b"]', ["a"]),
        ('{"summary": "s", "weakPoints": ["a"],', ["a"]),
        ('{"summary": "s", "weakPoints": ["a", "b', ["a", "b"]),
    ],
)
def test_extract_json_repairs_a_truncated_reply(raw: str, expected: list[str]):
    """A dropped closing brace must not cost us a good summary."""
    parsed = extract_json(raw)
    assert parsed is not None
    assert parsed["summary"] == "s"
    assert parsed["weakPoints"] == expected


def test_repair_never_invents_a_summary():
    assert extract_json('{"weakPoints": ["a"') == {"weakPoints": ["a"]}
    assert extract_json("{") is None


def test_deterministic_summary_names_both_halves():
    out = deterministic_summary(
        [
            {"skill": "animal_vocab", "result": "wrong"},
            {"skill": "listening_a1", "result": "correct"},
        ],
        "Mai",
    )
    assert "Mai" in out["summary"]
    assert "animal_vocab" in out["summary"] and "listening_a1" in out["summary"]
    assert out["weakPoints"] == ["animal_vocab"]


async def test_the_summariser_asks_about_the_right_child(core: Core):
    agent = wire(core, teach, reply=SUMMARY_JSON)
    summarizer = SessionSummarizer(core, agent)
    session_id = await play_a_session(core, student_id="s01", student_name="Mai")

    await summarizer(session_id, core.db.list_observations(session_id=session_id))

    sent = agent.completions[0][-1]["content"]
    assert "STUDENT Mai" in sent
    assert "animal_vocab" in sent
