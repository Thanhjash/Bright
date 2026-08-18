# 05 — OPEN QUESTIONS & SPIKES

**Date:** 2026-08-11
**Rule:** nothing in `../design/architecture.md` gets implemented past a prototype until the spike that de-risks it has run. Each spike is timeboxed and has a written kill criterion.

---

## Priority ordering

> **Re-tiered 2026-08-11** after the adversarial review in [execution plan](execution-plan.md).
> The original Tier-0 (SP-1, SP-2) was plumbing. The real existential risks are content
> economics and teacher control. If SP-1/SP-2 fail we lose a week and swap the serving
> layer. If SP-0 or SP-10 fail, we lose the project.

```
TIER 0 — existential
  SP-0   Lesson-authoring economics: how many hours to author ONE complete lesson?
  SP-10  Teacher control: can a real teacher recover from an agent failure alone?
  SP-4   16 GB co-residency: does everything fit and stay responsive?

TIER 1 — reshapes the architecture
  SP-3  E4B tool-routing eval: can a 42.2-Tau2 model drive the 4-tool surface?
  SP-5  End-to-end latency: student stops talking → AIRI starts talking
  SP-6  AIRI vendoring: can renderer packages be extracted in under two weeks?

TIER 2 — plumbing; run opportunistically in the background from week one
  SP-1  Gemma 4 E4B on OpenVINO: does it run on the target box? Audio input?
  SP-2  Hermes → OVMS: does provider:custom + base_url work, with tool calls?

TIER 3 — product quality, not existential
  SP-7  Child-speech STT quality (English + Vietnamese + code switching)
  SP-8  Pronunciation scoring baseline on SpeechOcean762
  SP-9  Student identity fusion accuracy
```

---

## TIER 0

### SP-0 — Lesson-authoring economics ★ run this first

**Question:** how many hours does it take to author **one complete 20-minute lesson** — narration, all activities, answer keys, distractors, recovery branches for every step, media manifest — such that it plays end to end with **no LLM**?

**Why it's now #1:** NS-1 requires `lesson_run.json` to be complete. If that costs 20–40 expert hours per lesson, the project dies of content starvation regardless of how good the agent is. No other spike measured this.

**Key insight to exploit:** internet exists at *authoring* time; it only disappears at *teaching* time. Use a frontier model at HQ to expand a short `lesson.md` into a full run, with a human teacher reviewing rather than writing.

**Do:**
1. Pick one A1 lesson (`At the Market` is the running example)
2. Author it fully, with frontier-model assistance
3. Log wall-clock hours, split human vs. model
4. Play it through a stub runner; count every place it would stall in a real class
5. Write `tools/lesson-lint/` rules from what you learn — chiefly: **every branch point must have a `default`**

**Kill criterion:** > 8 human-hours per 20-minute lesson after tooling → the content model is wrong. Reduce branch coverage, or shift to a template/parameter system where one authored template yields many lessons.

---

### SP-10 — Teacher control under failure

**Question:** can a teacher who has never seen the system recover from an agent failure, alone, in under 10 seconds?

**Why it's Tier 0:** an agent doing something odd that the teacher cannot stop is how a pilot dies. Ranked risk #2 in [execution plan](execution-plan.md).

**Do:** put the facilitator console in front of a real teacher. Run a scripted lesson and inject three failures:
1. the agent calls on the wrong student
2. the agent jumps to the wrong activity
3. the agent stalls mid-sentence for 15 seconds

**Kill criterion:** they freeze, or ask for help → redesign the console before writing more agent logic.

---

### SP-1 — Gemma 4 E4B on OpenVINO, on the real box

**Question:** does `OpenVINO/gemma-4-E4B-it-int4-ov` run on the target hardware, at what tokens/s, and **does it accept audio input?**

**Why it's Tier 0:** the whole reasoning layer sits on this. And OpenVINO release notes say the Gemma 4 implementation supports **text and image**; audio is unconfirmed. If audio is unsupported, GPT's "Gemma verifies ambiguous utterances" idea is dead and the design must not lean on it.

**Do:**
1. Pull `OpenVINO/gemma-4-E4B-it-int4-ov`, serve via OVMS
2. Measure: model load time, RSS at idle, prefill/decode tokens/s at 2K and 32K context
3. Test image input; test audio input explicitly
4. Repeat on the actual cheap-box CPU, not a dev laptop

**Kill criterion:** decode < 8 tok/s at 4K context on the target box → the pedagogy tier is unusable in real time; either upgrade the hardware target or move to E2B and accept a much narrower tool surface.

**Note:** target hardware SKU is still undefined. OpenVINO Gemma 4 support is documented for Core Ultra and 14th-gen+ desktop CPUs. A cheap N-series box may be well below that. **Decide the SKU before running this spike.**

---

### SP-2 — Hermes → OVMS

**Question:** does `provider: custom` + `base_url: http://127.0.0.1:<ovms>/v3` work, including **tool calling**?

**Why it's Tier 0:** grepping `openvino` across hermes-agent returns **zero hits**. Nobody has done this. Tool calling is the specific risk — the tool-call format must survive Hermes → OVMS → Gemma → back.

**Do:**
1. Configure `model: { provider: custom, base_url: ..., default: gemma-4-E4B }`
2. Plain chat first; then a trivial MCP tool; then a 3-tool sequence
3. Verify tool calls surface correctly on `/v1/responses` SSE as `function_call` / `function_call_output`
4. Raise `HERMES_API_TIMEOUT` and note the value needed

**Kill criterion:** tool calls do not round-trip → either write a shim provider plugin, or switch the serving layer (llama.cpp / vLLM, both already documented in Hermes).

---

### SP-4 — Resource co-residency

> **Re-scoped 2026-08-11.** The demo runs on a laptop, so this is no longer a
> pass/fail gate on 16 GB. It is now a **measurement** exercise: find out what
> the finished system actually consumes, and let that number choose the
> production SKU. Runs at M7, not week one.

**Question:** with everything running at once, does the box stay responsive?

**Concurrent load:** Gemma E4B INT4 (~4.5 GB model weights + KV cache) + STT + TTS + Chromium with WebGL/Live2D + camera capture + face embedding + hand tracking + Classroom Core + Hermes.

**Do:**
1. Bring all services up, run a scripted 45-minute lesson
2. Log RSS per process, total, swap usage, CPU steal, thermal throttling
3. Watch for KV-cache growth over a long session — this is the sneaky one
4. Measure whether reflex-tier latency stays under 100 ms while the LLM is generating

**Kill criterion:** swap is touched, or reflex latency exceeds 100 ms under load → 16 GB is not the production target; escalate to 32 GB and re-cost the hardware.

**Note:** Google's E4B numbers (Q4_0 = 4.5 GB) are *model* memory. System RAM must also cover OS, page cache, the browser, and every service above.

---

## TIER 1

### SP-3 — E4B tool-routing eval

**Question:** at Tau2 42.2, can E4B reliably drive our tool surface? And is a flat 15-tool surface better or worse than one `board` tool with an action enum?

**Why it matters:** this determines the entire shape of `classroom-mcp` — and `classroom-mcp` is a permanent asset (NS-4). Getting it wrong is expensive.

**Do:** build `agent/evals/` with ~300 scenarios across five classes:

```
tool_routing/   given class state + objective → is the tool choice right?
pedagogy/       scaffolding ladder respected? recasts correct?
bilingual/      EN/VI quality, code switching, does it fall back to VI too early?
recovery/       a tool fails / returns unexpected → does it repair or spiral?
lesson_policy/  does it stay within lesson_run, or wander off?
```

Metrics per class:

```
tool selection accuracy       policy violation rate
argument/schema validity      lesson-state consistency
hallucinated tool rate        repair-after-failure rate
response latency              tokens/s
```

Run twice: flat tool surface vs. action-enum surface. Same scenarios.

**Kill criterion:** tool selection accuracy < 85% on `tool_routing` after prompt/skill tuning → the tool surface must shrink, or the reflex tier must absorb more decisions, or we need a bigger model (12B at Tau2 69.0 — but that breaks the 16 GB target).

**This is the eval suite that also answers "is Hermes still good in six months" (NS-4).** Build it early; it pays for itself.

---

### SP-5 — End-to-end latency

**Question:** student stops speaking → AIRI starts speaking. How long?

**Budget to validate:**

```
VAD end-of-speech detection      ~200 ms
STT                              ?
Core → Hermes dispatch           ~20 ms
Hermes agent loop + Gemma        ?  ← dominant term
first text delta → TTS first chunk ?  ← REST-segmenter penalty here
audio decode + playback start    ~50 ms
─────────────────────────────────────
TARGET                           < 2.5 s to first sound
```

**Do:** instrument every hop with the event bus timestamps. Compare REST-segmenter TTS against AIRI's `streaming-pipeline.ts` to quantify what we gave up by not running AIRI server-runtime (see [fact check](../decisions/fact-check-gpt-brief.md) #7).

**Kill criterion:** > 4 s consistently → either revisit the streaming TTS decision, or make DEGRADED mode the default and let the LLM run further ahead of the class.

---

### SP-6 — AIRI vendoring feasibility

**Question:** can we extract the renderer packages and get a talking avatar in our own Vue app inside one week?

**Do:**
1. Submodule `airi` into `vendor/airi`
2. Build a minimal Vue app that renders one Live2D model
3. Wire `model-driver-lipsync` to an `AudioBuffer` from our TTS
4. Patch the two cross-package leaks (`stage-ui-three/.../lip-sync.ts:11`, `stage-ui-mmd/.../lip-sync.ts:15`) by injecting `AudioContext`
5. Adapt `expression-tools.ts` (currently dead code) into an event → animation mapper
6. Map Hermes SSE events → animations per [Hermes decision](../decisions/hermes-over-openclaw.md)

**Kill criterion:** more than two weeks, or the `Stage.vue` rewrite balloons → fall back to a simpler avatar (static sprite + mouth frames). NS-3 means the board carries the pedagogy; the avatar is presence, not payload.

---

## TIER 2

### SP-7 — Child-speech STT

Benchmark local STT on: children's English, Vietnamese, and EN↔VI code switching. Measure WER and latency. Pika claims their ASR was trained on 500+ Vietnamese children's voices — that is the bar, and it is also a signal that **child speech data is the real moat**, not the hardware.

Open sub-question: is there a usable open child-speech corpus for Vietnamese learners of English? Probably not — plan for collecting one.

### SP-8 — Pronunciation baseline

Prototype: G2P → forced alignment (wav2vec-style acoustic model) → phoneme posteriors → GOP/CTC scoring. Evaluate against SpeechOcean762's expert annotations (sentence/word/phoneme level, ~50% child speakers).

Do **not** try to reverse-engineer ELSA. Establish a measurable baseline first, and only emit descriptive feedback until the scores are calibrated ([architecture](../design/architecture.md) §7).

### SP-9 — Identity fusion

Build the fusion spec from [architecture](../design/architecture.md) §5 and measure accuracy in a realistic noisy room. Component questions:
- ECAPA-TDNN (SpeechBrain) speaker embeddings under classroom noise — how bad?
- Streaming diarization: `pyannote.audio` does **not** support streaming; `diart` is the upstream suggestion. Test both.
- 4-mic DOA + face position association — does it actually disambiguate?

**Set the confidence threshold empirically.** Misattributing an answer to the wrong child is worse than admitting uncertainty.

---

## Unresolved product/policy questions

These need a human decision, not a spike:

| # | Question |
|---|---|
| Q1 | ~~**Target hardware SKU.** Blocks SP-1 and SP-4.~~ **DEFERRED 2026-08-11.** Demo runs on a laptop. Pick the SKU after SP-4 measures real consumption — not before. Blocks nothing now |
| Q2 | **Privacy policy for children's biometrics.** Face embeddings of minors. What is stored, where, for how long, and who consents? Needed before any pilot. |
| Q3 | **Curriculum source.** Author our own, or align to an existing framework (Cambridge / national curriculum)? Determines the shape of `content/curriculum/`. |
| Q4 | **Facilitator authority.** Can the teacher override the agent mid-lesson? What does the console expose? |
| Q5 | **Content update path** with no internet. USB? Periodic sync visits? This shapes the content store design. |
| Q6 | **Language of the interface** for the facilitator console — Vietnamese, presumably. Confirm. |

---

## Prototyping order

Superseded by the milestone sequence in [execution plan](execution-plan.md) §5. In short:

```
Week 1     SP-0            ← answer this before building anything
Week 1-6   M1 → M5         ← schemas, core, UI, speech, avatar. NO LLM.
                             ★ minimum demo reached at M5 ★
background SP-1, SP-2      ← cheap, independent, never blocking
Week 4-6   SP-4, SP-6, SP-5
Week 6-9   SP-3 + M8       ← the eval suite and the agent, together
Week 9     SP-10           ← before any pilot
Later      SP-7, SP-8, SP-9
```

**Build `classroom-core` before, not alongside, the model work.** It is LLM-independent by design (NS-1), so nothing about the model blocks it. A `lesson_run.json` player with an authored lesson and no agent at all is the demoable milestone — see [execution plan](execution-plan.md) §5.
