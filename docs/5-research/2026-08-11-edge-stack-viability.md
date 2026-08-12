# Research Report: Edge Stack Viability for Bright

**Conducted:** 2026-08-11
**Scope:** the five unresolved spikes in [../05-open-questions.md](../4-build/open-questions.md) that external research can answer.
**Method:** 5 WebSearch queries (Gemini disabled — no `.ck.json`). Cross-referenced against Google/Intel/OpenVINO primary sources and arXiv.

---

## Executive Summary

**Three findings change the plan. None of them are fatal, but two invalidate stated assumptions.**

1. **The hardware cost target and the performance target are in conflict.** Gemma 4 E4B INT4 runs at 18.5 tok/s on an Arc 140V iGPU and 12.0 tok/s on NPU — measured on a **Core Ultra 7 258V (Lunar Lake)**, a premium chip. That is not a "cheap Intel box." A budget N-series CPU will land far below. The 16 GB / low-cost SKU assumption in doc 00 needs a real hardware decision before SP-1 can even be defined.

2. **TTS first-token latency alone blows the end-to-end budget.** Piper 1,510 ms FTTS, Kokoro 2,925 ms FTTS. The SP-5 target was < 2.5 s to first sound *total*. Neither model reaches it live. **Mitigation exists and it is architecturally free:** pre-render all authored narration to audio at authoring time. Only free-text LLM output needs live TTS. This falls out of NS-1 + the Authoring Studio already in the plan.

3. **Kokoro does not support Vietnamese.** Piper does (30+ languages). Given NS-1's scaffolding ladder ends in Vietnamese explanation, this constrains the choice — or forces two TTS engines.

Two findings **strengthen** existing decisions: grammar-constrained decoding gives a measured **+0.35 quality gain on classification for Gemma 4 E4B specifically** (and +0.90 on JSON), which directly validates the 4-tool `available_actions` design in doc 03 §3 — and says we should enforce it with a grammar, not just a prompt. And Vietnamese-English code-switched ASR is at **19.06% WER** for adults in the best recent work, confirming SP-7 is a research problem, not a shopping problem.

---

## Research Methodology

- Sources consulted: ~35 across 5 queries
- Date range: 2021 (SpeechOcean762) → July 2026 (ASR model comparisons)
- Search terms: Gemma 4 E4B OpenVINO NPU benchmark · child/Vietnamese code-switching ASR WER · GOP wav2vec2 SpeechOcean762 · offline TTS Piper Kokoro latency · grammar-constrained decoding small models

---

## Key Findings

### 1. Gemma 4 E4B on Intel — the numbers exist, and they hurt

| Device | Throughput |
|---|---|
| NPU (Intel AI Boost, Lunar Lake) | **12.0 tok/s** |
| iGPU (Arc 140V) | **18.5 tok/s** |

Measured on Core Ultra 7 258V, OpenVINO 2026, INT4, `NPUW_LLM_GENERATE_HINT=BEST_PERF`.

Notes from the same source: NPU throughput is **memory-bandwidth bound** — TURBO clock boost is ineffective. Official Gemma 4 support is *functional preview* in OpenVINO 2026.0/2026.1; **GPU support requires nightly builds**. Intel published day-zero optimization for Gemma 4.

**Implications:**

- At 18.5 tok/s, a 60-token teacher utterance costs **3.2 s of generation alone**, before prefill. The pre-registration pattern in [../07-execution-plan.md](../4-build/execution-plan.md) §3 is not an optimization — it is the only way this is usable live.
- Memory-bandwidth bound means **RAM speed matters more than core count**. A cheap box with slow single-channel DDR will underperform badly relative to its price tier.
- "Functional preview" + nightly-only GPU is a real supply-chain risk for an appliance. Pin the OpenVINO version.
- One community project runs E4B on NPU 3720 via stateful→stateless graph surgery — evidence the path is non-trivial on older NPUs.

**Action:** Q1 (hardware SKU) is now blocking, not deferred. Price out Core Ultra vs. N-series and measure both. The kill criterion in SP-1 (< 8 tok/s) is likely to *pass* on Lunar Lake and *fail* on budget silicon — which makes it a cost decision, not a technical one.

### 2. STT — code-switching is the hard part, children make it harder

- **TSPC** (arXiv 2509.05983), a two-stage phoneme-centric architecture using an extended Vietnamese phoneme set as intermediate representation, achieves **19.06% WER** on Vietnamese-English code-switching, explicitly designed for low compute. Best result found; still ~1 error in 5 words. **On adult speech.**
- General 2026 code-switching benchmarks: commercial (Universal-3.5 Pro) 7.69 normalized WER vs. GPT-4o Transcribe 44.58 — a 6× spread. Offline open models sit closer to the bad end.
- **Offline/edge options:** Vosk and **Moonshine** (Useful Sensors) target low-power hardware; smallest Moonshine model is **27 MB**. Whisper and NeMo checkpoints run air-gapped given compute.
- **No model found that is specifically validated on children's L2 English.** This is a genuine gap.

**Implications:** Pika's claim of training ASR on 500+ Vietnamese children's voices is a real moat, and this search confirms why — the data does not exist publicly. Do not plan around achieving good code-switched child-speech WER with an off-the-shelf model.

**Design consequence:** lean hard on *constrained recognition*. Most classroom utterances are answers to known prompts. Score against an expected-answer set rather than running open-vocabulary transcription. Full free-form STT is only needed in roleplay and EXPLORE.

### 3. Pronunciation — the approach in doc 03 §7 is correct and current

- **SpeechOcean762** confirmed: 5,000 utterances, 250 non-native speakers, utterance-level scores (accuracy/fluency/completeness/prosody/total 0–10), word-level (accuracy/stress/total 0–10), **phoneme-level accuracy 0–2**. Open baseline released in **Kaldi**, using classical NN-based GOP — explicitly described by its authors as not using latest techniques.
- Current direction: SSL encoders (**wav2vec2 / HuBERT / WavLM**, chosen for complementary phonetic/prosodic/noise strengths) feeding hierarchical CNN-BiLSTM heads.
- Concrete recent work worth reading: *Enhancing GOP in CTC-Based Mispronunciation Detection with Phonological Knowledge* (arXiv 2506.02080); *A Framework for Phoneme-Level Pronunciation Assessment Using CTC* (Interspeech 2024); *Phonological Level wav2vec2-based MDD* (arXiv 2311.07037).

**Verdict:** no change needed to doc 03 §7. Use the Kaldi baseline as a reference number only; build on wav2vec2-CTC + GOP. The phoneme-level 0–2 granularity maps directly to the descriptive-feedback requirement (`/θ/ needs practice`) — no calibration needed to report at that granularity.

### 4. TTS — the latency finding is the important one

| Model | MOS | Params/Size | FTTS | Peak RAM | Vietnamese |
|---|---|---|---|---|---|
| **Kokoro** | **4.2** (top of TTS Arena v1) | 82 M / 341 MB | 2,925 ms | 1.9 GB | ❌ **No** |
| **Piper** | lower | 100+ voices, 30+ langs | 1,510 ms | 2.6 GB | ✅ Yes |

Piper synthesizes ~2× realtime on a single CPU core (0.54× core-hour ratio). Both are recommended as the default choices when CPU-only deployment simplicity matters.

> ### ⚠️ CORRECTION — 2026-08-11, same day, by direct measurement
>
> **The published FTTS figures are cold-start numbers and are misleading for our use case.** Measured locally with a persistent `PiperVoice`:
>
> | | |
> |---|---|
> | Model load | 1.52 s — **paid once at startup** (this is what the 1,510 ms benchmark is measuring) |
> | 21-char sentence, warm | **100 ms** |
> | 76-char sentence, warm | **323 ms** |
> | Throughput | **0.07× realtime** |
>
> **Live TTS is viable.** The conclusion below ("live TTS cannot meet it") is wrong for a persistent service and is retained only to show what changed. The requirement it produces is simply: *never reload the model per request.*
>
> Pre-rendering authored narration is still worthwhile — better voices at authoring time, less CPU in class — but it is an optimization, not a necessity. Kokoro's numbers were not re-measured; the same cold-start caveat likely applies.

**~~The problem:~~** ~~1.5–2.9 s first-token latency versus a < 2.5 s *total* budget. Live TTS cannot meet it.~~

**The fix, and it is nearly free:**

```
AUTHORED NARRATION          → pre-rendered to audio at authoring time
(the majority of speech)      zero latency, best quality, deterministic
                              stored in the media manifest

FREE-TEXT LLM OUTPUT        → live TTS, latency accepted
(recasts, EXPLORE, roleplay)  masked by the backchannel pattern (07 §3)
```

This sits perfectly on the existing architecture: `lesson_run.json` already carries a media manifest, and the Authoring Studio already renders assets. **Add: narration audio is an authored asset.** It also improves quality — authored lines get the best voice available at HQ, unconstrained by edge CPU.

Also worth noting: Kokoro's 1.9 GB and Piper's 2.6 GB peak RAM are significant against a 16 GB budget already holding a 4.5 GB model. Pre-rendering narration reduces how often TTS is resident at all.

**Recommendation:** Piper for live TTS (Vietnamese support is mandatory for the scaffolding ladder). Use a high-quality model at authoring time for pre-rendered narration — no edge constraint applies there. Do not adopt Kokoro unless English-only is acceptable.

### 5. Constrained decoding — direct validation of doc 03 §3

Measured, and specifically on our model:

- **Gemma 4 E4B: +0.35 quality improvement on classification tasks** with constrained decoding
- **+0.90 on structured JSON generation**
- Constrained retry raised mean pass rate across 13 models from **62.5% → 75.2%**; Qwen3-0.6B reached success comparable to models twice its size
- Stated finding: small models *"often fail to generate a valid selection without formal runtime constraints"* **even when prompted with a valid option set**

That last point is the one that matters. The `available_actions[]` design in doc 03 §3 constrains the model *semantically* via the prompt. This research says that is **not sufficient** — it must also be constrained *mechanically* at decode time.

**Action:** upgrade doc 03 §3. The 4-tool surface stands, but add a hard requirement: `classroom_choose_next` must be emitted under **grammar-constrained decoding** restricted to the current `available_actions[]` ids. Technique is mature (Earley-driven dynamic pruning, GCD without finetuning) and low-overhead.

**New open question:** does OVMS / OpenVINO GenAI expose grammar-constrained or guided decoding? If not, this is an argument for llama.cpp (GBNF grammars, mature) over OVMS as the serving layer — which would partly reverse a doc 01 assumption. **This is now the highest-value thing to check in SP-2.**

---

## Implementation Recommendations

### Changes to make in the docs

| Doc | Change | Priority |
|---|---|---|
| 05 / Q1 | Hardware SKU is **blocking**. Price and benchmark Core Ultra vs. N-series before SP-1 | High |
| 03 §3 | Add grammar-constrained decoding as a hard requirement, not a prompt convention | High |
| 03 §6 / 06 | Narration audio is a **pre-rendered authored asset**; live TTS only for free text | High |
| 05 / SP-2 | Add: verify guided/grammar decoding support in OVMS. If absent, evaluate llama.cpp | High |
| 05 / SP-7 | Reframe: constrained recognition against expected answers, not open-vocabulary STT | Medium |
| 03 §7 | No change — approach validated | — |

### Revised latency budget

```
scripted narration     ~0 ms      pre-rendered  ← majority of speech
backchannel ack       <100 ms     reflex tier
free-text response    ~3-5 s      LLM 3.2s + Piper 1.5s, masked by backchannel
```

The old "< 2.5 s to first sound" target was measuring the wrong thing. **What matters is < 100 ms to *some* response**, which the reflex tier already guarantees, and pre-rendering makes the common case instant.

### Common pitfalls surfaced

- Benchmarking Gemma 4 on a dev laptop with a Core Ultra and concluding the cheap box will work. It will not — memory bandwidth, not TFLOPs, is the binding constraint.
- Assuming prompt-level option constraints are enough for a 4.5B model. Measured evidence says no.
- Choosing Kokoro on MOS alone, then discovering no Vietnamese three months in.
- Planning around off-the-shelf child-speech code-switched ASR. It does not exist.

---

## Resources & References

**Model / runtime**
- [Running Gemma 4 on Intel NPU (Lunar Lake) — OpenVINO 2026](https://zenn.dev/jkudo/articles/ae85d7d099e672?locale=en) — the 12.0/18.5 tok/s numbers
- [Gemma 4 Models optimized for Intel Hardware — Intel Community](https://community.intel.com/t5/Blogs/Tech-Innovation/Artificial-Intelligence-AI/Gemma-4-Models-optimized-for-Intel-Hardware-Enabling-instant/post/1742983)
- [Running Gemma 4 with OpenVINO end-to-end](https://medium.com/openvino-toolkit/running-gemma-4-with-openvino-building-a-multimodal-assistant-end-to-end-37a9ce74f0ca)
- [OpenVINO/gemma-4-E4B-it-int4-ov](https://huggingface.co/OpenVINO/gemma-4-E4B-it-int4-ov) · [OpenVINO release notes](https://docs.openvino.ai/releasenotes)
- [gemma4-npu — NPU 3720 graph surgery](https://github.com/semini080220-ship-it/gemma4-npu)

**ASR**
- [TSPC: Two-Stage Phoneme-Centric VI-EN code-switching ASR (arXiv 2509.05983)](https://arxiv.org/abs/2509.05983) — **read this first**
- [Vietnamese ASR: A Revisit (EACL 2026 Findings)](https://aclanthology.org/2026.findings-eacl.345/)
- [Best Open ASR Models in 2026 — WER/latency/license](https://www.marktechpost.com/2026/07/23/best-open-speech-recognition-asr-models-in-2026-wer-languages-latency-and-license-compared/)
- [Best open-source STT 2026 — Gladia](https://www.gladia.io/blog/best-open-source-speech-to-text-models)

**Pronunciation**
- [speechocean762 (arXiv 2104.01378)](https://ar5iv.labs.arxiv.org/html/2104.01378) · [Interspeech PDF](https://www.isca-archive.org/interspeech_2021/zhang21x_interspeech.pdf)
- [Enhancing GOP in CTC-Based MDD with Phonological Knowledge (arXiv 2506.02080)](https://arxiv.org/pdf/2506.02080)
- [Phoneme-Level Pronunciation Assessment Using CTC (Interspeech 2024)](https://www.isca-archive.org/interspeech_2024/cao24b_interspeech.pdf)
- [Phonological Level wav2vec2-based MDD (arXiv 2311.07037)](https://arxiv.org/pdf/2311.07037)

**TTS**
- [On-device TTS Comparison — Picovoice benchmark 2026](https://picovoice.ai/blog/on-device-tts/) — FTTS and peak-RAM numbers
- [Best Local TTS Models in 2026: 58 models](https://localclaw.io/blog/local-tts-guide-2026)
- [Open-Source TTS 2026: 8 models compared](https://texttolab.com/blog/open-source-text-to-speech)

**Constrained decoding**
- [Improving generation in Small Language Models with Grammar-Constrained Decoding — NVIDIA](https://developer.nvidia.com/blog/improving-bash-generation-in-small-language-models-with-grammar-constrained-decoding/)
- [Flexible and Efficient Grammar-Constrained Decoding (arXiv 2502.05111)](https://arxiv.org/pdf/2502.05111)
- [Earley-Driven Dynamic Pruning for Efficient Structured Decoding (arXiv 2506.01151)](https://arxiv.org/pdf/2506.01151)
- [Grammar-Constrained Decoding without Finetuning (arXiv 2305.13971)](https://arxiv.org/pdf/2305.13971)
- [A Guide to Structured Outputs Using Constrained Decoding](https://www.aidancooper.co.uk/constrained-decoding/)

---

## Next Steps

1. **Decide the hardware SKU.** Blocking. Benchmark Gemma 4 E4B INT4 on both a Core Ultra box and a budget N-series box. The gap between 18.5 tok/s and whatever the cheap box does is the real product decision.
2. **Check guided decoding in OVMS.** Fold into SP-2. If absent → evaluate llama.cpp (GBNF) as the serving layer.
3. **Amend doc 03 §3** — grammar-constrained decoding is mandatory for `classroom_choose_next`.
4. **Amend doc 03 §6 / doc 06** — pre-rendered narration audio as an authored asset.
5. **Read TSPC (2509.05983)** before designing the STT service; its phoneme-centric intermediate representation may be directly reusable.
6. Pick **Piper** for live TTS pending SP-5 measurement. Vietnamese support is non-negotiable.

---

## Unresolved Questions

1. **Does OVMS / OpenVINO GenAI support grammar-constrained or guided decoding?** Not answered by these searches. Highest-value open item.
2. **Actual throughput on budget Intel silicon (N100/N150/N355).** All published Gemma 4 numbers are Core Ultra. The number we need does not exist publicly.
3. **Does OpenVINO's Gemma 4 implementation accept audio input?** Still unconfirmed (SP-1). Release notes say text+image.
4. **Prefill latency at realistic context length.** Only decode tok/s was published. Prefill dominates first-token latency and is what SP-5 actually needs.
5. **Piper voice quality for English teaching pronunciation modeling.** A teacher's voice is a pronunciation target — Piper's MOS may be inadequate for that specific use even if fine for instructions. Untested.
6. **Is there any Vietnamese children's L2 English speech corpus at all?** Searches found none. Assume we must collect it.
7. **Kokoro's exact language list** — sources conflict slightly on which languages are covered. Verify against the model card before any decision.
