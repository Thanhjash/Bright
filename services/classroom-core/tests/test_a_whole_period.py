"""A whole period, driven through the real machinery with a scripted teacher.

The live rehearsal needs a model and a network. This does not: it replaces only
the brain, and drives everything else -- the turn lock, the MCP turn registry,
the tool dispatch, the board, the evidence ledger, the census, the plan store,
the scheduled wake -- exactly as a real period does.

What it proves is what a lesson NEEDS FROM THE ROOM, not whether she teaches
well: that a period can contain a plan, a recording, several pictures, an
exercise, honest marking, a drill that lasts more than one exchange, and a
close -- and that the period census reports all of it. Every one of those was
missing or broken on 2026-08-19, and none of them is visible in a single turn.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import teacher_os
from teacher_os import TeacherOS


class ScriptedTeacher:
    """A brain that does what a teacher does, in the order a period does it.

    It is deliberately dumb: it replays a fixed list of tool calls per turn. It
    is not a model and makes no decisions -- if it did, this test would be
    measuring the script instead of the room.
    """

    def __init__(self, moves: list[list[tuple[str, dict]]]) -> None:
        self.moves = moves
        self.turn = 0
        self.executor = None
        self.refused: list[str] = []

    def prepare_turn(self, turn_id: str) -> None:
        self.turn_id = turn_id

    async def turn_stream(self, _ctx):
        calls = self.moves[min(self.turn, len(self.moves) - 1)]
        self.turn += 1
        for name, args in calls:
            got = await self.executor(name, args)
            if isinstance(got, dict) and got.get("ok") is False:
                self.refused.append(f"{name}: {got.get('reason')}")
        yield SimpleNamespace(type="done", reason="complete", detail=None)


def _room():
    from db import open_database

    database = open_database(":memory:")
    database.upsert_student("learner-1", "Minh")
    scenes: list[tuple] = []
    spoken: list[str] = []
    core = SimpleNamespace(
        db=database,
        store=SimpleNamespace(state_version=1, mode="FULL", decision_revision=0,
                              set_scene=lambda kind, props: {"kind": kind, "props": props,
                                                             "stateVersion": 1}),
        bus=SimpleNamespace(publish=lambda *a, **k: scenes.append(a)),
        publish_speech=lambda text, source="agent", **k: spoken.append(text),
        turn_registry=SimpleNamespace(register=lambda *a, **k: None, retire=lambda *_: None),
        settings=SimpleNamespace(default_learner_id="learner-1"),
        student_id="learner-1",
        teacher_os=None,
        session_id=None,
        last_teacher_fault=None,
    )
    return core, database, scenes, spoken


PANEL_A = "asset://gs3/panels/u1l1-dialogue-a.jpg"
PANEL_B = "asset://gs3/panels/u1l1-dialogue-b.jpg"
BEN = "asset://gs3/panels/char-ben.jpg"
TRACK = "asset://gs3/audio/track-05.mp3"


def test_a_period_can_contain_a_whole_lesson() -> None:
    core, database, _scenes, spoken = _room()
    os_ = teacher_os.start_teacher_session(
        core, unit_id="gs3-u1-hello", learner_id="learner-1", learner_name="Minh"
    )

    period = [
        # Open: read the map, write the plan, put the first panel up, model it.
        [
            ("read_library", {"path": "units/gs3-u1-hello/map.md"}),
            ("plan", {"plan": "P1 open 0-10 | P2 model 10-25 | P3 practice 25-45 | "
                              "P4 close 45-60  NOW=P1"}),
            ("show_image", {"asset": PANEL_A}),
            ("play_clip", {"asset": TRACK, "transcript": "Hello. I'm Ben."}),
            ("say", {"teacher_line": "Listen: Hello. I'm Ben.", "board_text": "# Hello!",
                     "wake_in_s": 8}),
        ],
        # Her own scheduled beat: a choral round, no child input needed.
        [("say", {"teacher_line": "Say it with me: Hello!", "wake_in_s": 8})],
        # The child answers. Read the key, judge it, record it.
        [
            ("read_library", {"path": "units/gs3-u1-hello/keys.md"}),
            ("record_evidence", {"student_id": "learner-1", "objective_id": "greet-and-name",
                                 "outcome": "near", "mode": "name"}),
            ("say", {"teacher_line": "Nearly! Add your name: Hello. I'm Minh."}),
        ],
        # A new picture and a real exercise, from the authored payloads.
        [
            ("show_image", {"asset": BEN, "second": PANEL_B}),
            # 2..8 items: one card is not a choice, and nine do not fit a wall.
            ("show_exercise", {"kind": "vocabulary", "content": {"items": [
                {"id": "ben", "text": "Ben", "asset": BEN},
                {"id": "mai", "text": "Mai", "asset": "asset://gs3/panels/char-mai.jpg"},
            ]}}),
            ("say", {"teacher_line": "Who is this? Point and say."}),
        ],
        # Better this time.
        [
            ("record_evidence", {"student_id": "learner-1", "objective_id": "greet-and-name",
                                 "outcome": "correct", "mode": "name"}),
            ("say", {"teacher_line": "Yes. Hello, Minh."}),
        ],
        # Close it herself.
        [("say", {"teacher_line": "Goodbye, everyone. See you next time.", "closing": True})],
    ]
    brain = ScriptedTeacher(period)
    brain.executor = os_.execute
    core.agent = SimpleNamespace(prepare_turn=brain.prepare_turn, turn=brain.turn_stream)

    pupil = ["[sat_down]", "[wake]", "Hello", "Ben", "Hello. I'm Minh.", "Goodbye"]

    async def run() -> None:
        for line in pupil:
            got = await teacher_os._handle_teacher_turn(core, line)
            assert got["ok"] is True, (line, got)

    census = None

    def capture(os_arg):
        nonlocal census
        census = teacher_os.period_census(os_arg)

    real_log = teacher_os._log_period_census
    teacher_os._log_period_census = capture
    try:
        asyncio.run(run())
    finally:
        teacher_os._log_period_census = real_log

    assert not brain.refused, f"the room refused a legal move: {brain.refused}"

    # She ended the period herself; nobody stopped her.
    assert core.teacher_os is None, "say(closing=True) must end the period"
    assert census is not None, "the period census must be taken before the OS is dropped"

    # What a lesson needs from the room, every one of which was missing or
    # broken when this was measured live on 2026-08-19.
    assert census["clips"] == ["track-05"], "a recording must reach the room"
    assert len(census["images"]) >= 3, f"the picture must change: {census['images']}"
    assert census["exercises"] == ["vocabulary"], "an exercise must reach the board"
    assert "units/gs3-u1-hello/keys.md" in census["reads"], "she must read the key"
    assert census["outcomes"] == {"near": 1, "correct": 1}, census["outcomes"]
    assert census["objectives"] == ["greet-and-name"], "she stayed in Period 1"

    # The plan she wrote survives in SQL, and Core never read a word of it.
    stored = database.get_lesson_plan(core.session_id) or {}
    assert "NOW=P1" in (stored.get("plan") or "")

    # The class heard the recording first and her line after it -- a voice that
    # is not hers is most of what a track is for -- and then every line she
    # said, in order, and nothing else.
    assert spoken[0] == "Hello. I'm Ben.", "the clip is heard, not just fetched"
    assert spoken[1].startswith("Listen:")
    assert spoken[-1].startswith("Goodbye")
    assert len(spoken) == 7, spoken
    database.close()


def test_the_room_refuses_the_moves_a_lesson_must_not_make() -> None:
    """The same machinery, driven at the things it is supposed to stop."""
    core, database, _scenes, _spoken = _room()
    os_ = teacher_os.start_teacher_session(
        core, unit_id="gs3-u1-hello", learner_id="learner-1", learner_name="Minh"
    )
    evidence = {"student_id": "learner-1", "objective_id": "greet-and-name",
                "outcome": "correct", "mode": "name"}

    bad = [
        # Evidence on the turn the class sat down: nobody has spoken yet.
        [("record_evidence", dict(evidence)), ("say", {"teacher_line": "Hello everyone."})],
        # Twice for one utterance.
        [("record_evidence", dict(evidence)), ("record_evidence", dict(evidence)),
         ("say", {"teacher_line": "Good."})],
        # An objective this unit does not have, and a mode that is not one.
        [("record_evidence", {**evidence, "objective_id": "say-food-word"}),
         ("record_evidence", {k: v for k, v in evidence.items() if k != "mode"}),
         ("say", {"teacher_line": "Let's try again."})],
    ]
    brain = ScriptedTeacher(bad)
    brain.executor = os_.execute
    core.agent = SimpleNamespace(prepare_turn=brain.prepare_turn, turn=brain.turn_stream)

    async def run() -> None:
        for line in ["[sat_down]", "Hello", "Hello"]:
            got = await teacher_os._handle_teacher_turn(core, line)
            assert got["ok"] is True, got

    asyncio.run(run())

    reasons = " | ".join(brain.refused)
    # The event check fires first on [sat_down] -- either way the row is refused
    # because nobody had spoken yet.
    assert "class_start is not student evidence" in reasons, reasons
    assert "already recorded" in reasons, reasons
    assert "not on the unit map" in reasons, reasons
    assert "mode is required" in reasons, reasons
    # And she was never silenced by any of it -- the class heard every line.
    rows = database.list_observations(student_id="learner-1")
    assert len(rows) == 1, f"exactly one honest row survives: {rows}"
    database.close()
