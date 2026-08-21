"""Provider-neutral ASR seam.

The HTTP service depends on this small synchronous contract, not on Whisper.
Providers may use CPU/GPU libraries internally; request scheduling and
cancellation safety stay in ``app.py``. A future audio-native model must pass
the same conformance tests before it can replace Whisper.
"""

from __future__ import annotations

import io
import logging
import os
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
    peak: float = 0.0
    rms: float = 0.0


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
        hint: str | None = None,
    ) -> AsrResult: ...


# Silero's gate is too strict for this room, and it fails SILENTLY.
#
# Measured 2026-08-21 from the owner's own microphone, with peak/RMS logged on
# every clip:
#
#     rms 0.2319  ->  no-speech 0.364   transcribed        (shouting, close)
#     rms 0.2432  ->  no-speech 0.321   transcribed
#     rms 0.0471  ->  no-speech 1.000   VAD removed 100%   (ordinary speaking)
#     rms 0.0406  ->  no-speech 1.000   VAD removed 100%
#     rms 0.0255  ->  no-speech 1.000   VAD removed 100%
#
# The microphone was never the problem: those clips carry loud, healthy audio.
# `vad_filter=True` runs Silero at its default 0.5 threshold over the whole
# clip and, when a child speaks at ordinary volume across a room with a fan in
# it, decides there is no speech anywhere and hands Whisper an EMPTY array.
# Whisper then dutifully reports no-speech 1.000 and the room says nothing,
# with no error at any layer -- a child talks and is met with silence.
#
# The teammate's system (references/ClassroomAI_ai-core) hears the same person
# fine, and it runs whisper.cpp with no VAD at all. That is the difference.
#
# So: default OFF. It costs decode time -- silence is no longer stripped before
# the encoder -- and on this box that is a second or two we can afford, which is
# also the owner's own call ("dùng whisper chuẩn chậm cũng được"). Whisper's own
# `no_speech_threshold` still runs, and it judges per segment with the
# log-probability rescue, rather than deleting the audio before the model sees
# it. Set ASR_VAD_FILTER=1 to put it back.
#: Below this peak amplitude a clip is silence, and silence is never worth a
#: decode. Tunable because a different microphone has a different noise floor.
SILENCE_PEAK = float(os.environ.get("ASR_SILENCE_PEAK", "0.10"))
VAD_FILTER = os.environ.get("ASR_VAD_FILTER", "0").strip().lower() in {"1", "true", "yes"}


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
        hint: str | None = None,
    ) -> AsrResult:
        from faster_whisper.audio import decode_audio

        started = time.perf_counter()
        pcm = decode_audio(io.BytesIO(audio))
        decoded = time.perf_counter()
        # How loud was it, actually?
        #
        # "VAD removed 100% of the audio, no-speech 1.000" has two completely
        # different causes and the log could not tell them apart: a microphone
        # that sent silence, or real speech the VAD disliked. One is a broken
        # capture path, the other is a threshold. Peak and RMS separate them in
        # one number each, cost nothing, and would have saved an afternoon.
        try:
            peak = float(abs(pcm).max()) if len(pcm) else 0.0
            rms = float((pcm.astype("float64") ** 2).mean() ** 0.5) if len(pcm) else 0.0
        except Exception:  # noqa: BLE001 -- a diagnostic must never break a lesson
            peak = rms = -1.0

        # SILENCE NEVER REACHES THE MODEL.
        #
        # Whisper has no reason to stop early on silence: with nothing to
        # transcribe it rambles to the end of its 30s window, so the QUIETER the
        # clip the LONGER it takes. Measured live on 2026-08-21, mid-recording:
        #
        #     peak 0.756  real speech   ->  3.9s
        #     peak 0.920  real speech   ->  3.3s
        #     peak 0.072  room noise    -> 17.4s
        #     peak 0.019  near-silence  -> 18.1s
        #     peak 0.019  near-silence  -> 19.7s
        #
        # Eighteen seconds of the room frozen on a clip with nobody in it. The
        # gate opening on noise is a separate (and cheaper) problem; this is the
        # backstop that keeps its mistake from costing a lesson.
        #
        # The threshold has four times' margin: the quietest REAL utterance
        # measured on this microphone peaked at 0.435, the loudest silence at
        # 0.072. It is deliberately a peak and not an RMS -- one word spoken
        # into a quiet room has a low RMS and a high peak, and that word is
        # exactly what a beginner's answer looks like.
        if 0.0 <= peak < SILENCE_PEAK:
            log.info(
                "silence not decoded (peak %.4f rms %.5f, %.2fs) -- nothing sent to the model",
                peak, rms, len(pcm) / 16000.0,
            )
            return AsrResult(
                text="",
                language=language,
                language_probability=None,
                confidence=0.0,
                no_speech_probability=1.0,
                avg_logprob=None,
                audio_s=round(len(pcm) / 16000.0, 2),
                peak=round(peak, 4),
                rms=round(rms, 5),
                decode_ms=round((decoded - started) * 1000),
                infer_ms=0,
            )

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
            vad_filter=VAD_FILTER,
            condition_on_previous_text=False,
            # Names, and nothing else. `condition_on_previous_text` stays False
            # -- this biases the vocabulary for ONE utterance, it does not carry
            # a running transcript forward, which is what makes one hallucinated
            # word poison every word after it.
            initial_prompt=(hint or None),
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
            peak=round(peak, 4),
            rms=round(rms, 5),
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
            _, _, all_probs = detect(pcm, vad_filter=VAD_FILTER)
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
