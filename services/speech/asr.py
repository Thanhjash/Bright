"""Provider-neutral ASR seam.

The HTTP service depends on this small synchronous contract, not on Whisper.
Providers may use CPU/GPU libraries internally; request scheduling and
cancellation safety stay in ``app.py``. A future audio-native model must pass
the same conformance tests before it can replace Whisper.
"""

from __future__ import annotations

import io
import math
import time
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable


@dataclass(frozen=True)
class AsrResult:
    text: str
    language: str | None
    language_probability: float | None
    confidence: float
    no_speech_probability: float
    avg_logprob: float | None
    audio_s: float
    decode_ms: int
    infer_ms: int


@runtime_checkable
class AsrProvider(Protocol):
    """Conformance surface for resident local or hosted ASR providers."""

    @property
    def name(self) -> str: ...

    def transcribe(self, audio: bytes, *, language: str | None = None) -> AsrResult: ...


class FasterWhisperProvider:
    def __init__(self, model: Any, model_name: str) -> None:
        self.model = model
        self.model_name = model_name

    @property
    def name(self) -> str:
        return self.model_name

    def transcribe(self, audio: bytes, *, language: str | None = None) -> AsrResult:
        from faster_whisper.audio import decode_audio

        started = time.perf_counter()
        pcm = decode_audio(io.BytesIO(audio))
        decoded = time.perf_counter()
        segments, info = self.model.transcribe(
            pcm,
            language=language,
            beam_size=1,
            vad_filter=True,
            condition_on_previous_text=False,
        )
        rows = list(segments)  # faster-whisper inference is lazy
        finished = time.perf_counter()
        text = "".join(str(s.text) for s in rows).strip()
        spans = [max(0.0, float(s.end) - float(s.start)) for s in rows]
        span = sum(spans)
        avg_logprob = (
            sum(float(s.avg_logprob) * weight for s, weight in zip(rows, spans)) / span
            if span > 0 else None
        )
        no_speech = (
            sum(float(getattr(s, "no_speech_prob", 0.0)) * weight for s, weight in zip(rows, spans)) / span
            if span > 0 else 1.0
        )
        # Token probability is useful but not calibrated correctness. Penalize
        # it with Whisper's no-speech estimate and let Core apply a conservative
        # release threshold.
        confidence = math.exp(avg_logprob) * (1.0 - no_speech) if avg_logprob is not None else 0.0
        return AsrResult(
            text=text,
            language=getattr(info, "language", None),
            language_probability=_optional_probability(getattr(info, "language_probability", None)),
            confidence=_probability(confidence),
            no_speech_probability=_probability(no_speech),
            avg_logprob=round(avg_logprob, 3) if avg_logprob is not None else None,
            audio_s=round(len(pcm) / 16000.0, 2),
            decode_ms=round((decoded - started) * 1000),
            infer_ms=round((finished - decoded) * 1000),
        )


def _probability(value: Any) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    if not math.isfinite(number):
        return 0.0
    return round(max(0.0, min(1.0, number)), 4)


def _optional_probability(value: Any) -> float | None:
    return None if value is None else _probability(value)


__all__ = ["AsrProvider", "AsrResult", "FasterWhisperProvider"]
