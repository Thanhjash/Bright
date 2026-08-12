# 03 — ARCHITECTURE

> **Current implementation authority:** [Option B classroom runtime](../2-decisions/option-b-classroom-runtime.md).
> This design chapter contains earlier exploration. In particular, stock Hermes MCP
> discovery uses static schemas, so dynamic decoder enums and a guaranteed single
> repair attempt are not current guarantees. Core validation, deadlines, and turn
> fencing are the live safety boundary. Streamed assistant text—not
> `classroom_say`—is the live adaptive voice source. The diagrams and lifecycle
> below show the target system: local Gemma, Hermes cron/planning/memory, perception,
> and pre-class compilation are not claims about the live classroom profile. That
> profile explicitly disables Hermes memory, cron, delegation, terminal, filesystem,
> browser, web, and TTS tools. Control PTT now uses an authorized exact-turn
> barge-in handshake: Core validates the activity epoch, cancels that speech turn,
> and the mic waits for Stage termination plus the echo tail. See the
> [implementation status](../4-build/option-b-implementation-status.md) for evidence.

**Date:** 2026-08-11
**Governed by:** [north star](../1-vision/north-star.md), especially NS-1 (runs without an LLM) and NS-2 (two control tiers).

---

## 1. System diagram

```
                       STUDENTS
                voice · face · gesture
                          │
        ┌─────────────────┴─────────────────┐
        ▼                                   ▼
  perception-service                  speech-service
  MediaPipe hand · face detect        VAD · STT
  face embedding · tracking           (pronunciation is separate)
        │                                   │
        └─────────────────┬─────────────────┘
                          ▼
        ╔═══════════════════════════════════════╗
        ║          CLASSROOM CORE               ║
        ║                                       ║
        ║   event bus  ·  lesson state machine  ║
        ║   student state  ·  board state       ║
        ║                                       ║
        ║   ◄── SOURCE OF TRUTH ──►             ║
        ║   ◄── runs WITHOUT an LLM ──►         ║
        ╚═══════════════════════════════════════╝
             │                    ▲         │
             │ MCP tool call      │ events  │ scene
             ▼                    │         ▼
      ┌──────────────┐            │   ┌──────────────┐
      │ classroom-mcp│            │   │Learning Stage│
      └──────┬───────┘            │   │  (Chromium)  │
             │                    │   │              │
             ▼                    │   │ board + AIRI │
      ┌──────────────┐            │   └──────┬───────┘
      │ HERMES AGENT │────────────┘          │
      │ memory·skill │                       ▼
      │ cron·planning│                   PROJECTOR
      └──────┬───────┘
             │ provider: custom, base_url
             ▼
      ┌──────────────┐
      │ OVMS         │
      │ Gemma 4 E4B  │
      │ INT4 ~4.5GB  │
      └──────────────┘
```

**Key point:** Classroom Core sits at the center, not Hermes. Hermes is a *client* of Core, the same way Learning Stage is a client. Core survives Hermes dying.

---

## 2. Two control tiers (NS-2 made concrete)

### Reflex tier — inside Classroom Core, no LLM

These paths must respond in < 100 ms and must **never** touch Hermes:

| Event | Handling |
|---|---|
| `student.gesture.point` | map coordinates → card id → highlight immediately |
| `student.gesture.drag` | update drop zone, visual feedback |
| `board.choice.selected` | grade against the answer key in `lesson_run.json`, play sound |
| activity timer expiry | advance to the next step in `lesson_run` |
| `student.speech.started` | AIRI stops speaking, plays "listening" animation |

After handling, Core **emits an event upward** so Hermes learns about it — but never waits for Hermes.

### Pedagogy tier — Hermes + Gemma, latency in seconds

| Decision | Owner |
|---|---|
| What the next activity is | Hermes |
| What scaffolding level this student needs | Hermes |
| Recasting a student's wrong sentence | Hermes |
| Who to call on | Hermes (Core proposes candidates) |
| Updating skill estimates | Hermes writes via tool, Core persists |
| Whether to open EXPLORE | Hermes |

### Three operating modes (NS-1 made concrete)

```
FULL       Hermes responds < 3s     → agent fully drives the class
DEGRADED   Hermes slow / timing out → Core plays lesson_run sequentially;
                                       Hermes only intervenes at checkpoints
OFFLINE    Hermes dead              → Core plays lesson_run to completion,
                                       logs everything for post-class processing
```

Core switches modes based on measured latency. The teacher **never** needs to know which mode is active.

---

## 3. `classroom-mcp` — the tool contract

This is our most important asset (NS-4). Principle: **semantic, never DOM**.

### The sizing problem

The first draft of this section listed 26 distinct operations. At Tau2 **42.2**, E4B will not route 26 tools reliably. Counting "board.*" as one group hid the real number — a mistake worth naming, because the tool surface is the thing we cannot cheaply change later.

**Design rule:** the agent should *propose within a constrained option set*, not *compose from a large primitive vocabulary*. Rendering primitives belong to Core, not to the model.

### Primary surface — semantic tools

```
classroom_get_state()
    → { lesson, stage, position, current_student, board_summary,
        state_version, available_actions[] }

classroom_choose_next(state_version, action_id, params?)
    → picks from available_actions[] returned by get_state.
      Rejected if state_version is stale.

classroom_record_observation(student_id, skill, result, evidence)
    → the only write into student state
```

The live Hermes profile does not expose `classroom_say`. Hermes assistant text is
streamed through the Bright adapter and becomes the single adaptive voice. Core's
authored narration uses the same correlated speech protocol for deterministic
fallback. This prevents tool speech and final assistant text from being spoken twice.

The crucial move is `available_actions[]`. Core computes what is *legal right now* from `lesson_run.json` + current state, and hands the model a short enumerated list:

```json
"available_actions": [
  { "id": "next_activity",     "label": "advance to sentence_builder" },
  { "id": "repeat_activity",   "label": "repeat vocabulary_grid" },
  { "id": "scaffold_down",     "label": "drop to image support" },
  { "id": "call_student",      "label": "call on a student", "params": ["student_id"] },
  { "id": "open_explore",      "label": "open EXPLORE on 'penguin'" },
  { "id": "start_roleplay",    "label": "start market roleplay" }
]
```

This converts an open-ended tool-routing problem (where 42.2 is scary) into a **constrained multiple choice** (where a 4.5B model is much stronger). It also makes every agent decision auditable and replayable in evals.

`state_version` gating means a stale decision — the model deciding based on state from 4 seconds ago — is rejected rather than applied to a board that has moved on.

#### Semantic constraint is not enough — constrain the decoder too

`available_actions[]` constrains the model *through the prompt*. Research says that is insufficient: small models **"often fail to generate a valid selection without formal runtime constraints"** even when handed a valid option set.

Measured, on our exact model ([research report](../5-research/2026-08-11-edge-stack-viability.md) §5):

```
Gemma 4 E4B, classification tasks, constrained decoding:   +0.35 quality
Structured JSON generation, constrained decoding:          +0.90 quality
Constrained retry, mean pass rate across 13 models:  62.5% → 75.2%
```

**Future optimization, not a current guarantee:** a provider may emit
`classroom_choose_next` under grammar-constrained decoding generated from the current
`available_actions[]`. Stock Hermes discovers static MCP schemas, so the Option B
baseline cannot mutate this enum per request. Core therefore validates both
`state_version` and `action_id`, rejects stale/illegal calls, and records the failure.
Provider conformance tests determine whether a future local serving stack can add
decoder constraints without changing the contract.

This has a serving-layer consequence: whether OVMS/OpenVINO GenAI exposes guided decoding is unverified. If it does not, llama.cpp (mature GBNF grammar support) becomes the stronger serving choice. Folded into SP-2 — it is now the highest-value thing that spike checks.

### Secondary surface — read-only, added only if evals justify it

```
student_get_profile(student_id)
knowledge_search(query)
```

Everything else from the original 26 becomes an **`available_actions` entry**, not a tool. `board.show_vocabulary`, `board.ask_choice`, `board.sentence_builder`, `board.highlight`, `board.clear` are internal Core functions driven by `lesson_run.json` — the model never names them.

### Fallback ladder if routing accuracy is still poor (SP-3)

```
Tier A  4 tools + available_actions      ← start here
Tier B  drop to 2: get_state + choose_next; narration becomes templated
Tier C  no tool calling at all — constrained JSON decode from a
        single completion, parsed by Core. Model becomes a chooser.
Tier D  Core runs lesson_run linearly; model only writes
        observations after class (the DEGRADED mode from §2)
```

Tier D is already required by NS-1, so the fallback path is not extra work — it is the floor we are building anyway.

### Three hard rules for the tool layer

1. **No tool accepts HTML, CSS, JS, or a selector.**
2. **All assets are referenced as `asset://id`**, resolved by Core. The agent never sees a filesystem path.
3. **Every mutating call carries `state_version`.** Small models repeat and lag; the contract must be able to say no.

### One thing Hermes does that we must disable

`hermes-agent/agent/conversation_loop.py` implements a multi-attempt tool-repair loop. In a chat assistant that is a feature; in a live classroom it means a 3× latency spike while 30 children wait.

Configure provider retries as low as stock Hermes allows, but do not claim exact
single-attempt behaviour: Hermes also has internal tool-name/JSON repair paths. Core's
wall-clock deadline is authoritative. On expiry it logically cancels the turn,
rejects late effects, falls back to the authored action, and logs the outcome.

---

## 4. Event bus

Every component communicates through events; nothing calls anything else directly.

```json
{
  "type": "student.speech.final",
  "ts": 1754870400123,
  "seq": 4471,
  "state_version": 88,
  "student_id": "s17",
  "confidence": 0.71,
  "payload": { "text": "I want water" }
}
```

`seq` + `state_version` are borrowed from the OpenClaw Gateway protocol — Learning Stage needs them to reconnect without state drift.

### Event catalog

```
student.face.detected        student.gesture.point
student.active.changed       student.gesture.drag
student.speech.started       board.choice.selected
student.speech.final         board.activity.completed
pronunciation.completed      lesson.stage.changed
teacher.speech.started       agent.tool.started
teacher.speech.finished      agent.tool.completed
facilitator.override         system.mode.changed   (FULL/DEGRADED/OFFLINE)
```

---

## 5. Student identity — fusion, not a single signal

Voiceprint alone is not reliable in a noisy 30-student room. Fuse:

```
Face ID (embedding)          ─┐
Face track (continuity)      ─┤
Mouth activity               ─┼──►  posterior P(student_id)
Seat position                ─┤     + confidence threshold
Sound direction (4-mic DOA)  ─┤
Speaker embedding (ECAPA)    ─┤
Currently selected turn      ─┘
```

When the posterior falls below threshold → **do not guess**. Emit `student_id: null, confidence: 0.4` and let Hermes handle it (or ask "Is that Minh?").

**Privacy:** no raw video/audio stored by default. Only embeddings and events. A written policy is required before any real deployment with children.

---

## 6. Speech stack

```
MIC (4-mic array)
   ↓ DOA + beamforming
  VAD
   ↓
  STT (dedicated model, NOT Gemma)
   ↓
student.speech.final → Classroom Core → Hermes
   ↓
Hermes returns text
   ↓
TTS service (REST, /audio/speech)
   ↓ audio chunks
Learning Stage → AudioBuffer → AIRI lipsync + speakers
```

**Decision:** use AIRI's **REST + client-side segmenter** path (`tts-session.ts`, transport `rest`), **not** `streaming-pipeline.ts` — the latter requires a separate AIRI server-runtime (see [fact check](../2-decisions/fact-check-gpt-brief.md) #7).

### TTS latency — measured, and better than published

Published benchmarks report **Piper 1,510 ms first-audio** ([research report](../5-research/2026-08-11-edge-stack-viability.md) §4). **That number is cold-start.** Measured on this project's own hardware, 2026-08-11:

| | |
|---|---|
| Model load | **1.52 s — paid once**, at service startup |
| `"Which animal can fly?"` (21 chars) | **100 ms** |
| 76-char sentence | **323 ms** |
| Throughput | **0.07× realtime** (14× faster than speech) |

Vietnamese (`vi_VN-vais1000-medium`) performs the same. **Live TTS is not a bottleneck** as long as the service is persistent and never reloads the model.

Pre-rendering authored narration remains worth doing — better voice quality at authoring time, zero CPU during class — but it is now an **optimization, not a requirement**:

```
AUTHORED NARRATION           → pre-rendered to audio at authoring time
(the majority of class speech)  ~0 ms latency · best available voice
                                · deterministic · one less resident model

FREE-TEXT LLM OUTPUT         → live TTS, latency accepted and masked by
(recasts, EXPLORE, roleplay)    the backchannel pattern (07 §3)
```

**Narration audio is an authored asset**, produced by the Authoring Studio with an unconstrained high-quality voice at HQ. Edge CPU limits apply only to the free-text minority.

**Engine choice: Piper.** Kokoro scores higher (MOS 4.2) but **does not support Vietnamese** — disqualifying, since the scaffolding ladder (NS-1) ends in Vietnamese explanation. Confirm Piper's English voice is good enough to serve as a *pronunciation model* for students, not merely intelligible — that is a stricter bar and is untested (SP-5).

**Where Gemma audio fits:** *possibly* for ambiguous-utterance verification and post-class analysis — **only if SP-1 confirms OpenVINO supports audio input**. Do not design any dependency on it.

---

## 7. Pronunciation Engine — a separate service

Do not use Whisper WER for pronunciation scoring. The target text is known in advance, so use forced alignment:

```
target text ──► G2P ──► expected phonemes
                              │
audio ──► acoustic encoder ──► forced alignment
                              │
                        phoneme posteriors
                              │
                     GOP / CTC scoring
                              │
              ┌───────┬───────┬────────┬─────────┐
            phone   word  completeness fluency prosody
```

**Initial output must be descriptive, not numeric:**

```
✅  /θ/ needs practice — try "three" again
❌  83.716253%
```

Emit numbers only after calibration on real data. Evaluate first on SpeechOcean762 (~50% of its speakers are children), then consider a Vietnamese-children dataset — that is the long-term moat.

---

## 8. Content & data

### `lesson.md` (source) ≠ `lesson_run.json` (the run)

```
content/lessons/market/en-a1-market-01.md   ← curriculum, hand-authored, stable
                     ↓  Hermes cron, before class
data/runs/7A/2026-08-12-market-01.json      ← compiled, media preloaded
```

`lesson.md` — Markdown + YAML frontmatter:

```yaml
---
id: en-a1-market-01
title: At the Market
level: A1
objectives: [recognize food vocabulary, make polite requests]
target_phrases: ["I would like...", "How much is this?"]
vocabulary: [apple, banana, rice, water]
activity_pool: [vocabulary_grid, listen_choose, sentence_builder,
                pronunciation, roleplay, explore]
fallback_language: vi
---
(body: pedagogy notes, examples, common misconceptions, media links, world connections)
```

`lesson_run.json` — **must be sufficient to run the whole class with no LLM** (NS-1):

```json
{
  "lesson": "en-a1-market-01",
  "class": "7A",
  "focus": ["polite_request", "food_vocab"],
  "review": ["numbers_1_20"],
  "students_to_check": ["s17", "s04"],
  "activities": [
    { "type": "vocabulary_grid", "items": ["..."], "duration_s": 180 },
    { "type": "ask_choice", "prompt": "...", "options": ["..."], "correct": "apple" }
  ],
  "media_manifest": ["asset://apple.webp", "..."]
}
```

### Four memory tiers

| Tier | Holds | Stored in |
|---|---|---|
| Procedural | how to teach, strategies | Hermes Skills |
| Teacher long-term | synthesized observations about the class | Hermes memory provider |
| Learning state | per-student skill estimates | **our schema'd DB** |
| Content | curriculum, media | content store + retrieval |

Raw transcripts **never** enter Gemma's context.

### Student record

```json
{
  "student_id": "s017",
  "name": "Minh",
  "english": {
    "food_vocab": 0.82, "listening_a1": 0.71,
    "polite_request": 0.55, "speaking_confidence": 0.61
  },
  "pronunciation": { "patterns": ["/θ/ → /t/", "final -s dropped"] },
  "recent_sessions": ["market-01"]
}
```

---

## 9. Lifecycle of one class

```
BEFORE   (Hermes cron, unattended)
  read curriculum → read class state → pick review content
  → generate lesson_run.json → preload media → ready

DURING
  observe → teach → ask → student responds
  → assess → update belief → choose next action → act on Stage
  (this loop runs in the pedagogy tier; the reflex tier runs in parallel)

AFTER
  events → update student/class state → skill estimates
  → record common errors → session summary
  → prepare the next lesson
```

---

## 10. Proposed repo layout

```
bright/
├── apps/
│   ├── classroom-stage/          Vue — board + AIRI, runs in Chromium kiosk
│   └── facilitator-console/      teacher's secondary screen (override, status)
├── services/
│   ├── classroom-core/           ★ state machine + event bus + lesson runner
│   ├── perception/               MediaPipe, face, hand
│   ├── speech/                   VAD, STT, TTS (/audio/transcriptions, /audio/speech)
│   ├── pronunciation/            forced alignment + GOP
│   └── knowledge/                offline retrieval
├── mcp/
│   └── classroom-mcp/            ★ the tool contract Hermes sees
├── agent/
│   ├── skills/                   Hermes skills
│   ├── prompts/
│   ├── policies/                 pedagogy policy, scaffolding ladder
│   └── evals/                    ★ tool_routing, pedagogy, bilingual, recovery
├── content/
│   ├── curriculum/  lessons/  world/  media/  dictionaries/
├── data/
│   ├── schemas/     students/    runs/
├── vendor/
│   └── airi/                     git submodule — renderer packages only
└── infra/
    ├── hermes/                   config.yaml, systemd unit
    └── openvino/                 OVMS config, INT4 model
```

★ = irreplaceable assets (NS-4)

---

## 11. Ownership boundaries (to avoid spaghetti)

| Who | May | May not |
|---|---|---|
| **Hermes** | call MCP tools, read state via tools, write memory | touch the DOM, hold class state, handle gestures |
| **Classroom Core** | hold state, run lesson_run, grade answers, emit events | call an LLM directly |
| **Learning Stage** | render scenes, capture gestures, play audio | make pedagogical decisions, change activity on its own |
| **AIRI layer** | avatar, lipsync, animation driven by events | chat logic, model calls |
| **perception/speech** | emit events with confidence | make the final identity decision (Core fuses) |

If a PR blurs any boundary in this table → reject it.
