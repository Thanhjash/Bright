from __future__ import annotations

import asyncio
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as speech_app


def test_cancelled_tts_retains_lock_until_native_synthesis_finishes(monkeypatch):
    asyncio.run(_exercise_cancelled_tts_lock(monkeypatch))


async def _exercise_cancelled_tts_lock(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    calls = 0

    def synthesize(_voice: str, _text: str, _speed: float):
        nonlocal calls
        calls += 1
        entered.set()
        release.wait(timeout=2)
        return b"wav", 0.01

    monkeypatch.setattr(speech_app, "_synthesize", synthesize)
    monkeypatch.setitem(speech_app._state, "voices", {"en": object()})

    first = asyncio.create_task(
        speech_app.speech(speech_app.SpeechRequest(input="first", voice="en"))
    )
    assert await asyncio.to_thread(entered.wait, 1)
    first.cancel()
    second = asyncio.create_task(
        speech_app.speech(speech_app.SpeechRequest(input="second", voice="en"))
    )
    await asyncio.sleep(0.05)
    assert calls == 1, "cancellation released the non-thread-safe Piper session"

    release.set()
    try:
        await first
    except asyncio.CancelledError:
        pass
    else:
        raise AssertionError("cancelled speech request did not propagate cancellation")
    await second
    assert calls == 2


def test_a_line_with_nothing_to_say_answers_instead_of_crashing(monkeypatch):
    """The regression test for two of her sentences going missing on camera.

    2026-08-21, twice in one lesson: `wave.Error: # channels not specified` out
    of `_synthesize`, a 500 to the browser, and the segment silently skipped
    mid-line. Piper writes the WAV header inside its loop over synthesized
    chunks, so text the phonemiser cannot voice never writes one.

    The engine must not be reached at all, and the caller must get something it
    can play, or the rest of the line goes down with the chunk.
    """
    asyncio.run(_exercise_unsayable(monkeypatch))


async def _exercise_unsayable(monkeypatch):
    def explode(*_args, **_kwargs):
        raise AssertionError("the engine was handed text with nothing to say")

    monkeypatch.setattr(speech_app, "_synthesize", explode)
    monkeypatch.setitem(speech_app._state, "voices", {"en": object()})

    for unsayable in ("...", "…", "?!", "🙂"):
        response = await speech_app.speech(
            speech_app.SpeechRequest(input=unsayable, voice="en")
        )
        assert response.status_code == 200, unsayable
        assert response.media_type == "audio/wav"
        # Visible, not silent: a skipped line an adult can find in a header and
        # a log is the whole difference from the 500 that left no record.
        assert response.headers["X-Tts-Skipped"] == "1", unsayable
        assert response.body, "an empty body is not a playable WAV"
