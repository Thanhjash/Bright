# Prompt — bilingual classroom TTS + ASR (paste to another AI)

You are researching **offline speech I/O** for Bright: an autonomous AI English
teacher for Vietnamese children, one shared projector, cheap Intel box, no
internet in production.

## Product constraints (do not violate)

- **Two languages in one utterance.** Teacher mixes Vietnamese L1 + English
  target in the same sentence (e.g. “Chào con! Look — this is the market. Chợ
  đó.”). Children answer in Vietnamese, English, or mix.
- **Offline.** Must run on one classroom PC. No cloud TTS/ASR as the primary
  path. Hosted APIs are only a research comparison.
- **Latency.** Teacher line is 1–2 sentences. First audio < 800 ms after the
  agent decides `say`. Child utterance 1–4 s; transcript back to Core < 2 s.
- **Licence.** Must be shippable at zero cost to schools (giveaway). “Free for
  research / non-commercial” is a **fail**. Prefer Apache-2 / MIT / BSD / CC-0
  weights + code. Flag Live2D-style sample-licence traps.
- **Footprint.** Share a 16 GB design-intent box with Gemma later + Chromium +
  Core. Prefer INT8 / ONNX / OpenVINO.
- **Owner.** Bright already has `services/speech` (Piper + faster-whisper) and
  Stage as the only loudspeaker. New models must drop into
  `POST /audio/speech` and `POST /audio/transcriptions`. Do **not** put TTS/ASR
  tools on Hermes.

## What we already have (do not rediscover)

| Piece | Now | Why it is not enough |
|---|---|---|
| Piper `en_US-lessac-medium` | loaded as voice `en` | English only; Vietnamese text through this voice sounds broken |
| Piper `vi_VN-vais1000-medium` | loaded as voice `vi` | Vietnamese only; **not used** — UI hardcodes `voice: en` |
| faster-whisper `small.en` | resident STT | English-only. Child Vietnamese / mix will fail |
| Two Piper voices + a language detector | possible hack | Mid-sentence code-switch still sounds like two people |

We need **one** TTS that can code-switch in one line, and **one** ASR that
hears Vietnamese + English mix from children (noisy room).

## Deliverable

A comparison table, then a **recommendation**, then **exact how to get it**.

### TTS table (at least 5 candidates)

Columns: name · repo URL · weights URL · licence · bilingual / code-switch? ·
ONNX/OpenVINO? · RAM · RTF on CPU · Vietnamese quality · English quality ·
can it speak both in ONE utterance? · drop-in for Piper? · shippable?

Must consider (not only these): Piper multi-speaker, MMS-TTS, VITS /
Coqui XTTS, Kokoro, StyleTTS2, OpenVoice, VietTTS / PhoBERT-adjacent Viet
voices, any Intel OpenVINO speech samples. Reject anything that needs a
GPU always-on.

### ASR table (at least 5 candidates)

Columns: name · repo URL · weights URL · licence · languages · child / noisy
room notes · RAM · latency for 3 s clip · OpenVINO? · drop-in for
faster-whisper?

Must consider: faster-whisper `small` / `medium` **multilingual** (not
`.en`), Whisper OpenVINO, Distil-Whisper, PhoWhisper, wav2vec2 Viet,
NVIDIA NeMo FastConformer (only if offline + licence ok).

### How to get (required for the winner of each)

For the recommended TTS and ASR, write copy-paste commands:

```
# clone
# download weights (huggingface-cli / wget + exact file names)
# convert to ONNX / OpenVINO if needed
# expected directory layout under Bright models/
# one curl that proves en, one that proves vi, one that proves MIXED
```

### Explicitly reject

- ElevenLabs / Google / Azure / OpenAI as the production path
- Models that cannot be redistributed to 40M children
- Hermes-native TTS/STT tools
- AIRI streaming TTS server

**Today’s date: 2026-08-18.** Use current Hugging Face / GitHub pages, not
training-data memory.
