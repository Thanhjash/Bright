# Deep research brief — the brain: fast enough for a classroom, and eventually offline

**Commissioned:** 2026-08-18
**Status:** open
**Why now:** measured, not assumed. The model is 95% of Bright's turn latency.

---

## What Bright is

An autonomous AI English teacher for remote, under-resourced Vietnamese primary
classrooms, intended to be **given away** (target ~40M children). It runs on a
miniPC driving a **projector**; children never touch a keyboard, mouse or screen
— they speak, and the teacher runs the room.

The teacher is an **agent harness**, not a chatbot and not a scripted lesson.
It reads a markdown curriculum library the way a coding agent reads a repo, and
acts only through **nine typed MCP tools**:

```
read_library  search_library  write_board  read_board  show_image
play_clip     show_exercise   record_evidence  say
```

`say` is the **terminal tool**: the turn ends when, and only when, the model
calls it. A turn is bounded at 8 tool iterations.

## The measured problem

On a laptop (Intel, 16 GB), against hosted Xiaomi MiMo v2.5-pro on its
`token-plan` tier, reasoning disabled, `max_tokens: 512`:

| Stage | Time | Share |
|---|---|---|
| Voice-activity endpointing | 0.8 s | fixed by design |
| ASR (faster-whisper `base`, CPU INT8) | 1.7 s | ~3% |
| **Model** | **40–114 s** | **~95%** |
| TTS (Piper, CPU) | 1–2 s | ~3% |

Per model round-trip: **13–20 s**. A turn uses 2–6 round-trips
(`api_calls=3/8` … `6/8`). The gateway also logs
`Stream stale for 180s — no chunks received. Killing connection`, i.e. the
provider stalls entirely and the client retries.

**Target: under 5 s from a child finishing a sentence to the teacher starting to
speak.** That needs roughly **1–1.5 s per round-trip**, ~10× better than today.

## The questions

1. **Hosted, now.** Which OpenAI-compatible endpoints reliably serve a
   tool-calling model at **p95 < 1.5 s per round-trip** for short prompts
   (~2–4k tokens in, <512 out) from **Vietnam / Southeast Asia**? Give measured
   or vendor-published p50/p95 TTFT and tokens/sec, region availability, and
   concurrency limits. Note that our provider caps us at **one concurrent run**,
   which forced a serialised pulse loop — flag any candidate with similar caps.

2. **Tool-calling quality under constraint.** Bright needs a model that
   reliably (a) emits several tool calls in one assistant message rather than
   serialising them, (b) copies an opaque `turn_id`/`student_id` verbatim into
   every call, (c) never invents an id outside a supplied list, and (d) obeys a
   *terminal tool* contract. Rank candidates on tool-calling reliability, not on
   chat benchmarks. Cite tool-use/function-calling evaluations (e.g. BFCL) with
   dates.

3. **Bilingual behaviour, and script discipline.** The teacher code-switches
   Vietnamese↔English within one sentence. **Observed failure to avoid: our
   current Chinese-trained model wrote Chinese onto the projector in a
   Vietnamese classroom.** Which candidates hold a declared output language
   under instruction pressure? Is there evidence of training-language leakage
   for each? We now refuse alien scripts in the server, but a model that needs
   refusing is a model wasting turns.

4. **The offline endgame — this is the real requirement.** Production is an
   **offline appliance**: a low-cost Intel miniPC (assume 16 GB RAM, iGPU or
   NPU, no discrete GPU; state clearly if a small discrete GPU changes the
   answer). Which open-weight models can run **locally** with the tool-calling
   reliability above, bilingual VI/EN, at **< 2 s per round-trip**? Cover
   quantisation (INT4/INT8), runtimes (llama.cpp, OpenVINO/OVMS, vLLM), memory
   footprint alongside a resident ASR and TTS model, and thermal/throttling
   behaviour on a fanless or lightly-cooled box. Give the smallest model you
   would actually trust to run a classroom, and say what it gives up.

5. **Licence and giveaway.** Weights must be redistributable in an appliance
   image donated at scale. Flag anything non-commercial, research-only, or with
   acceptable-use terms that a school deployment could violate.

6. **Cost.** For the hosted bridge period: cost per teaching hour at ~4
   round-trips per turn and ~2–4k prompt tokens, with and without prompt
   caching. Prompt caching matters — our turn prefix is stable and we already
   see `cached_tokens` in responses.

## Constraints that are not negotiable

- **OpenAI-compatible `/v1/responses` or `/v1/chat/completions` with streaming
  and tool calls.** We will not rewrite the harness for a bespoke API.
- **No cloud dependency in the shipped classroom.** A hosted model is a bridge
  to the demo, not the product. Anything that cannot eventually run with the
  WAN unplugged is out.
- **No child audio or raw child text may leave the appliance** in the final
  product. Note any candidate whose terms claim training rights over inputs.
- We will not adopt a model that requires a per-lesson state machine, fine-
  tuning on our curriculum, or any design where code knows which lesson it is.

## Deliverables

1. A ranked table: model × hosting × p50/p95 latency × tool-call reliability ×
   bilingual VI/EN × licence × RAM at quantisation × offline-capable.
2. **One recommendation for right now** (hosted, gets us under 5 s this week)
   and **one for the appliance** (offline, on Intel CPU/iGPU/NPU).
3. The measurement protocol you would use to verify each claim on our own box —
   exact commands, so we can reproduce rather than trust.
4. Anything in the framing above that you believe is wrong. Say so plainly; we
   would rather change the plan than defend it.

## Prior art in this repo

`docs/research/external/Offline bilingual classroom speech IO for Bright.md`
answers the **speech** half of this problem (faster-whisper `small`
multilingual for ASR; VieNeu-TTS v3 Turbo for bilingual TTS). Do not re-litigate
speech. This brief is only about the brain.
