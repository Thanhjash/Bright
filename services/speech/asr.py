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
        # ONE decode pass, deliberately.
        #
        # faster-whisper's default `temperature` is a fallback LADDER --
        # [0.0, 0.2, 0.4, 0.6, 0.8, 1.0] -- and when a pass fails
        # `compression_ratio_threshold=2.4` it re-decodes THE WHOLE WINDOW at
        # the next rung. Repeated text compresses well, so a hallucination loop
        # fails that check every time and burns all six. Measured on this box
        # 2026-08-21, from the live log, using audio remaining after the
        # server's own VAD as the unit:
        #
        #     2.348s of speech ->  1.94s      one pass
        #     3.372s of speech -> 11.44s      1.94 x 6
        #     3.799s of speech ->  7.02s      1.94 x 3.6
        #    16.064s of CLEAN textbook audio ->  2.28s   one pass
        #
        # Sixteen seconds of clean speech decoded faster than three seconds of
        # room noise. The ladder is the whole difference, and it buys nothing
        # here: re-decoding fifteen seconds of an air conditioner at T=1.0 does
        # not produce a right answer, it produces a differently wrong one at
        # six times the price, while a child stands waiting.
        #
        # A scalar temperature alone is not enough -- the ratio is still
        # computed and a fallback logged that cannot happen. Both thresholds go
        # to None so the single pass is explicit.
        #
        # `no_speech_threshold` STAYS: `stt.ts` and `RoomDock` both read the
        # no-speech probability this produces, and it is what keeps her from
        # answering a chair.
        segments, info = self.model.transcribe(
            pcm,
            language=forced_language,
            beam_size=1,
            temperature=0.0,
            compression_ratio_threshold=None,
            # log_prob_threshold STAYS at the library default, and this is not
            # a detail. In `generate_segments` it is the RESCUE inside the
            # silence check (transcribe.py:1215-1226):
            #
            #     should_skip = no_speech_prob > no_speech_threshold
            #     if log_prob_threshold is not None and avg_logprob > log_prob_threshold:
            #         should_skip = False
            #
            # Setting it to None removes the rescue, so every segment scoring
            # above 0.6 no-speech is discarded no matter how confident its
            # tokens were. Measured here on 2026-08-21: a 23s textbook track
            # (no-speech 0.651) went from a full transcript to the empty string.
            # It only ever *triggers* a fallback when there is another rung to
            # fall back to, and with a single temperature there is not.
            log_prob_threshold=-1.0,
            no_speech_threshold=0.6,
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

    # NOTE -- deliberate deviation from the commissioned research.
    #
    # "Offline bilingual classroom speech IO for Bright" says plainly: *do not
    # run a language detector first and then force the entire recording*, because
    # that "converts a multilingual decoder into a one-language policy".
    #
    # We do detect, but we do not overrule the decoder with a free choice: we
    # restrict its own detection to the languages this deployment declares.
    # Measured 2026-08-18 on a 1.7 s Vietnamese clip, unrestricted:
    #   detected es (p=0.57) -> "¡Sin chao, costa un conteí la min!"
    # Restricted to {en, vi} the same clip lands on vi (p=1.0) and transcribes.
    # Whisper emits a language token either way, so this does not remove a
    # freedom the decoder had -- it removes ~100 languages the classroom does
    # not contain.
    #
    # The research's real warning still stands and is NOT solved here: forcing
    # one language per utterance cannot transcribe a sentence that switches
    # mid-way ("con muốn nói hello"). That needs a code-switch model -- the
    # research names NVIDIA Parakeet CTC 0.6B Vietnamese-English as challenger B
    # -- and Bright's own mixed-child corpus to choose between them.
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
