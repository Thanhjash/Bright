from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from asr import AsrProvider, AsrResult, DEFAULT_LANGUAGES, FasterWhisperProvider, parse_languages


BASE = AsrResult(
    text="cat", language="en", language_probability=0.99,
    confidence=0.8, no_speech_probability=0.1, avg_logprob=-0.2,
    audio_s=1.0, decode_ms=2, infer_ms=20,
)


class ConformingFakeProvider:
    name = "conformance-fake"

    def __init__(self, result: AsrResult = BASE) -> None:
        self.result = result

    def transcribe(
        self, audio: bytes, *, language: str | None = None, languages: Sequence[str] = DEFAULT_LANGUAGES
    ) -> AsrResult:
        assert audio
        return replace(self.result, language=language or self.result.language)


@pytest.fixture(params=[ConformingFakeProvider])
def asr_provider(request) -> AsrProvider:
    """Add every future provider class here; no provider-specific assertions."""
    return request.param()


def test_provider_conformance(asr_provider: AsrProvider):
    assert isinstance(asr_provider, AsrProvider)
    result = asr_provider.transcribe(b"audio", language="en")
    assert result.text == result.text.strip()
    assert 0.0 <= result.confidence <= 1.0
    assert 0.0 <= result.no_speech_probability <= 1.0
    assert result.decode_ms >= 0 and result.infer_ms >= 0 and result.audio_s >= 0


def test_silence_conformance():
    provider = ConformingFakeProvider(replace(
        BASE, text="", confidence=0.0, no_speech_probability=1.0, avg_logprob=None
    ))
    result = provider.transcribe(b"silence")
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.no_speech_probability == 1.0


# --- parse_languages -------------------------------------------------------

def test_parse_languages_default_on_empty():
    assert parse_languages(None) == DEFAULT_LANGUAGES
    assert parse_languages("") == DEFAULT_LANGUAGES
    assert parse_languages("   ") == DEFAULT_LANGUAGES


def test_parse_languages_splits_normalizes_dedupes():
    assert parse_languages("en, VI , en") == ("en", "vi")


# --- language clamping (FasterWhisperProvider._clamp_language) -------------
# The defect this guards: Whisper's raw top-1 language-ID is unreliable on
# short classroom utterances — a 1.7s Vietnamese greeting was misidentified as
# Spanish (p=0.57) in real testing against the running service. Clamping must
# pick whichever *allowed* language scored highest instead of trusting the
# global argmax, and must never fail the request outright.

class _FakeWhisperModel:
    """Minimal stand-in for faster_whisper.WhisperModel.detect_language."""

    def __init__(self, all_probs=None, raises: bool = False):
        self._all_probs = all_probs
        self._raises = raises

    def detect_language(self, pcm, vad_filter=True):  # noqa: ARG002
        if self._raises:
            raise RuntimeError("boom")
        top_lang, top_prob = max(self._all_probs, key=lambda item: item[1])
        return top_lang, top_prob, self._all_probs


def test_clamp_language_recovers_correct_allowed_language():
    # Global argmax says Spanish; only en/vi are allowed for this deployment.
    model = _FakeWhisperModel(all_probs=[("es", 0.57), ("vi", 0.30), ("en", 0.05)])
    provider = FasterWhisperProvider(model, "small")
    assert provider._clamp_language(object(), ("en", "vi")) == "vi"


def test_clamp_language_falls_back_when_detect_missing():
    class _NoDetect:
        pass

    provider = FasterWhisperProvider(_NoDetect(), "small")
    assert provider._clamp_language(object(), ("en", "vi")) == "en"


def test_clamp_language_falls_back_when_detect_raises():
    model = _FakeWhisperModel(raises=True)
    provider = FasterWhisperProvider(model, "small")
    assert provider._clamp_language(object(), ("vi", "en")) == "vi"


def test_clamp_language_falls_back_when_no_allowed_candidate():
    # Detector only sees languages outside the allowed set.
    model = _FakeWhisperModel(all_probs=[("es", 0.9), ("fr", 0.1)])
    provider = FasterWhisperProvider(model, "small")
    assert provider._clamp_language(object(), ("en", "vi")) == "en"
