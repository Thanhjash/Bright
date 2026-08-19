"""Core and the live prompt must not know a unit's answer key."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

FORBIDDEN = (
    "banana.svg",
    "apple.svg",
    "water.svg",
    "market.svg",
    "yellow fruit",
    "the yellow one",
    "pointed at the yellow",
    "_WORD_ASSETS",
    "_align_board_to_said_word",
    "food-recognise-apple",
    "colour-recognise-red",
)

SCAN = (
    ROOT / "services" / "classroom-core" / "teacher_os.py",
    ROOT / "services" / "agent" / "bright_agent" / "hermes.py",
    ROOT / "infra" / "hermes" / "config.yaml",
)


def test_runtime_source_has_no_unit_answer_key() -> None:
    for path in SCAN:
        text = path.read_text(encoding="utf-8")
        for needle in FORBIDDEN:
            assert needle not in text, f"{path.name} still teaches {needle!r}"



def test_the_profession_does_not_live_in_a_prompt_constant() -> None:
    """NS-6: "never in Python, never in a state machine, **never in a prompt
    constant**."

    Reviewed 2026-08-19 and found in breach by our own hand: `render_teacher_turn`
    had grown "A choral round is: model it, wake in 8, listen, model it again",
    a whole what-to-do-when-the-room-is-quiet paragraph, and a judgement about
    when saying something again teaches less than checking. Each line was good
    teaching. Every one of them was in the wrong layer -- a file only an
    engineer can edit, in a project whose whole claim is that the people who
    know how to teach can improve the teacher without a build step.

    They now live in `skills/take-the-floor`, `put-up-an-exercise` and
    `judge-a-response`, where READ_NOW names them. This keeps them there.
    """
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[3]
    surfaces = {
        "hermes.py": root / "services/agent/bright_agent/hermes.py",
        "config.yaml": root / "infra/hermes/config.yaml",
    }
    # Phrases that only a curriculum author should be writing. Not a general
    # word list -- each one is a teaching instruction we actually had to remove.
    PEDAGOGY = (
        "a choral round is",
        "model it, wake in 8",
        "run the round again",
        "go back over the one they fumbled",
        "teaches less than finding out",
        "two new items per ten minutes",
        "scaffold down",
    )
    for name, path in surfaces.items():
        body = path.read_text(encoding="utf-8").lower()
        # Comments explain WHY a mechanism exists and may quote what moved out.
        body = re.sub(r"^\s*#.*$", "", body, flags=re.M)
        for phrase in PEDAGOGY:
            assert phrase not in body, (
                f"{name} contains teaching, not mechanism: {phrase!r}. "
                "It belongs in content/library/skills/, where READ_NOW can name it."
            )
