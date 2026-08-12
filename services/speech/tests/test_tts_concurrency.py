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
