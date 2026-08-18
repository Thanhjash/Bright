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
