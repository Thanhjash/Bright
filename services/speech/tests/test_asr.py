from __future__ import annotations

import sys
from dataclasses import replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pytest

from asr import AsrProvider, AsrResult


BASE = AsrResult(
    text="cat", language="en", language_probability=0.99,
    confidence=0.8, no_speech_probability=0.1, avg_logprob=-0.2,
    audio_s=1.0, decode_ms=2, infer_ms=20,
)


class ConformingFakeProvider:
    name = "conformance-fake"

    def __init__(self, result: AsrResult = BASE) -> None:
        self.result = result

    def transcribe(self, audio: bytes, *, language: str | None = None) -> AsrResult:
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
