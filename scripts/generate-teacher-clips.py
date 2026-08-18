#!/usr/bin/env python3
"""Write spoken market clips. Not a live TTS path — files only."""

from __future__ import annotations

import shutil
import subprocess
import sys
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MEDIA = ROOT / "content" / "media"
PIPER_VOICE = ROOT / "models" / "piper" / "en_US-lessac-medium.onnx"
CLIPS = {
    "market/market.wav": "Look at the market.",
    "market/apple.wav": "Apple.",
    "market/banana.wav": "Banana.",
    "market/water.wav": "Water.",
    "colours/colours.wav": "Look at the colours.",
    "colours/red.wav": "Red.",
    "colours/blue.wav": "Blue.",
}


def _write_pcm(path: Path, pcm: bytes, rate: int = 16000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)


def _via_piper(text: str) -> bytes | None:
    if not PIPER_VOICE.is_file():
        return None
    try:
        from piper import PiperVoice
    except ImportError:
        return None
    voice = PiperVoice.load(str(PIPER_VOICE))
    chunks: list[bytes] = []
    for chunk in voice.synthesize(text):
        audio = getattr(chunk, "audio_int16_bytes", None) or getattr(chunk, "audio_bytes", None)
        if audio:
            chunks.append(bytes(audio))
    return b"".join(chunks) or None


def _via_espeak(text: str) -> bytes | None:
    binary = shutil.which("espeak-ng") or shutil.which("espeak")
    if not binary:
        return None
    raw = subprocess.run(
        [binary, "-v", "en-us", "-s", "130", "-w", "/dev/stdout", text],
        check=False,
        capture_output=True,
    )
    if raw.returncode != 0 or len(raw.stdout) < 44:
        return None
    try:
        import io

        with wave.open(io.BytesIO(raw.stdout), "rb") as wav:
            frames = wav.readframes(wav.getnframes())
            rate = wav.getframerate()
    except wave.Error:
        return None
    if rate == 16000:
        return frames
    # espeak often writes 22050; keep file as 16k by letting wave rewrite later
    tmp = MEDIA / "._espeak.wav"
    tmp.write_bytes(raw.stdout)
    try:
        with wave.open(str(tmp), "rb") as src:
            pcm = src.readframes(src.getnframes())
            got_rate = src.getframerate()
    finally:
        tmp.unlink(missing_ok=True)
    if got_rate != 16000:
        # store native rate if resample tools are absent
        return pcm if got_rate == 16000 else raw.stdout
    return pcm


def main() -> int:
    written = 0
    for name, line in CLIPS.items():
        path = MEDIA / name
        pcm = _via_piper(line)
        if pcm:
            _write_pcm(path, pcm)
            print(f"piper {path}")
            written += 1
            continue
        blob = _via_espeak(line)
        if blob and blob[:4] == b"RIFF":
            path.write_bytes(blob)
            print(f"espeak-wav {path}")
            written += 1
            continue
        if blob:
            _write_pcm(path, blob)
            print(f"espeak {path}")
            written += 1
            continue
        print(f"skip {name}: no piper voice and no espeak", file=sys.stderr)
    return 0 if written == len(CLIPS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
