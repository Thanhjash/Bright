# 06 — RUNTIME TOPOLOGY, PACKAGING & DIRECTORY LAYOUT

**Date:** 2026-08-11
**Governed by:** [north star](../1-vision/north-star.md)

---

## The one-sentence answer

> **Web-first. Local-first. Appliance-final.**

The product is a **local-first web application backed by native local AI services**. The classroom board and the facilitator console are web frontends. Hermes, Gemma/OpenVINO, vision, speech, and memory run locally as backend services. In production the same web UI is launched in Chromium kiosk mode on a dedicated Linux appliance — or, later, wrapped with Tauri.

**It is not a cloud web app, and "desktop vs web" is the wrong question.** Web technology is the UI layer; local services are the backend; the desktop/kiosk shell is packaging.

---

## 1. Two screens, one backend

```
                    AI CLASSROOM APPLIANCE
┌──────────────────────────────────────────────────────────┐
│                                                          │
│  LOCAL BACKEND (no network egress)                       │
│                                                          │
│   OVMS + Gemma 4 E4B ── Hermes ── Classroom MCP          │
│                            │                             │
│                     Classroom Core                       │
│              (state, event bus, lesson runner)           │
│                            │                             │
│         speech ── vision ── pronunciation ── knowledge   │
│                                                          │
│                localhost REST + WebSocket                │
│                            │                             │
│         ┌──────────────────┴───────────────────┐         │
│         ▼                                      ▼         │
│  FACILITATOR CONSOLE                   CLASSROOM STAGE   │
│  laptop screen                         projector         │
│  /control                              /classroom        │
│  status, override, take-over           AIRI + board      │
│                                                          │
└──────────────────────────────────────────────────────────┘
```

The laptop uses **Extend display**, not Mirror. Students never see the console.

### Classroom Stage — `/classroom`

Full screen. No browser chrome, no address bar, no settings, no terminal. Contains AIRI, the interactive board, images, video, games, word cards, sentence builder, roleplay scenes, pronunciation feedback, hand cursor, subtitles.

### Facilitator Console — `/control`

```
┌────────────────────────────────────┐
│  English · Class 7A                │
│  Lesson: At the Market             │
│  Stage:  Roleplay      [3 of 9]    │
│  Mode:   FULL                      │
│                                    │
│  Current student: Minh   (0.86)    │
│                                    │
│  Face ID    ✓      STT   listening │
│  Agent      thinking  Gemma  ready │
│  RAM 11.2/16 GB    p95 1.8s        │
│                                    │
│  [Pause] [Skip] [Repeat] [Back]    │
│  [Choose student]  [Take over]     │
└────────────────────────────────────┘
```

`Take over` is not a nice-to-have. Codex ranked loss of teacher control as risk #2 for this product. The console must let a teacher steer or stop the agent at any moment, with one tap, without understanding anything about the system. See [execution plan](../4-build/execution-plan.md).

---

## 2. Why web, concretely

| Reason | Detail |
|---|---|
| AIRI is already web | Vue, WebAudio, WebGPU, WebSocket, VRM, Live2D. Rewriting natively throws away the only avatar stack we have |
| The board is a web problem | drag-and-drop, cards, animation, canvas, video, gesture cursor — all trivial in DOM/Canvas, all painful natively |
| Projector | browser fullscreen is exactly right |
| Iteration speed | hot reload beats a native rebuild loop, and content authoring will dominate this project ([execution plan](../4-build/execution-plan.md)) |
| Hardware portability | the same frontend runs on a Windows laptop, a Linux laptop, an Intel mini-PC, and a future custom box with no UI rewrite |

### But the end user must never see a browser

```
DEVELOPMENT              PRODUCTION
pnpm dev                 power on
open Chrome         →    Linux boots
localhost:3000           services start (systemd)
                         Chromium kiosk launches
                         Classroom Stage appears
```

The teacher sees "AI Classroom." Not Ubuntu, not Chrome, not `localhost:3000`.

---

## 3. Service map

```
localhost:3000   classroom-ui        Vue app — /classroom and /control
localhost:8004   classroom-core      state, event bus, lesson runner, WS hub
localhost:8642   hermes              agent API (OpenAI-compatible)
localhost:8001   speech              VAD, STT, TTS
localhost:8002   vision              face, hand, tracking
localhost:8003   pronunciation       forced alignment, GOP
localhost:8005   knowledge           offline retrieval
localhost:9000   ovms                Gemma 4 E4B INT4
```

**All bound to `127.0.0.1`.** Nothing listens on an external interface. Ever.

### Merge policy

Start with these split for clarity, then merge aggressively once measured. On a 16 GB box, per-process Python overhead is real money. Likely merges after SP-4:

- `vision` + `speech` → one `perception` process (they share camera/audio device handles anyway)
- `pronunciation` into `speech` (shares the acoustic model)
- `knowledge` into `classroom-core` (it is a retrieval function, not a service)

Target end state: **4 processes** — `ovms`, `hermes`, `classroom-core` (+knowledge), `perception` (+speech+pronunciation), plus Chromium.

### Transport

- **REST** for request/response (`/audio/transcriptions`, `/audio/speech`, tool calls)
- **WebSocket** from `classroom-core` to both UIs for the event stream

The UI subscribes to the bus and renders. It never polls.

```json
{ "type": "student.speech.final", "seq": 4471, "state_version": 88,
  "student_id": "s017", "confidence": 0.71,
  "payload": { "text": "I would like an apple" } }
```

---

## 4. Learning Stage internals

**AIRI and the board are one application, not two windows.** Do not run AIRI standalone and iframe a whiteboard into it. We vendor AIRI's renderer packages ([reusing AIRI](reusing-airi-and-friends.md)) into our own Vue app.

```
ClassroomStage
│
├── CharacterLayer      AIRI — VRM/Live2D, lipsync, emotion, gaze
│
├── BoardLayer          the lesson world
│   ├── VocabularyGrid      ├── SentenceBuilder
│   ├── ChoiceGrid          ├── MatchingBoard
│   ├── RoleplayScene       ├── PronunciationStrip
│   ├── VideoStage          ├── StoryView
│   └── ExploreView
│
├── InteractionLayer    HandCursor, Highlights, DropZones
│
└── OverlayLayer        Subtitle, StudentName, ListeningIndicator,
                        ModeBadge (only visible in DEGRADED/OFFLINE)
```

AIRI **lives beside the board, not on top of it.** The board carries the pedagogy; the avatar carries presence (NS-3).

### Scene contract

Core owns scene state; the Stage is a pure renderer of it.

```json
{
  "scene": "roleplay",
  "version": 1,
  "state_version": 88,
  "environment": "market",
  "ai_role": "shopkeeper",
  "student_role": "customer",
  "target_phrases": ["I would like...", "How much is this?"],
  "overlay": { "subtitle": "Hello! What would you like?" }
}
```

Rules, mirroring the OpenClaw A2UI lesson ([reusing AIRI](reusing-airi-and-friends.md) §C):

1. Every scene payload carries a `version`. The Stage **rejects** unknown versions loudly rather than rendering something wrong.
2. The Stage never decides what comes next. It renders state and emits interaction events.
3. Reconnect is a first-class path: the Stage asks for a full scene snapshot by `state_version` and re-renders from scratch.

---

## 5. Directory layout

```
bright/
│
├── docs/                          ← this documentation
├── references/                    ← cloned upstreams, read-only (git-ignored)
│   ├── hermes-agent/  airi/  openclaw/
│
├── apps/
│   ├── classroom-ui/              ONE Vue app, two routes
│   │   ├── src/
│   │   │   ├── routes/
│   │   │   │   ├── classroom/     /classroom — projector
│   │   │   │   └── control/       /control   — facilitator
│   │   │   ├── stage/
│   │   │   │   ├── CharacterLayer/
│   │   │   │   ├── BoardLayer/
│   │   │   │   │   └── activities/    one component per activity type
│   │   │   │   ├── InteractionLayer/
│   │   │   │   └── OverlayLayer/
│   │   │   ├── bus/               WS client, event types, reconnect
│   │   │   ├── scene/             scene schema + version gate
│   │   │   └── speech/            TTS playback, AudioBuffer → lipsync
│   │   └── vite.config.ts
│   └── authoring-studio/          ← lesson authoring tool. See note below
│
├── services/
│   ├── classroom-core/            ★ state machine · event bus · lesson runner
│   │   ├── state/    bus/    runner/    grading/    modes/
│   ├── perception/                face, hand, tracking, identity fusion
│   ├── speech/                    VAD, STT, TTS
│   ├── pronunciation/             G2P, forced alignment, GOP
│   └── knowledge/                 offline retrieval
│
├── mcp/
│   └── classroom-mcp/             ★ the 4-tool contract Hermes sees
│
├── agent/
│   ├── skills/       Hermes skills — pedagogy strategies
│   ├── prompts/      system prompt, scaffolding ladder
│   ├── policies/     what the agent may never do
│   └── evals/        ★ tool_routing · pedagogy · bilingual · recovery · policy
│
├── content/
│   ├── curriculum/   level/unit structure
│   ├── lessons/      lesson.md sources (hand-authored)
│   ├── world/        EXPLORE topics
│   ├── media/        images, video, audio  (content-addressed)
│   └── dictionaries/ G2P, phoneme tables
│
├── data/
│   ├── schemas/      JSON Schema for every contract — the real spec
│   ├── students/     student records (gitignored, encrypted at rest)
│   └── runs/         compiled lesson_run.json per class per day
│
├── vendor/
│   └── airi/         git submodule — renderer packages only
│
├── infra/
│   ├── hermes/       config.yaml, systemd unit
│   ├── openvino/     OVMS config, INT4 model
│   ├── systemd/      all .service units
│   ├── kiosk/        Chromium kiosk launcher, display config
│   └── image/        appliance build scripts
│
└── tools/
    ├── lesson-lint/  validates lesson.md → can it produce a complete run?
    └── bench/        latency + RAM harness for the spikes
```

★ = irreplaceable assets (NS-4)

### Two notes on this layout

**`apps/authoring-studio/` is not optional.** Codex's review identifies lesson-authoring cost as the #1 project-killer ([execution plan](../4-build/execution-plan.md)). If authoring a lesson means hand-writing JSON, the project dies of content starvation regardless of how good the agent is. This tool exists to make one lesson cheap. It is a Tier-0 deliverable, not a nice-to-have.

**`data/schemas/` is the real specification.** Every contract — scene payload, event envelope, `lesson_run.json`, student record, tool arguments — gets a JSON Schema. Core validates on both sides. This is what makes the deterministic tier testable without an LLM, and it is what lets us swap Hermes out (NS-4) without archaeology.

---

## 6. Boot sequence

```
power on
   ↓
Linux (minimal, no desktop environment)
   ↓
systemd
   ├── ovms.service              (wants: network-online off; local only)
   ├── hermes.service            (after: ovms)
   ├── classroom-core.service    (after: hermes)
   ├── perception.service
   ├── speech.service
   └── classroom-ui.service      (static server)
   ↓
kiosk.service → Chromium --kiosk http://localhost:3000/classroom
   ↓
Stage shows "Ready" — teacher picks today's class
```

### Non-negotiable operational properties

| Property | Requirement |
|---|---|
| Cold boot to ready | < 90 s, including model load |
| Crash recovery | every unit `Restart=always`; Stage reconnects and resnapshots by `state_version` |
| A crashed agent | Core drops to DEGRADED, class continues (NS-1) |
| A crashed Stage | Chromium restarts, resnapshots, resumes mid-activity |
| Updates | offline. USB or scheduled sync visit ([open questions](../4-build/open-questions.md) Q5) |
| Logs | local, rotated, no telemetry egress |
| Shutdown | pulling the power must not corrupt student data — write-ahead or atomic swap |

---

## 7. Packaging path

```
PHASE 1  dev + DEMO   laptop. pnpm dev + Chrome fullscreen + local services.
                      ★ The school demo happens here. Do not wait for hardware. ★
PHASE 2  prototype    Intel mini-PC, Linux, systemd + Chromium kiosk
PHASE 3  appliance    prebuilt disk image, first-boot wizard, no shell exposed
PHASE 4  optional     Tauri wrapper — only if it buys something concrete
```

**Phase 1 carries the demo.** A laptop plugged into a projector, running Chrome in fullscreen (`F11`, or `--kiosk` if you want it clean), is a complete demonstration of the product. Nothing about the pitch requires a dedicated box — a school watching the lesson run cannot tell what it is running on, and does not care.

What this buys: the hardware SKU decision moves *after* we know the real workload, instead of before. Phase 2 then becomes a porting exercise with measured requirements, not a bet.

What must still hold in Phase 1, or Phase 2 becomes a rewrite:
- everything binds to `127.0.0.1`, no cloud calls anywhere on the primary path
- services are separate processes talking over REST/WS — not one monolith that has to be pulled apart later
- the UI is already the two-route split (`/classroom`, `/control`); use extended display on the laptop
- schemas versioned from line one

**Tauri is packaging, never architecture.** Adopt it only when a specific need appears: system tray, auto-start management, camera permission UX, native filesystem access, or auto-update. Note that AIRI's own desktop app is Electron and its Tauri path is legacy ([fact check](../2-decisions/fact-check-gpt-brief.md) #22), so we would not inherit anything from AIRI by choosing Tauri — it is an independent decision.

Until then, **Chromium kiosk is the shipping configuration.** It is simpler, lighter on a 16 GB box, and has no getUserMedia caveats — unlike an embedded WebView ([Hermes decision](../2-decisions/hermes-over-openclaw.md)).

---

## 8. What must be true for this topology to hold

- Chromium with WebGL/Live2D + a 4.5 GB model + speech + vision must coexist in 16 GB → **SP-4**
- The WS event bus must sustain gesture-rate traffic without jitter on the projector → measured in **SP-5**
- Reconnect-and-resnapshot must be genuinely seamless mid-activity → build it early, test by killing Chromium during a lesson
- All schemas versioned from day one — retrofitting versioning after content exists is expensive
