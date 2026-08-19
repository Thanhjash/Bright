"""OpenClaw-style teacher heartbeat is an OS pulse, not a second teacher."""

from __future__ import annotations

import asyncio
import time
from types import SimpleNamespace

import teacher_os
from teacher_os import TeacherOS, pulse_teacher, teacher_status_payload


def test_say_heartbeat_ok_is_silent() -> None:
    published: list[str] = []
    core = SimpleNamespace(publish_speech=lambda text, source="agent": published.append(text))
    os_ = TeacherOS(core, unit_id="market-food", learner_id="learner-1")

    async def run() -> None:
        silent = await os_.execute("say", {"teacher_line": "HEARTBEAT_OK"})
        spoken = await os_.execute("say", {"teacher_line": "Look at the fruit with me."})
        assert silent["ok"] is True
        assert silent.get("silent") is True
        assert spoken["ok"] is True

    asyncio.run(run())
    assert published == ["Look at the fruit with me."]
    assert os_.last_say == "Look at the fruit with me."


def test_heartbeat_cannot_write_evidence() -> None:
    os_ = TeacherOS(SimpleNamespace(), unit_id="market-food", learner_id="learner-1")
    os_.turn_kind = "heartbeat"

    async def run() -> None:
        blocked = await os_.execute(
            "record_evidence",
            {"objective_id": "food-recognise-apple", "outcome": "correct", "mode": "name"},
        )
        assert blocked["ok"] is False
        assert "heartbeat" in blocked["reason"]

    asyncio.run(run())
    assert os_.evidence == []


def test_pulse_stays_asleep_without_a_session() -> None:
    core = SimpleNamespace(teacher_os=None, capability_leases=None)

    async def run() -> None:
        pulse = await pulse_teacher(core)
        assert pulse["action"] == "asleep"
        assert pulse["phase"] == "asleep"

    asyncio.run(run())


def test_pulse_stays_quiet_when_class_just_spoke(monkeypatch) -> None:
    called: list[str] = []

    async def fake_turn(core, text):
        called.append(text)
        return {"ok": True, "say": "Should not run"}

    monkeypatch.setattr(teacher_os, "handle_teacher_turn", fake_turn)
    monkeypatch.setattr(teacher_os, "hermes_up", lambda: True)
    os_ = TeacherOS(SimpleNamespace(), unit_id="market-food", learner_id="learner-1")
    os_.last_say = "What food do you see?"
    os_.last_say_at = time.time()
    core = SimpleNamespace(teacher_os=os_, capability_leases=None)

    async def run() -> None:
        pulse = await pulse_teacher(core)
        assert pulse["action"] == "HEARTBEAT_OK"
        assert pulse["reason"] == "recent"

    asyncio.run(run())
    assert called == []


def test_pulse_wakes_after_silence(monkeypatch) -> None:
    called: list[str] = []

    async def fake_turn(core, text):
        called.append(text)
        return {"ok": True, "say": "Anyone still with me?", "action": "say"}

    monkeypatch.setattr(teacher_os, "handle_teacher_turn", fake_turn)
    monkeypatch.setattr(teacher_os, "hermes_up", lambda: True)
    os_ = TeacherOS(SimpleNamespace(), unit_id="market-food", learner_id="learner-1")
    os_.last_say = "What food do you see?"
    os_.last_say_at = time.time() - 60
    os_.started_at = time.time() - 90
    core = SimpleNamespace(teacher_os=os_, capability_leases=None)

    async def run() -> None:
        # She was not waiting for anyone, so the quiet means the floor is hers
        # and the room hands it to her -- not a heartbeat, which is what a class
        # THINKING about her question gets.
        pulse = await pulse_teacher(core, reason="tick")
        assert pulse["say"] == "Anyone still with me?"
        assert called == ["[floor]"]

        # Same silence, but this time she asked something: now it is a
        # heartbeat, and the long patient floor applies.
        called.clear()
        os_.awaiting_answer = True
        os_.nudged_once = False         # the early nudge has not gone yet
        os_.last_heartbeat_at = None
        os_.last_say_at = time.time() - 60
        pulse = await pulse_teacher(core, reason="tick")
        assert called == ["[heartbeat]"], called

    asyncio.run(run())


def test_the_floor_comes_to_her_far_sooner_than_a_thinking_class_is_interrupted() -> None:
    """Two different silences. Treating them as one is why a period lasted
    three minutes: she waited 45 seconds to do anything, every time, including
    when nobody was coming."""
    calls: list[str] = []

    async def fake_turn(core, text):
        calls.append(text)
        return {"ok": True, "say": "Let's try it again together.", "action": "say"}

    import pytest  # noqa: PLC0415

    for awaiting, nudged, silence, expected in (
        (False, True, 13.0, ["[floor]"]),      # her floor, taken quickly
        (False, True, 8.0, []),                # too soon even for her
        (True, True, 13.0, []),                # they are thinking; leave them
        (True, False, 46.0, ["[heartbeat]"]),  # thinking long, but un-nudged
        # Asked, nudged, and STILL nothing. The wait expires: a teacher does not
        # stand at the front of the room forever. The floor comes back to her.
        (True, True, 46.0, ["[floor]"]),
    ):
        calls.clear()
        os_ = TeacherOS(SimpleNamespace(), unit_id="market-food", learner_id="learner-1")
        os_.last_say = "Say it with me."
        os_.last_say_at = time.time() - silence
        os_.started_at = time.time() - silence - 30
        os_.awaiting_answer = awaiting
        os_.nudged_once = nudged
        core = SimpleNamespace(teacher_os=os_, capability_leases=None)

        monkey = pytest.MonkeyPatch()
        monkey.setattr(teacher_os, "handle_teacher_turn", fake_turn)
        monkey.setattr(teacher_os, "hermes_up", lambda: True)
        try:
            asyncio.run(pulse_teacher(core, reason="tick"))
        finally:
            monkey.undo()
        assert calls == expected, (awaiting, nudged, silence, calls)


def test_status_reports_asleep_phase() -> None:
    core = SimpleNamespace(
        teacher_os=None,
        last_teacher_fault=None,
        capability_leases=None,
    )
    body = teacher_status_payload(core)
    assert body["phase"] == "asleep"
    assert body["sessionOpen"] is False
    assert "hermesUp" in body
    assert "readyToStart" in body


def test_pulse_opens_the_class_when_the_room_is_there(monkeypatch, tmp_path) -> None:
    """Power on, touch nothing, she greets the room.

    NS-1: no adult decision sits on the teaching path, including a button to
    begin. The Stage already claims the audio lease by itself; this is the
    gate that turns that into an open class.
    """
    opened: list[str] = []

    async def fake_turn(core, text):
        opened.append(text)
        return {"ok": True, "say": "Hello!"}

    monkeypatch.setattr(teacher_os, "handle_teacher_turn", fake_turn)
    monkeypatch.setattr(teacher_os, "hermes_up", lambda: True)
    monkeypatch.setattr(teacher_os, "speech_up", lambda: True)
    monkeypatch.setattr(
        teacher_os, "start_teacher_session",
        lambda core, **kw: setattr(core, "teacher_os", object()) or core.teacher_os,
    )

    core = SimpleNamespace(
        teacher_os=None,
        capability_leases=SimpleNamespace(expire=lambda: None, stage_owner="stage-1"),
        settings=None,
    )

    async def run() -> dict:
        return await pulse_teacher(core)

    pulse = asyncio.run(run())
    assert opened == ["[sat_down]"], "she must open with the arrival event, not a greeting of her own"
    assert pulse["reason"].startswith("presence:")


def test_pulse_will_not_open_a_class_into_a_dark_room(monkeypatch) -> None:
    """No stage lease means no projector, no speaker, and nobody there.

    Opening anyway would burn a hosted turn and start a lesson nobody sees.
    The local lease check must gate the health probes, so an idle appliance
    is not polling the network every ten seconds either.
    """
    probed: list[str] = []
    monkeypatch.setattr(teacher_os, "hermes_up", lambda: probed.append("hermes") or True)
    monkeypatch.setattr(teacher_os, "speech_up", lambda: probed.append("speech") or True)

    core = SimpleNamespace(
        teacher_os=None,
        capability_leases=SimpleNamespace(expire=lambda: None, stage_owner=None),
        settings=None,
    )

    pulse = asyncio.run(pulse_teacher(core))
    assert pulse["action"] == "asleep"
    assert probed == [], "an empty room must not cost a health probe"


def test_she_nudges_once_soon_after_asking_then_waits(monkeypatch) -> None:
    """Four seconds of wait after a question, not forty-five.

    The unit map tells her to count to four after asking. The ordinary silence
    floor is 45s, which is the right wait for a room that has drifted off, and
    the wrong one for a child who was just asked something and is thinking.

    One nudge, then the long floor takes over -- ask, wait, nudge once, move on.
    Nagging every few seconds would be worse than silence, and on a local model
    every prompt is CPU we own.
    """
    fired: list[str] = []

    async def fake_turn(core, text):
        fired.append(text)
        return {"ok": True, "say": "Take your time."}

    monkeypatch.setattr(teacher_os, "handle_teacher_turn", fake_turn)
    monkeypatch.setattr(teacher_os, "hermes_up", lambda: True)

    os_ = TeacherOS(SimpleNamespace(), unit_id="gs3-u1-hello", learner_id="learner-1")
    os_.awaiting_answer = True
    # Silence is measured from the LAST of several marks, started_at included.
    stale = time.time() - (teacher_os.WAIT_AFTER_QUESTION_S + 1)
    os_.started_at = stale
    os_.last_say_at = stale
    core = SimpleNamespace(teacher_os=os_, capability_leases=None)

    first = asyncio.run(pulse_teacher(core))
    assert fired == ["[heartbeat]"], "she should look up shortly after asking"
    assert first["reason"] == "waiting_for_an_answer"

    # ...and exactly once. The next tick falls back to the ordinary long floor,
    # which is nowhere near reached yet.
    second = asyncio.run(pulse_teacher(core))
    assert fired == ["[heartbeat]"], "one nudge, not nagging"
    assert second["action"] == teacher_os.HEARTBEAT_OK


def test_a_statement_gets_the_long_wait(monkeypatch) -> None:
    """She was explaining, not asking. Nobody owes her an answer."""
    fired: list[str] = []

    async def fake_turn(core, text):
        fired.append(text)
        return {"ok": True}

    monkeypatch.setattr(teacher_os, "handle_teacher_turn", fake_turn)
    monkeypatch.setattr(teacher_os, "hermes_up", lambda: True)

    os_ = TeacherOS(SimpleNamespace(), unit_id="gs3-u1-hello", learner_id="learner-1")
    os_.awaiting_answer = False
    stale = time.time() - (teacher_os.WAIT_AFTER_QUESTION_S + 1)
    os_.started_at = stale
    os_.last_say_at = stale
    core = SimpleNamespace(teacher_os=os_, capability_leases=None)

    pulse = asyncio.run(pulse_teacher(core))
    assert fired == [], "no nudge is owed after a statement"
    assert pulse["action"] == teacher_os.HEARTBEAT_OK


def test_an_interrupted_period_resumes_instead_of_starting_over(monkeypatch) -> None:
    """Restart the teacher, never the lesson.

    Pull the power mid-period and the room comes back. If she greets the class
    a second time, a child watching learns that this is a machine. The open
    session row is how the room remembers there was a lesson in progress, and
    `[heartbeat]` tells her to look up and carry on rather than open a class
    she is already teaching.
    """
    fired: list[str] = []

    async def fake_turn(core, text):
        fired.append(text)
        return {"ok": True, "say": "Where were we — Fine, thank you."}

    monkeypatch.setattr(teacher_os, "handle_teacher_turn", fake_turn)
    monkeypatch.setattr(teacher_os, "hermes_up", lambda: True)
    monkeypatch.setattr(teacher_os, "speech_up", lambda: True)
    monkeypatch.setattr(teacher_os, "list_units", lambda: ["gs3-u1-hello"], raising=False)

    interrupted = {"id": "sess-cut", "student_id": "learner-1", "lesson_id": "gs3-u1-hello"}
    core = SimpleNamespace(
        teacher_os=None,
        capability_leases=SimpleNamespace(expire=lambda: None, stage_owner="stage-1"),
        settings=None,
        db=SimpleNamespace(find_open_session=lambda: interrupted),
        store=SimpleNamespace(mode="OFFLINE"),
    )

    asyncio.run(pulse_teacher(core))

    assert fired == ["[heartbeat]"], "she must look up, not greet the class again"
    assert core.session_id == "sess-cut", "the same period, not a new one"
    assert core.teacher_os.unit_id == "gs3-u1-hello"


def test_she_ends_the_period_herself_and_the_room_does_not_reopen_it() -> None:
    """A teacher ends her own lesson; she does not run until someone stops her.

    Two halves, and the second is the one that bites. Closing must happen after
    the goodbye is spoken or the class never hears it -- and once closed, the
    room must not immediately open another period. The Stage still holds the
    audio lease and the pulse still ticks every ten seconds, so without a
    cooldown she would say goodbye and greet the same class three seconds
    later, forever.
    """
    ended: list[str] = []
    spoken: list[str] = []
    core = SimpleNamespace(
        db=SimpleNamespace(end_session=lambda sid, **k: ended.append(sid)),
        session_id="sess-1",
        publish_speech=lambda text, **k: spoken.append(text),
        store=SimpleNamespace(mode="OFFLINE"),
    )
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    core.teacher_os = os_

    async def run() -> dict:
        # Ending a period is a professional act with a procedure; Core enforces
        # that the procedure was opened, and reads none of it.
        await os_.execute("read_library", {"path": "skills/close-a-period/SKILL.md"})
        return await os_.execute("say", {"teacher_line": "Goodbye, see you next time.", "closing": True})

    result = asyncio.run(run())
    assert result["ok"] is True
    assert spoken == ["Goodbye, see you next time."], "the class must hear the goodbye"
    assert ended == ["sess-1"], "the session row must be closed"
    assert core.teacher_os is None, "the period is over"

    # And the room refuses to start another one straight away.
    core.capability_leases = SimpleNamespace(expire=lambda: None, stage_owner="stage-1")
    pulse = asyncio.run(pulse_teacher(core))
    assert pulse["action"] == "asleep", "she just closed; do not reopen the period"


def test_a_heartbeat_she_answers_with_silence_is_not_a_fault() -> None:
    """The SSE loop used to rebind `event`, the system-event name.

    After the stream finished, `event` held a stream frame, so `event ==
    "heartbeat"` was false however the turn had started. Silence was the right
    answer -- the class still had time to think -- and the room filed it as a
    fault anyway, which is how an adult reading /teacher/status learns to
    ignore the fault line. Found by the turn census printing a stream frame
    where the event name belonged.
    """
    # The stream MUST emit at least one frame, because the frame is the whole
    # bug: a generator that yields nothing never rebinds the loop variable and
    # the test passes against the broken code.
    async def silent_turn(_ctx):
        yield SimpleNamespace(type="done", reason="complete", detail=None)

    core = SimpleNamespace(
        db=SimpleNamespace(record_observation=lambda *a, **k: 1),
        session_id="sess-hb",
        store=SimpleNamespace(state_version=1, mode="FULL"),
        bus=SimpleNamespace(publish=lambda *a, **k: None),
        publish_speech=lambda *a, **k: None,
        turn_registry=SimpleNamespace(register=lambda *a, **k: None, retire=lambda *_: None),
        agent=SimpleNamespace(prepare_turn=lambda *_: None, turn=silent_turn),
        last_teacher_fault={"error": "stale"},
    )
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")
    core.teacher_os = os_

    got = asyncio.run(teacher_os._handle_teacher_turn(core, "[heartbeat]"))

    assert got["ok"] is True, got
    assert got["say"] is None, "silence was the right answer"
    assert core.last_teacher_fault is None, "silence is not a fault"


def test_she_can_ask_the_room_for_her_own_next_beat() -> None:
    """Without this there is structurally no such thing as an ACTIVITY.

    Her only wakes were a child speaking, one 7s nudge, and a 45s silence
    floor. So "say it together, three times, listening between each" is three
    rounds of a silent classroom -- and she simply never starts one. Measured
    2026-08-19: zero exercises and one picture across a whole period.

    A scheduled beat is not a heartbeat. A heartbeat may honestly answer
    HEARTBEAT_OK and stay quiet; for a move she asked for, that is the drill
    dying mid-round.
    """
    core = SimpleNamespace(publish_speech=lambda *a, **k: None)
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        plain = await os_.execute("say", {"teacher_line": "Look at this word."})
        assert plain["ok"] is True
        assert os_.wake_at is None, "no wake unless she asks for one"

        asked = await os_.execute(
            "say", {"teacher_line": "Say it with me: Hello!", "wake_in_s": 8}
        )
        assert asked["ok"] is True
        assert os_.wake_at is not None
        assert 5.0 <= os_.wake_at - time.time() <= 9.0

        # Clamped at both ends -- a drill beat is seconds, not an hour, and a
        # zero would mean "wake me before I have finished speaking".
        await os_.execute("say", {"teacher_line": "Again.", "wake_in_s": 9999})
        assert os_.wake_at - time.time() <= teacher_os.WAKE_MAX_S + 1
        await os_.execute("say", {"teacher_line": "Again.", "wake_in_s": 1})
        assert os_.wake_at - time.time() >= teacher_os.WAKE_MIN_S - 1

        # A plain line does NOT clear it any more. It used to, so the first
        # time she answered a child who interrupted her drill, the drill
        # silently ended and she went back to waiting.
        await os_.execute("say", {"teacher_line": "Yes, Minh -- good."})
        assert os_.wake_at is not None, "answering a child must not end the drill"

        # Only saying so clears it.
        await os_.execute("say", {"teacher_line": "That is enough of that.", "wake_in_s": 0})
        assert os_.wake_at is None

    asyncio.run(run())


def test_a_wake_turn_is_not_a_heartbeat() -> None:
    """Two different events, because the escape hatch differs. A heartbeat may
    honestly answer HEARTBEAT_OK; a beat she scheduled may not."""
    assert teacher_os.system_event("[wake]") == "wake"
    assert teacher_os.system_event("[heartbeat]") == "heartbeat"
    assert teacher_os.system_event("[wake]") != teacher_os.system_event("[heartbeat]")


def test_closing_without_the_procedure_is_refused_but_never_silences_her() -> None:
    """She ended a period after fifteen minutes and eight exchanges on
    2026-08-19, having never opened `close-a-period`.

    Core reads not a word of that skill -- it enforces only that the procedure
    was opened, exactly as READ_NOW names keys.md before she judges. And she is
    not silenced for it: the line is spoken, the period stays open, and the
    result says why. A refused `say` is a teacher standing mute in front of
    children, which is the one thing the tool surface exists to prevent.
    """
    published: list[str] = []
    core = SimpleNamespace(publish_speech=lambda text, source="agent": published.append(text))
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        early = await os_.execute(
            "say", {"teacher_line": "Goodbye, everyone!", "closing": True}
        )
        assert early["ok"] is True, "she must still be heard"
        assert published == ["Goodbye, everyone!"]
        assert "not closed" in early["board"], early
        assert "close-a-period" in early["board"]
        assert getattr(core, "last_close_at", None) is None, "the period must stay open"

        await os_.execute("read_library", {"path": "skills/close-a-period/SKILL.md"})
        proper = await os_.execute(
            "say", {"teacher_line": "Goodbye, everyone!", "closing": True}
        )
        assert proper["ok"] is True
        assert "not closed" not in proper["board"]

    asyncio.run(run())


def test_the_nudge_budget_belongs_to_the_question_not_the_sentence() -> None:
    """Why she waited for ever.

    `nudged_once` was reset on every `say`. So: she asks, the 7s nudge fires and
    sets it True, she speaks on that nudge turn -- and the reset puts it back to
    False. The room therefore never reached "asked, nudged, still nothing", and
    every silence for the rest of the period was classified as a class still
    thinking. Measured 2026-08-19: 84 heartbeats, not one teaching move.
    """
    core = SimpleNamespace(publish_speech=lambda *a, **k: None)
    os_ = TeacherOS(core, unit_id="gs3-u1-hello", learner_id="learner-1")

    async def run() -> None:
        await os_.execute("say", {"teacher_line": "What is this?", "awaiting_answer": True})
        assert os_.nudged_once is False, "a new question starts with its nudge unspent"

        os_.nudged_once = True                       # the early nudge fires
        # She speaks again while still waiting on the SAME question.
        await os_.execute("say", {"teacher_line": "Have a look at the picture."})
        assert os_.nudged_once is True, "the budget belongs to the question"
        assert os_.awaiting_answer is False, "a plain line is not another question"

        # Asking something new spends a fresh nudge.
        await os_.execute("say", {"teacher_line": "And this one?", "awaiting_answer": True})
        assert os_.nudged_once is False

    asyncio.run(run())


def test_an_alarm_that_repeats_every_twelve_seconds_is_an_alarm_nobody_reads() -> None:
    """Once she has handed the room over, she waits.

    Measured 2026-08-19: she called the adult on three consecutive floor turns,
    twelve seconds apart. The room must stop giving her the floor -- she is not
    teaching now, she is waiting for a person, and only a person ends that.

    A child speaking DOES end it, because a class that answers is a class she
    could reach after all.
    """
    calls: list[str] = []

    async def fake_turn(core, text):
        calls.append(text)
        return {"ok": True, "say": "Let's wait together.", "action": "say"}

    import pytest  # noqa: PLC0415

    os_ = TeacherOS(SimpleNamespace(), unit_id="gs3-u1-hello", learner_id="learner-1")
    os_.last_say_at = time.time() - 60
    os_.started_at = time.time() - 200
    os_.escalated = True
    core = SimpleNamespace(teacher_os=os_, capability_leases=None)

    monkey = pytest.MonkeyPatch()
    monkey.setattr(teacher_os, "handle_teacher_turn", fake_turn)
    monkey.setattr(teacher_os, "hermes_up", lambda: True)
    try:
        got = asyncio.run(pulse_teacher(core, reason="tick"))
        assert calls == [], "she must not be handed the floor while waiting"
        assert got["reason"] == "waiting_for_the_adult"

        # The room is NOT torn down -- the adult walks into what the children
        # were looking at, and the period can be picked up.
        assert core.teacher_os is os_
    finally:
        monkey.undo()
