"""One voice per sentence, not one per teacher line.

The defect these lock down was measured on lines the teacher really said in a
live period on 2026-08-20. Every one of them code-switches, every one contains
a Vietnamese letter, and the old rule picked one voice for the whole line — so
the English the child is supposed to copy came out of the Vietnamese voice.

In a lesson whose subject IS the target language, the model pronunciation is
the one thing that must be right. And `say` never fails, so nothing in the
census could ever have shown this.
"""

from __future__ import annotations

import io
import sys
import wave
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app import _concat_wavs, _voice_spans


def spans(text: str, *, default: str = "en") -> list[tuple[str, str]]:
    return [
        (voice, chunk.strip())
        for voice, chunk in _voice_spans(text, default_voice=default, marked_voice="vi")
    ]


# Verbatim from .runtime/teacher-agent/logs — not invented for the test.
SAID_IN_A_REAL_PERIOD = [
    (
        "How are you? Mình khỏe, cảm ơn. Listen and say: Fine, thank you.",
        ["en", "vi", "en"],
    ),
    ("Không sao đâu. Say with me: Fine, thank you.", ["vi", "en"]),
    ("Fine, thank you! Now let's say goodbye: Goodbye!", ["en"]),
    ("Hello, Minh! How are you?", ["en"]),
]


@pytest.mark.parametrize("line,expected", SAID_IN_A_REAL_PERIOD)
def test_each_sentence_gets_its_own_voice(line: str, expected: list[str]) -> None:
    assert [voice for voice, _ in spans(line)] == expected, spans(line)


def test_the_english_a_child_must_copy_is_never_in_the_other_voice() -> None:
    """The whole point, stated as the thing that must not happen.

    Before: one Vietnamese letter anywhere put the entire line, English and
    all, through the Vietnamese voice.
    """
    line = "Không sao đâu. Say with me: Fine, thank you."
    english = [chunk for voice, chunk in spans(line) if voice == "en"]
    assert english == ["Say with me: Fine, thank you."], spans(line)


def test_neighbouring_sentences_in_one_language_are_one_span() -> None:
    """Fewer synthesis calls, and no prosody reset where no switch happened."""
    got = spans("Hello. I'm Mai. How are you?")
    assert len(got) == 1 and got[0][0] == "en", got


def test_a_line_with_no_sentence_end_still_speaks() -> None:
    assert spans("Fine, thank you") == [("en", "Fine, thank you")]
    assert spans("Không sao") == [("vi", "Không sao")]


def test_a_line_that_never_switches_is_one_call() -> None:
    """Segmentation must not tax the common case."""
    assert len(_voice_spans("Listen and repeat.", default_voice="en", marked_voice="vi")) == 1


def test_the_marked_script_goes_to_its_voice_whatever_was_requested() -> None:
    """The regression this file missed the first time.

    The parameter used to be `other_voice` -- "whichever voice is not the
    requested one" -- which is right only when the request asked for the
    un-marked voice. Build a Vietnamese fixture with `--voice vi` and every
    Vietnamese sentence went to the ENGLISH voice: this function's own defect,
    running backwards. It read as bad Vietnamese ASR, not as bad audio.

    "Con không biết cô ạ" came back from Whisper as
    'Concom BI letter 1EBT co letter 1E1' -- and forcing `language=vi` did not
    help, which is what proved the audio was wrong rather than the transcript.
    """
    for requested in ("en", "vi"):
        got = spans("Con không biết cô ạ", default=requested)
        assert got == [("vi", "Con không biết cô ạ")], (requested, got)

    # And the other direction still holds: English never lands in the marked
    # voice just because the caller named it.
    assert spans("Say with me: Fine, thank you.", default="en") == [
        ("en", "Say with me: Fine, thank you.")
    ]


def _wav(seconds: float, rate: int = 22050) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(b"\x00\x00" * int(rate * seconds))
    return buf.getvalue()


def test_joined_audio_keeps_every_span() -> None:
    joined = _concat_wavs([_wav(0.5), _wav(0.25)])
    with wave.open(io.BytesIO(joined), "rb") as wf:
        assert wf.getnframes() == int(22050 * 0.75)
        assert wf.getnchannels() == 1 and wf.getsampwidth() == 2


def test_mismatched_voices_refuse_rather_than_change_pitch() -> None:
    """A joined WAV at the wrong sample rate plays every span at the wrong pitch.

    One voice in the wrong language is bad; one voice at the wrong pitch is
    worse, and it would sound like a broken appliance rather than a teacher.
    The endpoint catches this and falls back to a single voice.
    """
    with pytest.raises(ValueError):
        _concat_wavs([_wav(0.2, rate=22050), _wav(0.2, rate=16000)])
