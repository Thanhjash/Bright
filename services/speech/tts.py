"""Provider-neutral TTS seam.

The mirror of ``asr.py``, and it exists for the same reason: the HTTP service
should depend on a small synchronous contract, not on Piper. A candidate engine
must satisfy this contract and pass the same measurements before it can replace
the resident one.

WHAT SITS ABOVE THIS AND MUST KEEP WORKING. ``app.py`` splits a teacher line
into one span per sentence and picks a voice for each, because a line that
code-switches used to get ONE voice for all of it — so the English a child is
asked to copy came out of the Vietnamese voice, and read back through Whisper as
'Kosoco Sado, Sao Yume, Fai, Vakiu'. That logic is deliberately *above* the
provider: it is about which voice, not about how audio is made, and it must
apply to every engine we ever plug in here.

WHAT A CANDIDATE HAS TO PROVE, from the code-switching research (§12), because
"it sounds good in a demo" is not a gate:

  * curriculum-keyword pronunciation   >= 99% majority-rater correct
  * same perceived speaker across a switch  >= 95% of clips
  * obvious accent/timbre/prosody break     <  5% of clips
  * naturalness >= 4.0/5, mixed-vs-monolingual MOS penalty <= 0.3
  * p95 first-audio <= 350 ms, p95 RTF <= 0.6 on the shipping box
  * zero failures across 10,000 generated lines

Only the last two and a coarse proxy for the first are machine-checkable:
synthesize, then read the audio back through our own ASR and compare. The rest
needs bilingual human raters. Nothing may be recorded as *adopted* on machine
evidence alone — see docs/research/external/README.md.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

log = logging.getLogger("speech.tts")


@dataclass(frozen=True)
class TtsResult:
    """One synthesized span.

    ``audio`` is a complete WAV. Spans are joined by the caller, which refuses
    to join mismatched formats rather than emit audio at the wrong pitch — one
    voice in the wrong language is bad, one voice at the wrong pitch sounds
    like broken equipment.
    """

    audio: bytes
    voice: str
    synth_s: float


@runtime_checkable
class TtsProvider(Protocol):
    """Conformance surface for a resident local speech synthesizer."""

    @property
    def name(self) -> str:
        """Engine plus weights, specific enough to appear in a measurement."""
        ...

    @property
    def voices(self) -> tuple[str, ...]:
        """Voice ids this provider can speak, in no particular order.

        NS-7: the ids are whatever the deployment installed. This module must
        never assume a particular language is present, or that any specific
        language exists at all.
        """
        ...

    def synthesize(self, text: str, *, voice: str, speed: float = 1.0) -> TtsResult:
        """Speak one span. Must raise rather than return silence on failure.

        A provider that returns an empty or silent WAV is worse than one that
        raises: the room cannot tell it from a teacher who chose not to speak.
        """
        ...
