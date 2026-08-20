"""VieNeu-TTS v3 Turbo behind the TtsProvider seam, with a disk cache.

WHY THIS ENGINE. Measured here 2026-08-20 against the resident Piper, read back
through our own ASR:

    "Không sao đâu. Say with me: Fine, thank you."
        VieNeu  -> 'Không sao đâu, say with me, fine thank you.'
        Piper   -> 'Hong Sao Do, say with me. Fine, thank you.'

Correct diacritics, correct tones, correct English, out of ONE utterance. Piper
loses the tones entirely, and only gets that far with the sentence-splitting
fallback. The children are Vietnamese; the teacher's Vietnamese has to be
Vietnamese.

WHY IT NEEDS A CACHE. VieNeu runs at RTF 1.9-2.5 on this box; Piper at 0.12.
The research gate for live speech is RTF <= 0.6, so VieNeu misses it by 3-4x,
and a child already waits ~19s to be answered.

The way out is that a teacher repeats herself. Measured over one live period,
"Fine, thank you" was in fourteen of fifteen lines. Cache by (engine, voice,
text) and the price is paid once per DISTINCT utterance, not once per
utterance: the first "Fine, thank you." of a term costs three seconds and every
one after it is a file read. Pre-warm the unit's locked language -- about ten
lines -- and most of a lesson is already on disk before it starts.

This is the research's §10A ("pre-render authored curriculum speech") arriving
by a different door, and it covers dynamic speech too, which pre-rendering
cannot.

NOT ADOPTED, still. The acceptance gate is 240 utterances rated by three
bilingual humans per voice: same perceived speaker across a switch, accent
breaks, naturalness. Machines can measure intelligibility and latency and
nothing else. See docs/research/external/README.md.
"""

from __future__ import annotations

import hashlib
import io
import json
import logging
import os
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any

from tts import TtsResult

log = logging.getLogger("speech.tts.vieneu")

ROOT = Path(__file__).resolve().parents[2]
VIENEU_SRC = Path(os.environ.get("VIENEU_SRC", ROOT / "references" / "VieNeu-TTS" / "src"))
# v3turbo.py:122. Writing this as 24000 halves the playback speed and doubles
# the apparent duration -- it is how a model that misses the latency gate can
# look like one that meets it.
SAMPLE_RATE = 48_000
CACHE_DIR = Path(os.environ.get("TTS_CACHE", ROOT / ".runtime" / "tts-cache"))
DEFAULT_PRESET = os.environ.get("VIENEU_VOICE", "Ngọc Linh")


class VieNeuProvider:
    """One resident engine, one preset voice, one cache directory."""

    def __init__(self, preset: str = DEFAULT_PRESET, *, cache_dir: Path | None = None):
        self.preset = preset
        self.cache_dir = Path(cache_dir) if cache_dir else CACHE_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._engine: Any = None
        self._emb: Any = None
        self._codes: Any = None

    @property
    def name(self) -> str:
        return f"vieneu-v3-turbo-int8:{self.preset}"

    @property
    def voices(self) -> tuple[str, ...]:
        # One teacher, one voice. The preset carries its own language coverage;
        # this engine does not need a voice per language, which is the whole
        # reason it is here.
        return (self.preset,)

    def _load(self) -> None:
        if self._engine is not None:
            return
        if str(VIENEU_SRC) not in sys.path:
            sys.path.insert(0, str(VIENEU_SRC))
        import numpy as np

        from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine

        started = time.perf_counter()
        self._engine = OnnxV3LiteEngine(onnx_subfolder="onnx_int8", threads=0)
        presets = json.loads(
            (VIENEU_SRC / "vieneu" / "assets" / "voices_v3_turbo.json").read_text(encoding="utf-8")
        )["presets"]
        if self.preset not in presets:
            raise RuntimeError(
                f"voice {self.preset!r} is not a VieNeu preset; have {sorted(presets)[:5]}…"
            )
        chosen = presets[self.preset]
        self._emb = np.asarray(chosen["speaker_emb"], dtype=np.float32)
        self._codes = np.asarray(chosen["codes"], dtype=np.int64)
        log.info("vieneu ready in %.1fs (voice %s)", time.perf_counter() - started, self.preset)

    def _key(self, text: str, speed: float) -> Path:
        digest = hashlib.sha256(
            f"{self.name}|{speed:.2f}|{' '.join(text.split())}".encode()
        ).hexdigest()[:32]
        return self.cache_dir / f"{digest}.wav"

    def synthesize(self, text: str, *, voice: str | None = None, speed: float = 1.0) -> TtsResult:
        cached = self._key(text, speed)
        if cached.is_file():
            # The point of the whole design: a repeated line costs a file read.
            return TtsResult(audio=cached.read_bytes(), voice=self.preset, synth_s=0.0)

        import numpy as np

        with self._lock:
            self._load()
            started = time.perf_counter()
            wav = self._engine.infer(text=text, speaker_emb=self._emb, ref_codes=self._codes)
            elapsed = time.perf_counter() - started

        samples = np.asarray(wav, dtype=np.float32).reshape(-1)
        if samples.size == 0:
            # A silent WAV is worse than an exception: the room cannot tell it
            # from a teacher who chose not to speak.
            raise RuntimeError(f"vieneu returned no audio for {text[:40]!r}")

        buf = io.BytesIO()
        with wave.open(buf, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(SAMPLE_RATE)
            out.writeframes((np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes())
        audio = buf.getvalue()

        # Write through a temp file: a half-written cache entry read by the next
        # request is a corrupt WAV in a classroom, and it would persist.
        tmp = cached.with_suffix(".part")
        tmp.write_bytes(audio)
        tmp.replace(cached)
        log.info(
            "vieneu %dch -> %dB in %.2fs (%.2fs audio) cached",
            len(text), len(audio), elapsed, samples.size / SAMPLE_RATE,
        )
        return TtsResult(audio=audio, voice=self.preset, synth_s=elapsed)

    def warm(self, lines: list[str], *, speed: float = 1.0) -> dict[str, int]:
        """Render lines into the cache ahead of the lesson.

        Called with the unit's locked language, this is the difference between
        a child waiting three extra seconds on every new sentence and waiting
        for none of them.
        """
        made = hit = 0
        for line in lines:
            if self._key(line, speed).is_file():
                hit += 1
                continue
            self.synthesize(line, speed=speed)
            made += 1
        return {"rendered": made, "already": hit}
