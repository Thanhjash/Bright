# 08 — PHASE 1: THE FRAME

**Date:** 2026-08-11
**Status:** proposed, ready to build
**Goal:** a talking, teaching, remembering avatar on screen. The skeleton that everything else plugs into.

---

## 0. What changed

The user supplied a hosted OpenAI-compatible model (MiMo v2.5-pro, Singapore). **Phase 1 no longer hosts a model locally.**

Verified working 2026-08-11 against `https://token-plan-sgp.xiaomimimo.com/v1`:

| Capability | Status | Note |
|---|---|---|
| Chat completions | ✅ | `api-key:` header or `Authorization: Bearer`, both accepted |
| Disable reasoning | ✅ | `"thinking": {"type":"disabled"}` — **top-level request field** |
| Tool calling | ✅ | correctly selected `action_id` from an enum on first try |
| Streaming SSE | ✅ | standard `chat.completion.chunk` deltas |
| Prompt caching | ✅ | `cached_tokens` reported; a hidden system preamble costs ~250 prompt tokens/call |

**Trap:** `extra_body={"thinking":...}` is *Python SDK* syntax — the SDK flattens it into the request body. Over raw HTTP the field must be top-level. Get this wrong and reasoning stays on: our first test returned **empty content** after burning the entire 32-token budget on `reasoning_content`.

### What this defers

| Was | Now |
|---|---|
| OVMS + Gemma 4 E4B locally | remote HTTP call |
| SP-1, SP-2, SP-4 (Tier-0/2 plumbing) | **moot for Phase 1** |
| SP-3 tool-routing risk at Tau2 42.2 | **much lower** — MiMo is far stronger than E4B |
| Fully offline | ❌ **not offline in Phase 1** |

> ### ⚠️ The offline promise is suspended, not cancelled
>
> NS-1 and the whole product thesis rest on running with no internet. Phase 1 borrows against that deliberately, to get a working frame fast.
>
> **The debt is repaid by keeping one boundary clean:** everything model-related goes through `TeacherAgent` (§3). Swapping remote MiMo for local Gemma must be a config change plus one class, never a refactor.
>
> Two rules that keep this honest and cost nothing now:
> 1. **Never design against MiMo's strength.** The tool surface stays the 4-tool `available_actions` shape sized for a 4.5B model. If Phase 1 works only because the model is smart, Phase 3 fails.
> 2. **Everything except the LLM call stays local from day one.** Assets, state, TTS, student data, event bus. One outbound host, nothing else.

---

## 1. What Phase 1 delivers

Open a browser. See a Live2D character beside an interactive board.

1. It **greets you by name** — because it remembers you from last time
2. It **teaches a short English exchange** — vocabulary on the board, asks a question
3. You **answer** — click, or speak
4. It **reacts** — emotion animation, correct/incorrect feedback, moves on
5. It **records** what you got right and wrong
6. Between sessions it **works in the background** — reviews what happened, prepares next time

Not in Phase 1: face recognition, hand tracking, 30 students, pronunciation scoring, projector kiosk, offline operation, real curriculum.

**The teaching content in Phase 1 is a placeholder.** Ms. Quỳnh owns curriculum, prompts, and pedagogy policy. Phase 1 builds the machine that runs them, using one throwaway lesson.

---

## 2. Architecture

```
┌──────────────────────── BROWSER (localhost:3000) ────────────────────────┐
│                                                                          │
│   /classroom                              /control                       │
│   ┌──────────────────────────┐            ┌────────────────────┐         │
│   │  BoardLayer   │ Avatar   │            │ status · transcript│         │
│   │  scene render │ Live2D   │            │ pause skip takeover│         │
│   └──────────────────────────┘            └────────────────────┘         │
│              ▲          ▲                          ▲                     │
│              │ scene    │ audio+ACT                │                     │
└──────────────┼──────────┼──────────────────────────┼─────────────────────┘
               │          │      WebSocket           │
               └──────────┴────────┬─────────────────┘
                                   │
┌──────────────────── classroom-core  (Python, :8004) ─────────────────────┐
│                                                                          │
│   ws hub ──── event bus ──── state store ──── lesson runner              │
│                                   │                                      │
│                            ┌──────┴───────┐                              │
│                            │  SQLite      │  students · skills ·         │
│                            │  + FTS       │  sessions · observations     │
│                            └──────┬───────┘                              │
│                                   │                                      │
│   scheduler (background) ─────────┤                                      │
│                                   │                                      │
│   TeacherAgent  ◄─────────────────┘                                      │
│      │  tools: get_state · choose_next · say · record · recall           │
└──────┼───────────────────────────────────────────────────────────────────┘
       │  HTTPS (the ONLY outbound call in the system)
       ▼
   MiMo v2.5-pro
```

One backend process in Phase 1. Split later when there is a measured reason — `perception` and `speech` become separate services in Phase 2 because they own hardware; nothing else needs to move.

---

## 3. `TeacherAgent` — the swappable seam

This interface is the entire insurance policy for the offline promise.

```python
class TeacherAgent(Protocol):
    async def turn(self, ctx: TurnContext) -> AsyncIterator[AgentEvent]: ...
```

`AgentEvent` is a small union: `TextDelta`, `Act`, `ToolCall`, `ToolResult`, `Done`. Nothing downstream knows which implementation produced them.

| Implementation | When | Notes |
|---|---|---|
| **`DirectAgent`** | **Phase 1** | ~300 lines. Talks OpenAI-compatible HTTP directly. Full control over the prompt, the tool loop, and retries |
| `HermesAgent` | Phase 2, if needed | Hermes' value is skills, cron, subagents, MCP. Consume it behind this same interface |
| `LocalAgent` | Phase 3 | same as `DirectAgent`, `base_url` points at OVMS or llama.cpp |

### Why `DirectAgent` first — a reversal worth stating plainly

[Doc 01](../2-decisions/hermes-over-openclaw.md) chose Hermes over OpenClaw, and that analysis stands: if we run an agent framework, it is Hermes. Phase 1 asks a different question — *do we need an agent framework at all yet?*

The three things wanted from Hermes right now:

| Want | Hermes gives | But |
|---|---|---|
| memory | memory providers + `MEMORY.md` | student learning state must live in **our** schema regardless (NS-5). Hermes memory would be *teacher* memory — a nice-to-have, not the ask |
| query memory | provider-specific API | ours is SQL + FTS over the same DB the lesson runner already uses |
| background work | cron subsystem | `apscheduler` calling our own code — ~30 lines |

Against that: installing Hermes means config archaeology, disabling its retry loop ([doc 03](../3-design/architecture.md) §3), verifying it passes MiMo's non-standard `thinking` field through, and bending a single-user chat runtime toward a classroom.

**Call: ship `DirectAgent` in Phase 1. Keep `HermesAgent` as a drop-in for Phase 2**, when skills/cron/subagents earn their weight. Doc 01 is not wrong; it is answering "which framework," and Phase 1's answer is "not yet."

This is [doc 07](execution-plan.md) §6 applied — *treat the runtime as a service behind an adapter* — one step further than written.

---

## 4. The agent loop

Bounded, and sized for a small model even though Phase 1 runs a large one.

```
     ┌──────────────────────────────────────────┐
     │  1. core builds TurnContext              │
     │     · lesson position                    │
     │     · what the student just did          │
     │     · student profile (skills, history)  │
     │     · recalled memories (top-k)          │
     │     · available_actions[]  ← computed    │
     └──────────────────┬───────────────────────┘
                        ▼
     ┌──────────────────────────────────────────┐
     │  2. TeacherAgent.turn()                  │
     │     model picks ONE action + says text   │
     └──────────────────┬───────────────────────┘
                        ▼
     ┌──────────────────────────────────────────┐
     │  3. core validates                       │
     │     · action_id ∈ available_actions?     │
     │     · state_version still current?       │
     │     no → fall back to lesson_run default │
     │           (never retry in front of class)│
     └──────────────────┬───────────────────────┘
                        ▼
     ┌──────────────────────────────────────────┐
     │  4. execute: scene.update + speech.say   │
     │     text stream carries inline <|ACT|>   │
     └──────────────────┬───────────────────────┘
                        ▼
     ┌──────────────────────────────────────────┐
     │  5. record observation → SQLite          │
     └──────────────────────────────────────────┘
```

### Tools exposed to the model — five, no more

```
classroom_get_state()                        → state + available_actions[]
classroom_choose_next(state_version, action_id, params?)
classroom_say(text, style?)
classroom_record_observation(student_id, skill, result, evidence)
classroom_recall(query, k?)                  ← Phase 1 addition
```

`classroom_recall` is the "query memory" capability: full-text + recency search over past observations and session summaries. It is a **tool the model calls**, not context we always inject — which keeps the prompt small and makes retrieval auditable.

### Prompt budget

MiMo already spends ~250 prompt tokens on a hidden preamble, and reports `cached_tokens`. Keep the system prompt **stable across turns** so it caches; put everything volatile (state, available actions, recalled memory) in the final user message.

---

## 5. Memory model

Four tiers, but only three exist in Phase 1.

| Tier | Store | Phase 1 |
|---|---|---|
| Learning state | SQLite `students`, `skills` | ✅ |
| Episodic | SQLite `observations`, `sessions` + FTS5 | ✅ |
| Teacher long-term | `session_summaries`, written by the background job | ✅ |
| Procedural (skills) | files | ⏳ Phase 2 |

```sql
students          (id, name, display_name, created_at, meta_json)
skills            (student_id, skill, estimate, confidence, updated_at)
sessions          (id, student_id, started_at, ended_at, lesson_id, mode)
observations      (id, session_id, student_id, skill, result, evidence, ts)
session_summaries (session_id, summary, weak_points_json, next_focus_json)
memories_fts      -- FTS5 over observations.evidence + summaries.summary
```

`classroom_recall(query, k)` → FTS5 match, recency-weighted, returns short snippets with dates. No vector DB in Phase 1 — SQLite FTS5 is enough at this scale and has zero deployment cost. Revisit only if recall quality measurably fails.

---

## 6. Background work

`apscheduler` inside `classroom-core`. Three jobs:

| Job | When | Does |
|---|---|---|
| `summarize_session` | 30 s after a session ends | agent reads the session's observations → writes a summary + weak points |
| `prepare_next` | nightly, or on demand | reads weak points → picks review content → compiles `lesson_run.json` |
| `health_probe` | every 60 s | measures agent latency → sets FULL / DEGRADED / OFFLINE |

These use the same `TeacherAgent` — the agent genuinely works while nobody is watching, which is the behaviour asked for.

---

## 7. Frontend

React 19 + Vite + TypeScript. Justified by: the user knows React; Vite is required for AIRI's `?worker&url` worklet imports; a local SPA has no use for Next.js's server.

```
apps/classroom-ui/src/
├── routes/
│   ├── classroom/          the projector view
│   └── control/            the facilitator view
├── stage/
│   ├── AvatarLayer/        Live2D via pixi-live2d-display
│   ├── BoardLayer/         one component per SceneKind
│   ├── OverlayLayer/       subtitle, listening indicator, mode badge
│   └── SceneRouter.tsx     scene.kind → component. Unknown kind → error card
├── bus/                    WS client, reconnect, snapshot-on-gap
├── speech/                 text → TTS → AudioBuffer → playback → lipsync
└── store/                  zustand
```

### Avatar: Live2D first

VRM needs react-three-fiber plus a port of `VRMModel.vue` (1041 lines). Live2D needs `pixi-live2d-display` plus a port of `motion-manager.ts` (522 lines, Vue-type-only). Live2D is lighter on a laptop and the faster path to a moving mouth. VRM stays possible — `loadVrm()` in `vrm/core.ts` is already framework-free.

### Reused from AIRI, verbatim, no Vue

| Package | Lines | Gives |
|---|---|---|
| `model-driver-lipsync` | 157 | wLipSync worklet, vowel→mouth, tuned profile |
| `pipelines-audio` | ~2200 | playback queue, TTS chunker, ordering gate, ACT parser |
| `stream-kit` | 96 | ordered async queue |

Ported with a `Ref` shim: `motion-manager.ts`, `expression-controller.ts`, live2d `utils/*`.
Rewritten in React: the `.vue` components and Pinia stores — which [doc 04](../3-design/reusing-airi-and-friends.md) always said we'd rewrite.

---

## 8. Build order

Each step ends in something runnable. No step depends on a later one.

```
B0  contracts        PROTOCOL.md → TS types + Pydantic models          ✅ done
B1  core skeleton    FastAPI, WS hub, event bus, SQLite, state store
B2  ui skeleton      React+Vite, WS client, SceneRouter, 3 scene kinds
                     → board renders scenes pushed by hand. No agent, no audio.
B3  agent            DirectAgent → MiMo, 5 tools, turn loop, validation
                     → it decides what to show. Still silent.
B4  speech           TTS → AudioBuffer → playback queue → subtitles
                     → it talks.
B5  avatar           Live2D + lipsync + ACT tokens → emotion
                     → it is alive. ★ Phase 1 demo ★
B6  memory+bg        recall tool, session summary, scheduler
                     → it remembers and works in the background.
```

B1 and B2 are independent — parallel. B3 needs B1. B4 needs B2. B5 needs B4.

### Parallelisation, without collisions

Each agent owns exactly one directory and may not write outside it. All code against `packages/contracts/PROTOCOL.md`, which is frozen before any of them start.

```
services/classroom-core/   ← agent A
apps/classroom-ui/         ← agent B
packages/airi-bridge/      ← agent C   (vendor + de-Vue the AIRI packages)
services/agent/            ← agent D   (DirectAgent + prompts + tools)
```

---

## 9. Risks specific to Phase 1

| Risk | Handling |
|---|---|
| **Building against a strong model, deploying on a weak one** | tool surface stays 4+1, sized for E4B. Re-run the same scenarios on a small model before Phase 3 commits |
| **The offline promise quietly dies** | this document. One outbound host, one seam, stated debt |
| MiMo's hidden system preamble fights our prompt | measured: ~250 tokens. Keep our system prompt stable for cache hits; test for instruction conflicts early |
| `thinking` field not passed through by a future middleman | it is a non-standard field — a reason `DirectAgent` (which controls the request body) beats a framework in Phase 1 |
| API key in plaintext | `.env`, gitignored. **Rotate after the prototype** — it has been through a chat transcript |
| Live2D model licensing | need a model we may legally ship. Resolve before any public demo |

---

## 10. Open items for the human

| # | Needs a decision |
|---|---|
| P1 | **Which Live2D model?** Need one that is legally shippable. Free options exist (Hiyori sample, etc.) — confirm licence before the demo |
| P2 | **TTS provider for Phase 1.** MiMo is chat-only. Options: a hosted TTS API, or local Piper immediately. Piper is the Phase 3 answer anyway — starting there avoids a throwaway |
| P3 | **One throwaway lesson** for B2–B5. Ms. Quỳnh's real curriculum plugs in after the frame works; this is scaffolding, ~10 minutes of content |
| P4 | Rotate the API key after prototyping |
