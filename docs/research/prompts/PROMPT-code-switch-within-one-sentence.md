# Deep research brief — code-switching inside one sentence, VI↔EN

**Commissioned:** 2026-08-18
**Status:** open
**Follows:** `docs/research/external/Offline bilingual classroom speech IO for Bright.md`

---

## Read the prior work first

The earlier brief settled the *bilingual* question and we are not reopening it:

- **ASR:** faster-whisper `small` multilingual (one decoder covers EN and VI).
  Adopted and running.
- **TTS:** VieNeu-TTS v3 Turbo, ONNX INT8, Apache-2.0. Recommended, **not yet
  adopted**.

This brief is about the narrower thing that survey explicitly left open: a
sentence that switches language **part-way through**.

## Why it matters here

Bright teaches English to Vietnamese primary children. Its own authored
pedagogy (`content/library/how-to-teach.md`) *mandates* code-switching inside a
single utterance:

> "This is a banana. Chuối — banana."

So the teacher is required to say bilingual sentences, and children answer with
sentences like *"Con muốn nói hello"*. Both directions are in scope.

Two failures we have measured or reasoned to:

1. **TTS.** Piper picks one voice per line by counting Latin vs Vietnamese
   letters. A mixed line is therefore mispronounced in one of its two halves —
   she mispronounces her own pedagogy. (`docs/STATE.md` §7.)
2. **ASR.** Whisper emits one language token per utterance. We restrict
   detection to the languages the deployment declares, which fixed a real
   failure (a Vietnamese clip decoded as Spanish).

   > **Correction, 2026-08-19.** An earlier version of this brief said a
   > mid-sentence switch "cannot be transcribed correctly by construction".
   > **That is wrong**, and the answering research said so: the language token
   > *conditions* decoding, it is not a vocabulary gate, and multilingual
   > Whisper can emit English words after Vietnamese ones. The true statement
   > is: *utterance-level conditioning can bias code-switched decoding, and
   > Bright's mixed-speech accuracy is unmeasured.*
   >
   > Measured here on one concatenated clip ("This is a banana. Chuối. This is
   > a banana."): auto and our clamp both gave *"This is a banana. **Joy**,
   > this is a banana."*; forced `en` gave the same text ~1 s faster; forced
   > `vi` lost the English entirely. So the clamp costs a detection pass and
   > buys nothing measurable here, and mixed recognition fails under every
   > policy. Concatenated Piper audio is not a person code-switching, so treat
   > this as indicative, not evidence.

## The questions

1. **ASR that transcribes a mixed VI-EN utterance in one pass.** The prior
   survey named **NVIDIA Parakeet CTC 0.6B Vietnamese-English** as "challenger
   B", noting NVIDIA's own caution that its English coverage is oriented to
   English *occurring inside* Vietnamese rather than arbitrary full English.
   Verify that with evidence. Also evaluate **PhoWhisper** (VinAI, BSD-3), and
   anything newer. For each: word/character error rate on **mixed** utterances
   specifically (not monolingual benchmarks), licence, CPU INT8 latency for a
   1–4 s clip on a low-cost Intel box, and whether it is a drop-in behind an
   existing faster-whisper HTTP service or needs a new runtime adapter.

2. **Children, not adults.** Nearly every Vietnamese ASR benchmark is adult
   read speech. What evidence exists for **child L2 English** and **child
   Vietnamese**, at 8–14 years, in a reverberant classroom with 20–40 children?
   If none exists — say so plainly, and specify the smallest corpus we would
   have to record ourselves to choose between candidates responsibly: how many
   children, how many utterances, what prompts, what annotation scheme.

3. **TTS that pronounces both halves of one sentence.** Confirm or refute the
   VieNeu-TTS v3 Turbo recommendation with independent evidence on
   **intra-sentence** switching: does one speaker embedding hold across a
   language boundary without an accent break? What are first-audio and
   real-time factors on a low-cost Intel CPU, measured rather than claimed by
   the maintainer? Name alternatives with intra-sentence VI-EN support and a
   redistributable licence.

4. **A cheaper architecture we may be missing.** Is there a defensible design
   that avoids the problem instead of solving it — e.g. segmenting a line at
   language boundaries and synthesising each span with a matched voice, then
   concatenating? Say what that costs in naturalness, prosody and latency, and
   whether any production system does it. We would rather ship something boring
   that works than something elegant that does not.

## Constraints

- Must run **offline** on a low-cost Intel miniPC (assume 16 GB, no discrete
  GPU) alongside a resident LLM and a TTS model. State RAM at quantisation.
- Licence must permit **redistribution in a donated appliance image** at a
  scale of millions. Flag non-commercial or research-only terms immediately.
- No cloud speech service may sit in the production dependency graph. Cloud is
  acceptable only as a development-time comparator.
- No raw child audio may leave the device.

## Deliverables

1. A ranked table for ASR and for TTS: candidate × mixed-utterance accuracy ×
   child-speech evidence × CPU latency × RAM × licence × integration cost.
2. A clear verdict on whether **one** model can do mixed VI-EN ASR well enough
   to replace faster-whisper `small`, or whether we should keep it and accept
   one language per utterance for now.
3. The exact acceptance corpus and pass/fail thresholds you would require
   before putting any of this in front of real children.
4. Anything above you think is wrong. We would rather be corrected early.
