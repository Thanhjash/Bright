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
            {"student_id": "learner-1", "objective_id": "greet-and-name", "outcome": "wrong"},
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

    async def run() -> None:
        missing = await os.execute(
            "record_evidence",
            {"student_id": "learner-1", "objective_id": "greet-and-name", "outcome": "correct"},
        )
        assert missing["ok"] is True
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
        named = await os.execute(
            "record_evidence",
            {
                "student_id": "learner-1",
                "objective_id": "greet-and-name",
                "outcome": "near",
                "mode": "name",
            },
        )
        assert named["ok"] is True
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
    assert [row["mode"] for row in rows] == [None, "point", "name"]
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
    assert "greet-and-name name supported=0 contradicted=0 no_decision=1" in card
    assert "greet-and-name -" in past
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
