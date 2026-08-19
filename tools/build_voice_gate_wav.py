#!/usr/bin/env python3
"""Build the WAV Chromium plays as a fake microphone.

Referenced by `tests/node/voice_gate_playwright.mjs` since 2026-08-18 and never
committed, so every fake-microphone test in this repo has been unrunnable. This
is that file, rebuilt.

What Chromium wants from `--use-file-for-fake-audio-capture`: uncompressed
16-bit PCM, mono or stereo, 16000 or 48000 Hz. 44.1 kHz is not reliably
accepted. It loops the file forever unless the path ends in `%noloop`, and it
restarts at offset 0 on every fresh `getUserMedia`.

What the voice gate wants, which is the reason this script exists at all
(`apps/classroom-ui/src/speech/voiceGate.ts`):

  * CALIBRATION_MS = 1000  -- it measures the room's noise floor before the
    gate may open even once. Speech in the first second is speech the gate is
    still calibrating against, and it will raise the floor to match.
  * SILENCE_MS = 800       -- trailing quiet is how an utterance ENDS. Without
    it the clip never closes and `onClip` never fires.
  * MIN_CLIP_MS = 600      -- shorter takes are dropped, because Whisper
    invents words on them.

So: silence, speech, silence. The padding is not politeness, it is the protocol.

    ./tools/build_voice_gate_wav.py --say "Hello. I'm Minh." --voice en -o out.wav
    ./tools/build_voice_gate_wav.py --wav tests/room/audio/clean/q_animal__cat_bare.wav -o out.wav

It prints one JSON line so a test harness can read the exact spans back:

    {"path": "...", "preMs": 1400, "speechMs": 1350, "postMs": 1400, ...}
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import urllib.request
import wave
from pathlib import Path

SPEECH_URL = "http://127.0.0.1:8001"
# Chromium accepts 16k or 48k. 16k is also exactly what Whisper wants, so the
# fixture is the same rate end to end and nothing resamples behind our back.
RATE = 16000
# Comfortably over CALIBRATION_MS and SILENCE_MS, because the gate also needs a
# few poll ticks (POLL_MS = 40) to settle inside each window.
PAD_MS = 1400


def _tts(text: str, voice: str) -> bytes:
    body = json.dumps({"input": text, "voice": voice}).encode()
    req = urllib.request.Request(
        f"{SPEECH_URL}/audio/speech", data=body,
        headers={"content-type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as response:
        return response.read()


def _to_mono_16k(raw: bytes) -> tuple[bytes, int]:
    """PCM frames at RATE, mono, 16-bit. Returns (frames, duration_ms).

    ffmpeg rather than the stdlib: `audioop` was removed in Python 3.13, and
    ffmpeg is already a dependency of the room's test tooling. It also accepts
    whatever the source is -- Piper's 22050 Hz, a 16 kHz fixture, an mp3 -- and
    resamples once, correctly.
    """
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / "in"
        source.write_bytes(raw)
        target = Path(tmp) / "out.wav"
        subprocess.run(
            ["ffmpeg", "-v", "error", "-y", "-i", str(source),
             "-ac", "1", "-ar", str(RATE), "-c:a", "pcm_s16le", str(target)],
            check=True,
        )
        with wave.open(str(target), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
    return frames, round(len(frames) / 2 / RATE * 1000)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    source = ap.add_mutually_exclusive_group(required=True)
    source.add_argument("--say", help="speak this with our own TTS")
    source.add_argument("--wav", help="use an existing WAV (e.g. tests/room/audio/clean/*.wav)")
    ap.add_argument("--voice", default="en", help="en or vi (with --say)")
    ap.add_argument("--pad-ms", type=int, default=PAD_MS)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    if args.say:
        raw = _tts(args.say, args.voice)
    else:
        raw = Path(args.wav).read_bytes()
    speech, speech_ms = _to_mono_16k(raw)

    if speech_ms < 600:
        print(f"refusing: {speech_ms}ms is under the gate's MIN_CLIP_MS of 600",
              file=sys.stderr)
        return 2

    # Digital silence, not noise. The gate's floor adapts upward from whatever
    # it hears, so a hissy pad would raise the bar its own speech has to clear.
    pad = b"\x00\x00" * int(RATE * args.pad_ms / 1000)
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(RATE)
        wav.writeframes(pad + speech + pad)

    print(json.dumps({
        "path": str(out.resolve()),
        "preMs": args.pad_ms,
        "speechMs": speech_ms,
        "postMs": args.pad_ms,
        "totalMs": args.pad_ms * 2 + speech_ms,
        "rate": RATE,
        "said": args.say or args.wav,
    }))
    return 0


if __name__ == "__main__":
    sys.exit(main())
