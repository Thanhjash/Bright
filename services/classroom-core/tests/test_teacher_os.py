import asyncio
import inspect
from pathlib import Path
from types import SimpleNamespace

import teacher_os
from mcp_server import TOOLS_BY_NAME
from teacher_os import TeacherOS


class _RecordingStore:
    """Fake StateStore that just echoes back kind/props, like the Store in
    test_show_image_publishes_legal_scene_update above."""

    def set_scene(self, kind, props):
        return {"kind": kind, "props": props}


def _stage_core(*, session_id: str = "sess-stage"):
    frames: list[tuple] = []
    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id=session_id,
        store=_RecordingStore(),
        bus=SimpleNamespace(publish=lambda *a, **k: frames.append((a, k))),
        publish_speech=lambda *a, **k: None,
    )
    return core, frames


def _published_props(frames: list[tuple]) -> dict:
    event, scene = frames[-1][0]
    assert event == "scene.update"
    return scene["props"]


def test_teacher_module_has_no_lesson_run_graph() -> None:
    source = inspect.getsource(teacher_os)
    assert "lesson_run" not in source
    assert "LessonRunner" not in source
    assert "propose_move" not in source
    script = Path(__file__).resolve().parents[3] / "scripts" / "teacher-agent-l1.sh"
    text = script.read_text(encoding="utf-8")
    # The lesson-graph player is deleted: the launcher must not point Core at
    # a lesson_run, not even an empty placeholder one.
    assert "CORE_LESSON_RUN=" not in text
    assert "no-lesson.json" not in text
    assert "sample_lesson_run" not in text


def test_show_image_publishes_legal_scene_update() -> None:
    frames: list[tuple] = []

    class Store:
        def set_scene(self, kind, props):
            return {"kind": kind, "props": props}

    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id="sess-stage",
        store=Store(),
        bus=SimpleNamespace(publish=lambda *a, **k: frames.append((a, k))),
    )
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        ok = await os.execute("show_image", {"asset": "asset://gs3/pages/p10.jpg"})
        assert ok["ok"] is True

    asyncio.run(run())
    assert frames
    assert frames[0][0][0] == "scene.update"
    assert "board.present" not in str(frames)


def test_three_teaching_hands_are_generic() -> None:
    published: list[tuple] = []
    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id="sess-hands",
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda text, source="agent", audio_asset=None: published.append(
            (text, source, audio_asset)
        ),
    )
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        chalk = await os.execute(
            "write_board",
            {"text": "# apple\n\n- red\n- fruit"},
        )
        assert chalk["ok"] is True
        assert os.last_writing is not None and os.last_writing.startswith("# apple")
        seen = await os.execute("read_board", {})
        assert seen["ok"] is True
        assert seen["writing"] == os.last_writing
        html = await os.execute("write_board", {"text": "<script>x</script>"})
        assert html["ok"] is False
        graded = await os.execute("write_board", {"text": "# word\n\n- you said it ✓"})
        assert graded["ok"] is False
        pic = await os.execute("show_image", {"asset": "asset://gs3/pages/p10.jpg"})
        assert pic["ok"] is True
        assert os.last_images["main"] == "asset://gs3/pages/p10.jpg"
        bad = await os.execute("show_image", {"asset": "asset://../secret.png"})
        assert bad["ok"] is False
        missing = await os.execute("play_clip", {"asset": "asset://gs3/audio/nope.mp3"})
        assert missing["ok"] is False
        invented = await os.execute(
            "record_evidence",
            {"student_id": "learner-1", "objective_id": "say-food-word", "outcome": "correct"},
        )
        assert invented["ok"] is False
        extra = await os.execute("show_image", {"asset": "asset://gs3/pages/p12.jpg"})
        assert extra["ok"] is True
        clip = await os.execute(
            "play_clip",
            {"asset": "asset://gs3/audio/track-05.mp3", "transcript": "apple"},
        )
        assert clip["ok"] is True
        assert os.last_clip == {"asset": "asset://gs3/audio/track-05.mp3", "transcript": "apple"}
        assert published[-1][2] == "asset://gs3/audio/track-05.mp3"

    asyncio.run(run())


def test_teacher_os_says_and_records_without_a_graph() -> None:
    observations: list[tuple] = []

    class Db:
        def record_observation(self, *args, **kwargs):
            observations.append((args, kwargs))
            return 1

    published: list[tuple] = []
    core = SimpleNamespace(
        db=Db(),
        session_id="sess-1",
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda text, source="agent": published.append((text, source)),
    )
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    # A real turn sets this from what Core heard. Evidence is anchored to a
    # witnessed student act, so a direct-drive test has to supply one.
    os.turn_student_text = "banana"

    async def run() -> None:
        bad = await os.execute("say", {"teacher_line": "You are wrong."})
        assert bad["ok"] is False
        ok = await os.execute("say", {"teacher_line": "Look at the apple with me."})
        assert ok["ok"] is True
        ask = await os.execute("say", {"teacher_line": "What food do you see?"})
        assert ask["ok"] is True
        bare = await os.execute("say", {"teacher_line": "Look at all the food"})
        assert bare["ok"] is True
        assert published[-1] == ("Look at all the food", "agent")
        read = await os.execute("read_library", {"path": "units/gs3-u1-hello/map.md"})
        assert read["ok"] is True
        assert "greet-and-name" in read["text"]
        assert os.reads == ["units/gs3-u1-hello/map.md"]
        ev = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "greet-and-name",
                "outcome": "wrong",
                "mode": "name",
            },
        )
        assert ev["ok"] is True
        assert os.evidence[0]["outcome"] == "wrong"
        assert "banana" not in str(observations)

    asyncio.run(run())


def test_stream_text_that_fails_say_bounds_is_dropped() -> None:
    async def praise(_ctx):
        yield SimpleNamespace(type="text_delta", text="Yes, well done.")

    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id="sess-praise",
        store=SimpleNamespace(state_version=1, mode="FULL"),
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
        turn_registry=SimpleNamespace(register=lambda *a, **k: None, retire=lambda *_: None),
        agent=SimpleNamespace(prepare_turn=lambda *_: None, turn=praise),
    )
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    core.teacher_os = os

    async def run() -> None:
        body = await teacher_os._handle_teacher_turn(core, "the sky one")
        assert body["ok"] is False
        assert body["say"] is None

    asyncio.run(run())


def test_silent_hermes_does_not_replay_previous_say() -> None:
    async def silent_turn(_ctx):
        if False:
            yield None

    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id="sess-silent",
        store=SimpleNamespace(state_version=1, mode="FULL"),
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
        turn_registry=SimpleNamespace(register=lambda *a, **k: None, retire=lambda *_: None),
        agent=SimpleNamespace(prepare_turn=lambda *_: None, turn=silent_turn),
    )
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    os.last_say = "Welcome to the market, look at all the food."
    os.last_present = {"layout": "image", "slots": {"main": "asset://gs3/pages/p06.jpg"}}
    core.teacher_os = os

    async def run() -> None:
        body = await teacher_os._handle_teacher_turn(core, "that yellow one")
        assert body["ok"] is False
        assert body["say"] is None
        assert os.last_present["slots"]["main"] == "asset://gs3/pages/p06.jpg"
        assert core.last_teacher_fault and core.last_teacher_fault.get("error")

    asyncio.run(run())


def test_another_unit_is_only_more_library_files() -> None:
    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id="sess-2",
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
    )
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-2")

    async def run() -> None:
        read = await os.execute("read_library", {"path": os.map_path()})
        assert read["ok"] is True
        assert "answer-wellbeing" in read["text"]
        assert "lesson_run" not in read["text"]
        assert "goto" not in read["text"]
        keys = await os.execute("read_library", {"path": "units/gs3-u1-hello/keys.md"})
        assert keys["ok"] is True
        found = await os.execute("search_library", {"query": "answer-wellbeing"})
        assert found["ok"] is True
        assert any("gs3-u1-hello" in str(hit.get("path")) for hit in found["hits"])

    asyncio.run(run())


def test_record_evidence_keeps_mode_orthogonal_to_outcome() -> None:
    from db import open_database

    database = open_database(":memory:")
    database.upsert_student("learner-1", "Minh")
    session_id = database.start_session(student_id="learner-1", lesson_id="gs3-u1-hello")
    core = SimpleNamespace(db=database, session_id=session_id)
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    os.turn_student_text = "Hello, I'm Minh"

    async def run() -> None:
        # `mode` used to be optional, and a modeless row then fell silently out
        # of SKILL_CARD coverage (ATTEMPT_MODES is {name, point}) -- evidence
        # she recorded evaporating from the one thing that reads it.
        missing = await os.execute(
            "record_evidence",
            {"student_id": "learner-1", "objective_id": "greet-and-name", "outcome": "correct"},
        )
        assert missing["ok"] is False
        assert "mode is required" in missing["reason"]
        named = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "greet-and-name",
                "outcome": "correct",
                "mode": "name",
            },
        )
        assert named["ok"] is True
        point = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "ask-wellbeing",
                "outcome": "correct",
                "mode": "point",
            },
        )
        assert point["ok"] is True

        # Same objective, same turn -- refused. One row per objective per turn.
        again = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "greet-and-name",
                "outcome": "near",
                "mode": "name",
            },
        )
        assert again["ok"] is False
        assert "already recorded" in again["reason"]

        # A later turn, though, is the most valuable pattern this memory can
        # hold: wrong-then-right after scaffolding IS the learning, so the key
        # is (objective, turn) and never (objective, session).
        os.turn_recorded = set()
        os.turn_id = "bright-later-turn"
        later = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "greet-and-name",
                "outcome": "near",
                "mode": "name",
            },
        )
        assert later["ok"] is True
        refuse = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "take-leave",
                "outcome": "uncertain",
                "mode": "off-topic",
            },
        )
        assert refuse["ok"] is False
        invented = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "say-food-word",
                "outcome": "correct",
                "mode": "name",
            },
        )
        assert invented["ok"] is False

    asyncio.run(run())
    rows = database.list_observations(student_id="learner-1")
    assert [row["mode"] for row in rows] == ["name", "point", "name"]
    assert all((row["evidence"] or "").startswith("unit=") for row in rows)
    assert all("yellow" not in (row["evidence"] or "") for row in rows)
    student = database.get_student("learner-1")
    # record_evidence no longer touches the `skills` table -- the confidence
    # number it used to compute there saturated after four attempts
    # regardless of correctness and had no live reader. See
    # docs/decisions/2026-08-18-show-exercise-tool.md.
    assert student["skills"] == {}
    card, past = teacher_os.format_skill_memory(rows)
    assert "ask-wellbeing point supported=1 contradicted=0 no_decision=0" in card
    # correct on the first turn, `near` on a later one -- both rows count,
    # and `near` is a no_decision rather than support.
    assert "greet-and-name name supported=1 contradicted=0 no_decision=1" in card
    # PAST is a modeless row no more: mode is required, so every row names
    # how the answer was elicited.
    assert "greet-and-name name correct" in past
    later = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    recalled = teacher_os._session_recall(later)
    texts = [item.text for item in recalled]
    assert any(item.startswith("SKILL_CARD=") and "supported=1" in item for item in texts)
    assert any(item.startswith("PAST=") and "greet-and-name" in item for item in texts)
    assert any(item.startswith("student_id=learner-1") for item in texts)
    other = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-2")
    stranger = [item.text for item in teacher_os._session_recall(other)]
    assert not any(item.startswith("SKILL_CARD=") for item in stranger)
    database.close()


def test_the_turn_carries_no_raw_child_words() -> None:
    from db import open_database

    database = open_database(":memory:")
    database.upsert_student("learner-1", "Minh")
    core = SimpleNamespace(
        db=database,
        session_id=database.start_session(student_id="learner-1", lesson_id="gs3-u1-hello"),
        store=SimpleNamespace(mode="FULL"),
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
    )
    os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    os.turn_student_text = "cái màu vàng"

    async def run() -> None:
        await os.execute("say", {"teacher_line": "Look at this with me."})
        await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "ask-wellbeing",
                "outcome": "correct",
                "mode": "point",
            },
        )

    asyncio.run(run())
    texts = [item.text for item in teacher_os._session_recall(os)]
    assert not any(item.startswith("BEATS=") for item in texts), (
        "BEATS was a log Core wrote ABOUT her, from which she re-inferred where "
        "she was every turn. PLAN is an intention she writes herself."
    )
    joined = " ".join(texts)
    assert "yellow" not in joined, "no raw child words leave the turn"
    assert "cái" not in joined
    database.close()


def test_reopen_session_writes_summary_without_raw_words() -> None:
    from db import open_database

    database = open_database(":memory:")
    core = SimpleNamespace(db=database, store=SimpleNamespace(mode="FULL"))
    first = teacher_os.start_teacher_session(
        core, unit_id="gs3-u1-hello", learner_id="learner-sum", learner_name="Minh"
    )
    first_id = core.session_id
    first.turn_student_text = "Hello, I'm Minh"

    async def run() -> None:
        await first.execute(
            "record_evidence",
            {
                "student_id": "learner-sum",
                "objective_id": "greet-and-name",
                "outcome": "correct",
                "mode": "name",
            },
        )

    asyncio.run(run())
    teacher_os.start_teacher_session(
        core, unit_id="gs3-u1-hello", learner_id="learner-sum", learner_name="Minh"
    )
    ended = database.get_session(first_id)
    assert ended is not None and ended["ended_at"]
    summary = database.get_session_summary(first_id)
    assert summary is not None
    assert "greet-and-name" in summary["summary"]
    assert "apple" not in summary["summary"].replace("greet-and-name", "")
    assert core.session_id != first_id
    database.close()


def test_evidence_fails_closed_when_the_unit_is_missing() -> None:
    """A renamed or missing unit must reject evidence, not accept anything.

    The previous guard was `if allowed and objective not in allowed`, so an
    empty catalog disabled validation entirely -- silently, and exactly when a
    unit had just been renamed.
    """

    async def run() -> None:
        core = SimpleNamespace(db=None, session_id=None, store=None, bus=None)
        os_ = TeacherOS(core, unit_id="unit-that-does-not-exist", learner_id="learner-1")
        os_.turn_student_text = "Hello"
        got = await os_.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "anything-at-all",
                "outcome": "correct",
                "mode": "name",
            },
        )
        assert got["ok"] is False
        assert "no objectives" in got["reason"]
        assert os_.evidence == []

    asyncio.run(run())


CHOICE_CONTENT = {
    "prompt": "Which one is the apple?",
    "options": [
        {"id": "a", "text": "apple", "asset": "asset://gs3/pages/p10.jpg"},
        {"id": "b", "text": "banana"},
    ],
    "correct_id": "a",
}


def test_show_exercise_choice_never_emits_chosen_id() -> None:
    """The board must never grade one child in front of the class.

    ChoiceBoard.tsx renders `revealed.chosenId` as a red cross with
    aria-label="not correct" on whatever the child picked. `chosenId` is not
    in the show_exercise schema, so this asserts it is genuinely absent from
    the published scene -- not merely `None`.
    """
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        shown = await os_.execute("show_exercise", {"kind": "choice", "content": CHOICE_CONTENT})
        assert shown["ok"] is True
        revealed = await os_.execute(
            "show_exercise",
            {"kind": "choice", "content": {**CHOICE_CONTENT, "reveal": True}},
        )
        assert revealed["ok"] is True

    asyncio.run(run())
    assert len(frames) == 2
    props = _published_props(frames)
    assert props["revealed"] == {"correctId": "a"}
    assert "chosenId" not in props["revealed"]

    async def read() -> dict:
        return await os_.execute("read_board", {})

    board = asyncio.run(read())
    assert board["exercise"]["revealed"] == {"correctId": "a"}
    assert "chosenId" not in board["exercise"]["revealed"]


def test_show_exercise_vocabulary_forces_interaction_none() -> None:
    """A wrong `interaction` is dropped, not rejected -- that would burn a
    turn iteration for a non-mistake (see the show_exercise decision doc)."""
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    content = {
        "items": [
            {"id": "apple", "text": "apple", "asset": "asset://gs3/pages/p10.jpg"},
            {"id": "banana", "text": "banana"},
        ],
        "interaction": "tap",
        "highlight_id": "apple",
    }

    async def run() -> dict:
        return await os_.execute("show_exercise", {"kind": "vocabulary", "content": content})

    got = asyncio.run(run())
    assert got["ok"] is True
    props = _published_props(frames)
    assert props["interaction"] == "none"
    assert props["highlightId"] == "apple"


def test_two_asset_show_image_puts_both_assets_on_the_stage() -> None:
    """_push_stage used to read only `last_images["main"]`, silently dropping
    the second asset. A pair now routes through the vocabulary scene.

    The pair is spelled `asset` + `second`; `left`/`right` was a second,
    invisible calling convention and is gone from the wire schema."""
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> dict:
        return await os_.execute(
            "show_image",
            {"asset": "asset://gs3/pages/p10.jpg", "second": "asset://gs3/pages/p11.jpg"},
        )

    got = asyncio.run(run())
    assert got["ok"] is True
    assert frames, "show_image must publish a scene"
    kind = frames[-1][0][1]["kind"]
    props = _published_props(frames)
    assert kind == "vocabulary"
    assets = {item["asset"] for item in props["items"]}
    assert assets == {"asset://gs3/pages/p10.jpg", "asset://gs3/pages/p11.jpg"}
    assert props["interaction"] == "none"


def test_every_id_core_hands_her_is_an_id_core_accepts() -> None:
    """ASSETS= must survive the round trip back through the tools.

    It did not. The line stripped `asset://` before showing her the catalogue,
    and every tool that takes an asset requires the whole form -- so she copied
    exactly what Core handed her and Core refused it. Measured 2026-08-20 over
    one live period: show_image 4 of 5 refused, play_clip 3 of 3, all
    `asset-malformed`. The board was blank the entire lesson.

    This asserts the contract in the only direction that matters: whatever Core
    prints, Core must accept.
    """
    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    listed = [
        item.text[len("ASSETS=") :]
        for item in teacher_os._session_recall(os_)
        if item.text.startswith("ASSETS=")
    ]
    assert listed, "the unit prints assets; ASSETS= must name them"
    ids = [part.strip() for part in listed[0].split(",") if part.strip()]
    assert len(ids) > 1

    refused = [asset for asset in ids if teacher_os._as_asset(asset) is None]
    assert not refused, f"Core printed ids its own _as_asset refuses: {refused[:3]}"
    missing = [asset for asset in ids if teacher_os._media_file(asset) is None]
    assert not missing, f"Core printed ids with no file behind them: {missing[:3]}"

    # And prove it through the tool a child actually sees, not just the helper.
    picture = next(a for a in ids if a.endswith((".jpg", ".png")))
    clip = next(a for a in ids if a.endswith(".mp3"))

    async def run() -> tuple[dict, dict]:
        return (
            await os_.execute("show_image", {"asset": picture}),
            await os_.execute("play_clip", {"asset": clip, "transcript": "Hello."}),
        )

    shown, played = asyncio.run(run())
    assert shown["ok"] is True, shown
    assert played["ok"] is True, played


def _record(os_: TeacherOS, objective: str, outcome: str) -> None:
    """One evidence row, through the real path, with the turn gate satisfied."""
    os_.turn_kind = None
    os_.turn_student_text = "Fine"
    os_.turn_recorded = set()

    async def run() -> dict:
        return await os_.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": objective,
                "outcome": outcome,
                "mode": "name",
            },
        )

    got = asyncio.run(run())
    assert got.get("ok") is True, got


def test_attempts_are_counted_not_collapsed() -> None:
    """The pacing law is "attempts are the measure", and attempts were a set.

    `period_evidence` deduplicated, so ten identical `answer-wellbeing wrong`
    rows became ONE entry. Measured live 2026-08-20: twelve observations in SQL,
    ten of them wrong, rendered as `THIS_PERIOD=answer-wellbeing x2`, and the
    period census reported `outcomes {correct: 1, near: 1, wrong: 1}`. Both
    instruments told us the marking was healthy while the child failed the same
    thing ten times in a row.
    """
    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    for _ in range(4):
        _record(os_, "answer-wellbeing", "wrong")
    _record(os_, "answer-wellbeing", "near")

    census = teacher_os.period_census(os_)
    assert census["outcomes"] == {"wrong": 4, "near": 1}, census["outcomes"]
    assert census["evidenceRows"] == 5

    texts = [item.text for item in teacher_os._session_recall(os_)]
    line = next(t for t in texts if t.startswith("THIS_PERIOD="))
    assert "x5" in line, f"four wrongs and a near is five attempts: {line}"
    assert "wrong 4" in line, (
        f"'tried five times' and 'failed four times' must not read alike: {line}"
    )

    # Reads stay a SET -- "did she ever open this" is a different question, and
    # collapsing repeats there is still right.
    os_.period_reads.clear()
    for _ in range(3):
        os_._note_use("read_library", {}, {"path": "how-to-teach.md"})
    assert os_.period_reads == ["how-to-teach.md"]


def test_she_is_told_the_objectives_after_the_map_leaves_her_context() -> None:
    """She opens map.md on turn one and never again; store:false keeps nothing.

    Same fix, same reason as ASSETS=: she remembers that objectives exist, not
    what they are called. Which one to work on stays hers -- the map groups them
    by period and Core never reads that grouping.
    """
    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    texts = [item.text for item in teacher_os._session_recall(os_)]
    line = next((t for t in texts if t.startswith("OBJECTIVES=")), None)
    assert line, "the unit's objective ids must survive the map going out of context"
    listed = {part.strip() for part in line[len("OBJECTIVES=") :].split(",")}
    assert {"greet-and-name", "answer-wellbeing", "take-leave"} <= listed, listed

    # Core lists them; Core must not rank them. No period grouping, no "next".
    assert "period" not in line.lower()
    assert "next" not in line.lower()


def test_she_is_told_what_she_has_already_used_this_period() -> None:
    """"No clip played all period" was the adult's finding and never hers.

    period_census has carried clips/images/exercises since it was written, and
    its docstring names the reason: no single turn can show it. That went to
    /teacher/status and stopped there. Measured 2026-08-20: a whole period with
    clips=[] beside an ASSETS= line offering ten recordings.

    `images=`/`clip=` in the same block are the CURRENT scene, which says
    nothing about the twenty minutes before it -- so this is a different fact,
    not a duplicate one.
    """
    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    def line() -> str:
        texts = [item.text for item in teacher_os._session_recall(os_)]
        return next(t for t in texts if t.startswith("USED_SO_FAR="))

    # An empty period must SAY it is empty. Omitting the line when nothing has
    # been used is the bug BOARD=empty was added to fix: "nothing yet" and "I
    # was not told" would read identically.
    assert "clips none" in line(), line()

    async def run() -> None:
        await os_.execute("show_image", {"asset": "asset://gs3/panels/char-mai.jpg"})
        await os_.execute(
            "play_clip",
            {"asset": "asset://gs3/audio/track-09.mp3", "transcript": "How are you?"},
        )

    asyncio.run(run())
    after = line()
    assert "clips track-09" in after, after
    assert "images char-mai" in after, after

    # It is the period, not the board: put a different picture up and the first
    # one must still be listed.
    asyncio.run(os_.execute("show_image", {"asset": "asset://gs3/panels/char-ben.jpg"}))
    both = line()
    assert "char-mai" in both and "char-ben" in both, both


def test_show_exercise_refuses_evaluative_text() -> None:
    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    content = {**CHOICE_CONTENT, "prompt": "You are correct, well done!"}

    async def run() -> dict:
        return await os_.execute("show_exercise", {"kind": "choice", "content": content})

    got = asyncio.run(run())
    assert got["ok"] is False
    assert os_.last_exercise is None


def test_show_exercise_choice_structural_validation() -> None:
    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def check(content: dict) -> dict:
        return await os_.execute("show_exercise", {"kind": "choice", "content": content})

    too_few = asyncio.run(check({**CHOICE_CONTENT, "options": [CHOICE_CONTENT["options"][0]]}))
    assert too_few["ok"] is False

    duplicate = asyncio.run(
        check(
            {
                **CHOICE_CONTENT,
                "options": [
                    {"id": "a", "text": "apple"},
                    {"id": "a", "text": "another apple"},
                ],
            }
        )
    )
    assert duplicate["ok"] is False

    unknown_correct = asyncio.run(check({**CHOICE_CONTENT, "correct_id": "z"}))
    assert unknown_correct["ok"] is False

    valid = asyncio.run(check(CHOICE_CONTENT))
    assert valid["ok"] is True


def test_record_evidence_without_student_id_writes_no_row() -> None:
    from db import open_database

    database = open_database(":memory:")
    database.upsert_student("learner-1", "Minh")
    core = SimpleNamespace(
        db=database,
        session_id=database.start_session(student_id="learner-1", lesson_id="gs3-u1-hello"),
    )
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> dict:
        return await os_.execute(
            "record_evidence",
            {"objective_id": "greet-and-name", "outcome": "correct"},
        )

    got = asyncio.run(run())
    assert got["ok"] is False
    assert database.list_observations(student_id="learner-1") == []
    database.close()


def test_record_evidence_rejects_a_choral_placeholder() -> None:
    from db import open_database

    database = open_database(":memory:")
    database.upsert_student("learner-1", "Minh")
    core = SimpleNamespace(
        db=database,
        session_id=database.start_session(student_id="learner-1", lesson_id="gs3-u1-hello"),
    )
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def try_id(student_id: str) -> dict:
        return await os_.execute(
            "record_evidence",
            {"student_id": student_id, "objective_id": "greet-and-name", "outcome": "correct"},
        )

    for placeholder in ("class", "Everyone", "CHORAL", "all"):
        got = asyncio.run(try_id(placeholder))
        assert got["ok"] is False, placeholder

    wrong_learner = asyncio.run(try_id("some-other-child"))
    assert wrong_learner["ok"] is False

    assert database.list_observations(student_id="learner-1") == []
    database.close()


def test_writing_after_a_picture_actually_reaches_the_board() -> None:
    """The most recent hand wins, or her chalk is invisible.

    last_images / last_exercise persist across turns so read_board can report
    them. Under a fixed ranking, a picture shown in an earlier turn beats
    writing she has just put up -- and the writing never reaches the
    projector at all.
    """
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        shown = await os_.execute("show_image", {"asset": "asset://gs3/pages/p10.jpg"})
        assert shown["ok"] is True, shown
        assert frames[-1][0][1]["kind"] == "image"

        wrote = await os_.execute("write_board", {"text": "# Hello"})
        assert wrote["ok"] is True, wrote
        assert frames[-1][0][1]["kind"] == "text"
        assert "Hello" in _published_props(frames)["text"]

        # and a picture after writing still wins
        again = await os_.execute("show_image", {"asset": "asset://gs3/pages/p11.jpg"})
        assert again["ok"] is True, again
        assert frames[-1][0][1]["kind"] == "image"

    asyncio.run(run())


def test_the_board_refuses_a_script_this_classroom_cannot_read() -> None:
    """The hosted model's own language must not reach the projector.

    Observed live 2026-08-18: MiMo (a Chinese model) wrote
    "不用唱出来，听听就好" onto the board in a Vietnamese classroom. A prompt
    instruction is not a control for this.

    The permitted set is not hardcoded -- NS-7 says software never names a
    language. It is derived from the writing systems the appliance's own
    authored curriculum uses, so a deployment that teaches in another script
    is allowed it automatically.
    """
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        leaked = await os_.execute("write_board", {"text": "# 不用唱出来"})
        assert leaked["ok"] is False, leaked

        spoken = await os_.execute("say", {"teacher_line": "听听就好"})
        assert spoken["ok"] is False, spoken
        assert "han" in spoken["reason"]

        # the languages the library is actually written in still pass
        fine = await os_.execute("write_board", {"text": "# Xin chào\n- Hello"})
        assert fine["ok"] is True, fine

    asyncio.run(run())


def test_speaking_and_chalking_are_one_call_but_not_one_string() -> None:
    """She writes while she talks, and the words are usually different.

    Speaking and chalking are one physical act, so they belong in one call --
    that is the whole reason `board_text` lives on `say`. But a teacher says
    "look at this one together" and writes just the word, so the two must not
    be forced to share a string.

    Everything else she can do -- a picture, a clip, an exercise -- is a
    DIFFERENT act and stays a different tool. A merged tool was tried on
    2026-08-19 and failed exactly there: one malformed sub-field killed the
    speech too, and the model then repeated the call until the circuit breaker
    took the room out of the turn. In a classroom with no adult in the loop,
    that is a teacher standing silent in front of children.
    """
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        spoken = await os_.execute(
            "say", {"teacher_line": "Look at this one together.", "board_text": "banana"}
        )
        assert spoken["ok"] is True, spoken
        assert os_.last_writing == "banana"
        assert os_.last_say == "Look at this one together."
        assert _published_props(frames)["text"] == "banana"

        # Most lines need no board, and must not disturb the one already there.
        plain = await os_.execute("say", {"teacher_line": "Now you try."})
        assert plain["ok"] is True, plain
        assert os_.last_writing == "banana", "a silent line must not wipe the board"

    asyncio.run(run())


def test_a_refused_board_text_never_silences_her_but_is_never_silent_either() -> None:
    """The chalk rides on `say` only because it degrades instead of failing.

    A malformed picture or exercise costs one move; a malformed `say` costs the
    class its teacher. So bad `board_text` is skipped and she still speaks --
    but skipping SILENTLY was its own bug: she believed she had written, and
    the next turn's WRITING= disagreed with her. The result must name what
    happened to the board, in words she can act on inside the same turn.
    """
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        good = await os_.execute(
            "say", {"teacher_line": "Look at this word.", "board_text": "banana"}
        )
        assert good["board"] == "applied", good

        # Han script: the classroom does not read it, and the refusal has to
        # say so rather than dropping the chalk on the floor.
        bad = await os_.execute(
            "say", {"teacher_line": "Try this one.", "board_text": "\u9999\u8549"}
        )
        assert bad["ok"] is True, "a bad board must never silence her"
        assert os_.last_say == "Try this one."
        assert bad["board"].startswith("skipped:"), bad
        assert "script" in bad["board"], bad
        assert os_.last_writing == "banana", "the old board survives a refusal"

        # No board asked for is not a failure, and must not read like one.
        none = await os_.execute("say", {"teacher_line": "Now you try."})
        assert none["board"] == "none", none

    asyncio.run(run())


def test_show_image_without_a_picture_is_refused_by_the_schema() -> None:
    """Every argument used to be optional, so `show_image({turn_id})` passed
    validation and only failed at execute -- a wasted round-trip a child sits
    through, handed free to any model that guesses. This is the same
    all-optional trap that killed the merged `teach` tool on 2026-08-19.
    """
    schema = TOOLS_BY_NAME["show_image"]["inputSchema"]
    assert "asset" in schema["required"]
    assert "left" not in schema["properties"], "one spelling of the argument, not two"
    assert "right" not in schema["properties"]


def test_record_evidence_never_offers_a_mode_it_always_refuses() -> None:
    """`off-topic` was legal in the enum and rejected unconditionally in
    execute. A schema-legal value that always fails is a landmine for a small
    model, which trusts an enum over the prose beside it."""
    modes = TOOLS_BY_NAME["record_evidence"]["inputSchema"]["properties"]["mode"]["enum"]
    assert "off-topic" not in modes
    assert set(modes) == {"name", "point", "ask"}


def test_the_turn_census_counts_tools_and_never_carries_words() -> None:
    """The six-month tell for an offline model that has quietly degraded.

    An E4B that stops bundling, or stops touching the board and just talks,
    looks like a working teacher in any single transcript. Only the counts
    show it: tools per turn falling toward one, board_touched collapsing.

    A persisted `last_writing` must not count as touching the board -- a false
    positive here hides the exact failure the counter exists to catch.
    """
    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        await os_.execute("write_board", {"text": "# Hello"})
        assert os_.turn_tools == ["write_board"]

        # A chalked say counts; a plain say the turn after does not, even
        # though the board still shows the earlier writing.
        os_.turn_tools, os_.turn_chalked = [], False
        await os_.execute("say", {"teacher_line": "Look.", "board_text": "banana"})
        assert os_.turn_chalked is True

        os_.turn_tools, os_.turn_chalked = [], False
        await os_.execute("say", {"teacher_line": "Now you try."})
        assert os_.last_writing == "banana", "the board still shows it"
        assert os_.turn_chalked is False, "but THIS turn did not touch the board"

        # Refusals are bucketed, never quoted.
        os_.turn_refusals = []
        await os_.execute("show_image", {"asset": "asset://../secret.png"})
        assert os_.turn_refusals, "a refusal must be counted"
        for entry in os_.turn_refusals:
            assert "secret" not in entry, "the census must not echo arguments"

    asyncio.run(run())


def _plan_core(session_id: str = "sess-plan"):
    from db import open_database

    database = open_database(":memory:")
    database.upsert_student("learner-1", "Minh")
    core = SimpleNamespace(
        db=database,
        session_id=database.start_session(student_id="learner-1", lesson_id="gs3-u1-hello"),
        store=SimpleNamespace(mode="FULL"),
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
    )
    return core, database


def test_core_stores_her_plan_and_never_branches_on_a_word_of_it() -> None:
    """This is the line between an agent and the cassette this repo deleted.

    She may write anything in her plan. Core's job is to keep it and hand it
    back -- never to read it and decide something. Two wildly different plans
    must therefore leave the room in exactly the same state, and both must
    come back to her verbatim on the next turn.
    """
    core, database = _plan_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        first = await os_.execute(
            "plan", {"plan": "Greet, then the two dialogue panels, then names."}
        )
        assert first["ok"] is True and first["revision"] == 1

        state_a = (os_.last_writing, dict(os_.last_images), os_.last_say, os_.unit_id)

        # A plan that names a tool, a phase, a number -- none of it may steer
        # anything. If Core ever grows an `if "exercise" in plan`, this fails.
        second = await os_.execute(
            "plan", {"plan": "SKIP the dialogue. show_exercise now. close after 2 minutes."}
        )
        assert second["ok"] is True and second["revision"] == 2

        state_b = (os_.last_writing, dict(os_.last_images), os_.last_say, os_.unit_id)
        assert state_a == state_b, "the plan's words changed the room"

        # It comes back to her, verbatim, on the next turn.
        texts = [item.text for item in teacher_os._session_recall(os_)]
        assert "PLAN=SKIP the dialogue. show_exercise now. close after 2 minutes." in texts

    asyncio.run(run())
    database.close()


def test_her_plan_survives_a_restart_because_it_is_not_in_the_context_window() -> None:
    """A plan lives in SQL, not in the conversation. Restart the teacher, never
    the lesson: what she meant to do next has to outlast the process, and a
    harness NS-4 says is replaceable."""
    core, database = _plan_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        await os_.execute("plan", {"plan": "Panels first, then their own names."})

    asyncio.run(run())

    # The process dies; only the database survives.
    core.teacher_os = None
    resumed = teacher_os.resume_teacher_session(core)
    assert resumed is not None, "an open session must be re-attachable"
    assert resumed.plan == "Panels first, then their own names."
    database.close()


def test_a_plan_with_no_session_is_refused_rather_than_lost() -> None:
    """Failing closed: a plan written with nowhere to store it must say so,
    not return ok and vanish at the next restart."""
    core, _frames = _stage_core()
    core.db = None
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        got = await os_.execute("plan", {"plan": "Panels first."})
        assert got["ok"] is False, got

    asyncio.run(run())


def test_preparation_cannot_speak_show_or_record() -> None:
    """Before class the room is empty and the projector is dark.

    "The Stage is the only loudspeaker" is not a thing to ask an agent nicely
    for, so a preparation turn is stopped in `execute`, not in the prompt. The
    same guard covers evidence: there is no child in the room to attribute
    anything to.

    This is also why preparation does NOT run on the harness's own cron or
    child agents. Verified upstream 2026-08-19: a platform whose
    `platform_toolsets` names no MCP server gets every globally-enabled MCP
    server unioned in (hermes_cli/tools_config.py:2495), so a cron job asking
    for `[cronjob, delegation]` would be handed `bright-classroom` -- and `say`
    with it. Nothing upstream blocks an MCP tool by name for a child agent.
    """
    core, database = _plan_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    os_.turn_kind = "prepare"

    async def run() -> None:
        for name, args in (
            ("say", {"teacher_line": "Good morning!"}),
            ("write_board", {"text": "# Hello"}),
            ("show_image", {"asset": "asset://gs3/pages/p10.jpg"}),
            ("show_exercise", {"kind": "choice", "content": {}}),
            ("play_clip", {"asset": "asset://gs3/audio/a1.mp3"}),
            (
                "record_evidence",
                {
                    "student_id": "learner-1",
                    "objective_id": "ask-wellbeing",
                    "outcome": "correct",
                },
            ),
        ):
            got = await os_.execute(name, args)
            assert got["ok"] is False, f"{name} must not work before the room fills"
        assert os_.last_say is None, "nothing may reach the loudspeaker"
        assert os_.last_writing is None, "nothing may reach the projector"

        # Reading and planning are exactly what preparation is for.
        assert (await os_.execute("read_library", {"path": "how-to-teach.md"}))["ok"]
        assert (await os_.execute("plan", {"plan": "Panels, then their names."}))["ok"]

    asyncio.run(run())
    database.close()


def test_a_period_prepared_last_night_starts_with_that_plan() -> None:
    """Preparation is the only place an offline 4B is allowed to be slow, and
    therefore the only place it is allowed to be thorough -- nobody is waiting.
    The point is that the morning inherits the work."""
    from db import open_database

    database = open_database(":memory:")
    database.upsert_student("learner-1", "Minh")
    core = SimpleNamespace(
        db=database,
        session_id=None,
        student_id=None,
        teacher_os=None,
        settings=SimpleNamespace(default_learner_id="learner-1"),
        store=SimpleNamespace(mode="FULL"),
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
    )
    database.save_lesson_plan(
        teacher_os.prepared_plan_id("gs3-u1-hello"),
        "gs3-u1-hello",
        "Start with the panels; they only pointed last time.",
    )

    os_ = teacher_os.start_teacher_session(
        core, unit_id="gs3-u1-hello", learner_id="learner-1", learner_name="Minh"
    )
    assert os_.plan == "Start with the panels; they only pointed last time."
    # And it is copied onto the live session, so revising it tonight does not
    # rewrite what she actually did this morning.
    assert (database.get_lesson_plan(core.session_id) or {})["plan"] == os_.plan
    database.close()


def test_preparation_refuses_to_run_while_a_class_is_in_progress() -> None:
    """A second teacher thinking out loud during a lesson is the one thing the
    turn lock exists to prevent."""
    core, database = _plan_core()
    core.teacher_os = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    got = asyncio.run(teacher_os.prepare_period(core, unit_id="gs3-u1-hello"))
    assert got["ok"] is False
    assert "in progress" in got["error"]
    database.close()


def test_core_is_a_witness_not_a_marker() -> None:
    """Where Core's refusal stops and her judgement starts.

    Core may refuse a claim about the room it witnessed: no turn happened, no
    child spoke, this row is already written, that objective is not on the map.
    Core may never rule on whether the answer was good enough -- that lives in
    keys.md, which is curriculum, which Python must never read.

    The observed failure on 2026-08-19: a pupil said "em chưa hiểu" (*I don't
    understand*) and `take-leave` was recorded `correct` on that turn. She was
    recording the utterance she wished she had heard. Core cannot know the
    answer was poor, but it does know nobody said anything a child could have
    meant by it -- and on a heartbeat, that nobody spoke at all.
    """
    core, database = _plan_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    good = {
        "student_id": "learner-1",
        "objective_id": "take-leave",
        "outcome": "correct",
        "mode": "name",
    }

    async def run() -> None:
        # No child spoke this turn -> nothing to record.
        os_.turn_student_text = ""
        empty = await os_.execute("record_evidence", dict(good))
        assert empty["ok"] is False
        assert "no child spoke" in empty["reason"]

        # A system event is not a child speaking, whichever event it is.
        for kind in ("heartbeat", "class_start", "prepare"):
            os_.turn_kind = kind
            os_.turn_student_text = "Goodbye"
            got = await os_.execute("record_evidence", dict(good))
            assert got["ok"] is False, kind
        os_.turn_kind = None

        # A real child act -> hers to judge, and Core does not second-guess it.
        os_.turn_student_text = "Goodbye"
        os_.turn_id = "bright-turn-1"
        first = await os_.execute("record_evidence", dict(good))
        assert first["ok"] is True
        assert os_.evidence[-1]["objective_id"] == "take-leave"

    asyncio.run(run())
    database.close()


def test_every_row_is_anchored_to_the_turn_it_claims_to_be_about() -> None:
    """`response_turn_id` used to be a fresh random uuid on every call.

    Two consequences, both silent: the unique index on
    (session_id, response_turn_id, skill) could never fire once, and no row
    could ever be traced back to the utterance it claims to be about. A false
    row was unfalsifiable after the fact; now it is one join.
    """
    core, database = _plan_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    os_.turn_student_text = "Goodbye"
    os_.turn_id = "bright-turn-7"

    async def run() -> None:
        await os_.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "take-leave",
                "outcome": "correct",
                "mode": "name",
            },
        )

    asyncio.run(run())
    rows = database.list_observations(student_id="learner-1")
    assert rows, "the row must exist"
    assert rows[-1]["response_turn_id"] == "bright-turn-7"
    database.close()


def test_the_exercise_wire_is_flat_because_a_nested_object_came_back_empty() -> None:
    """`content` used to be {"type": "object"} with no properties.

    Measured 2026-08-19 against google/gemini-3.7-flash: handed the exact
    payload verbatim in the prompt and told to send it, the model called
    show_exercise with `content: {}` -- empty. A provider translating an
    untyped object into a function declaration produces a field with nothing
    in it, so there is nothing for the model to fill.

    That is how the merged `teach` tool died (`board: {}`), and it is why three
    separate prompt fixes produced not one call across four live periods. It
    was never a prompting problem, and no amount of instruction could have made
    it one.
    """
    schema = TOOLS_BY_NAME["show_exercise"]["inputSchema"]
    props = schema["properties"]
    assert "content" not in props, "the nested object is what the model could not fill"
    assert schema["required"] == ["turn_id", "kind"], schema["required"]
    for field in ("prompt", "options", "correct_id", "items",
                  "environment", "ai_role", "student_role", "target_phrases"):
        assert field in props, field
    # Arrays carry a typed item shape, or the translator has nothing to offer
    # the model there either.
    for field in ("options", "items"):
        assert props[field]["items"]["type"] == "object"
        assert "id" in props[field]["items"]["properties"]


def test_a_flat_exercise_and_a_nested_one_both_reach_the_board() -> None:
    """The wire is flat; a nested `content` still works.

    Refusing a shape that carries the same information would be pedantry a
    child pays for in a wasted round-trip -- and it is how the older tests and
    any in-process caller spell it.
    """
    core, frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    cards = [
        {"id": "ben", "text": "Ben", "asset": "asset://gs3/panels/char-ben.jpg"},
        {"id": "mai", "text": "Mai", "asset": "asset://gs3/panels/char-mai.jpg"},
    ]

    async def run() -> None:
        flat = await os_.execute("show_exercise", {"kind": "vocabulary", "items": cards})
        assert flat["ok"] is True, flat
        assert os_.last_exercise["kind"] == "vocabulary"
        assert len(os_.last_exercise["content"]["items"]) == 2

        nested = await os_.execute(
            "show_exercise", {"kind": "vocabulary", "content": {"items": cards}}
        )
        assert nested["ok"] is True, nested

        # An empty one is refused with something she can act on, not silently.
        empty = await os_.execute("show_exercise", {"kind": "vocabulary"})
        assert empty["ok"] is False
        assert "needs its fields" in empty["reason"]

    asyncio.run(run())


def test_the_authored_exercises_are_the_call_itself() -> None:
    """A block copied out of exercises.md must BE the arguments.

    They were {kind, items:[...]} while the tool wanted {kind, content:{...}},
    so a model copying the authored block verbatim got a refusal and fell back
    to talking -- the same "two invisible spellings" disease removed from
    show_image, reintroduced between a tool and its own textbook.
    """
    import json as _json
    import re

    from library import LIBRARY_ROOT

    body = (LIBRARY_ROOT / "units/gs3-u1-hello/exercises.md").read_text(encoding="utf-8")
    blocks = [_json.loads(m) for m in re.findall(r"```json\n(\{.*?\})\n```", body, re.S)]
    assert blocks, "the unit must ship exercise payloads"

    core, _frames = _stage_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        for block in blocks:
            assert "content" not in block, f"authored block is not flat: {block.get('kind')}"
            got = await os_.execute("show_exercise", dict(block))
            assert got["ok"] is True, (block.get("kind"), got)

    asyncio.run(run())


def test_she_can_finally_call_the_adult() -> None:
    """NORTH-STAR §1 has listed five hand-over situations since the beginning
    and `skills/escalate-to-the-adult` tells her exactly how -- and until now
    she had no hand that reached a person. `say` goes to the loudspeaker and
    the board goes to the projector; neither is the adult.

    Doctrine with no mechanism is not a safety policy, it is a wish.
    """
    core, database = _plan_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        bad = await os_.execute("call_the_adult", {"reason": "because I am bored"})
        assert bad["ok"] is False, "the list is short on purpose"

        got = await os_.execute("call_the_adult", {
            "reason": "cannot_reach_the_class",
            "detail": "Lớp không trả lời. Cô nhờ thầy cô xem giúp ạ.",
        })
        assert got["ok"] is True, got
        assert core.escalation["reason"] == "cannot_reach_the_class"
        assert os_.escalated is True

        # She stopped -- but the period is NOT closed. A lesson handed to an
        # adult is not a period this class has had, and the room must still
        # show what the children were looking at when the adult walks in.
        assert getattr(core, "teacher_os", "untouched") == "untouched"
        assert getattr(core, "last_close_at", None) is None

        # And she can still speak, because the class needs one calm line.
        after = await os_.execute("say", {"teacher_line": "Let's wait a moment together."})
        assert after["ok"] is True

    asyncio.run(run())
    database.close()


def test_an_escalation_carries_no_child_words() -> None:
    """The adult is a person reading a line on a laptop, and everything else
    she writes is checked for URLs, markup and grade words. This is not the
    exception."""
    core, database = _plan_core()
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        got = await os_.execute("call_the_adult", {
            "reason": "equipment",
            "detail": "see http://fix.example.com for the manual",
        })
        assert got["ok"] is False
        assert "URL" in got["reason"] or "markup" in got["reason"]

    asyncio.run(run())
    database.close()
