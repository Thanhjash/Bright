"""Provider-neutral ASR seam.

The HTTP service depends on this small synchronous contract, not on Whisper.
Providers may use CPU/GPU libraries internally; request scheduling and
cancellation safety stay in ``app.py``. A future audio-native model must pass
the same conformance tests before it can replace Whisper.
"""

from __future__ import annotations

import io
import logging
import math
import time
from dataclasses import dataclass
from typing import Any, Protocol, Sequence, runtime_checkable

log = logging.getLogger("speech.asr")

# The deployment declares which languages it actually runs with (NS-7 — this
# module must never name a language or subject itself). ``app.py`` resolves
# the real set from ASR_LANGUAGES / a per-request form field and passes it in;
# this default only covers callers (tests, ad-hoc scripts) that pass nothing.
DEFAULT_LANGUAGES: tuple[str, ...] = ("en", "vi")


def parse_languages(value: str | None) -> tuple[str, ...]:
    """Turn a comma-separated language list into a clean, ordered tuple.

    Falls back to DEFAULT_LANGUAGES on empty/missing input so a caller can
    never end up with an empty allowed set.
    """
    if not value:
        return DEFAULT_LANGUAGES
    codes = tuple(dict.fromkeys(c.strip().lower() for c in value.split(",") if c.strip()))
    return codes or DEFAULT_LANGUAGES


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

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        languages: Sequence[str] = DEFAULT_LANGUAGES,
    ) -> AsrResult: ...


class FasterWhisperProvider:
    def __init__(self, model: Any, model_name: str) -> None:
        self.model = model
        self.model_name = model_name

    @property
    def name(self) -> str:
        return self.model_name

    def transcribe(
        self,
        audio: bytes,
        *,
        language: str | None = None,
        languages: Sequence[str] = DEFAULT_LANGUAGES,
    ) -> AsrResult:
        from faster_whisper.audio import decode_audio

        started = time.perf_counter()
        pcm = decode_audio(io.BytesIO(audio))
        decoded = time.perf_counter()
        # Caller-forced language: honour it unchanged, no detection pass.
        # Otherwise detect once and CLAMP to the allowed set — Whisper's raw
        # top-1 language ID is unreliable on short classroom utterances (a 1.7s
        # Vietnamese greeting was misidentified as Spanish, p=0.57, in testing
        # on 2026-08-18). Clamping picks whichever allowed language actually
        # scored highest instead of trusting the global argmax.
        forced_language = language if language else self._clamp_language(pcm, languages)
        segments, info = self.model.transcribe(
            pcm,
            language=forced_language,
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

    def _clamp_language(self, pcm: Any, languages: Sequence[str]) -> str:
        """Detect once, then pick whichever *allowed* language scored highest.

        Never returns a language outside ``languages``. Falls back to the
        first allowed language if detection is unavailable, errors, or comes
        back with nothing usable — a degraded transcript beats a 500 in a
        classroom.
        """
        allowed = tuple(languages) or DEFAULT_LANGUAGES
        fallback = allowed[0]
        detect = getattr(self.model, "detect_language", None)
        if detect is None:
            return fallback
        try:
            _, _, all_probs = detect(pcm, vad_filter=True)
        except Exception as exc:  # noqa: BLE001 — detection is a hint, not a hard dependency
            log.warning("language detection failed (%s); falling back to %r", exc, fallback)
            return fallback
        if not all_probs:
            return fallback
        allowed_set = set(allowed)
        candidates = [(lang, prob) for lang, prob in all_probs if lang in allowed_set]
        if not candidates:
            return fallback
        candidates.sort(key=lambda item: item[1], reverse=True)
        return candidates[0][0]


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


__all__ = ["AsrProvider", "AsrResult", "DEFAULT_LANGUAGES", "FasterWhisperProvider", "parse_languages"]
