# Bright — documentation

An autonomous AI English teacher for Vietnamese classrooms. It is local-first and
keeps teaching when the network or model is unavailable. Hosted inference is an
explicit transitional mode; local Gemma remains the deployment target.

**New here? Read [1-vision/north-star.md](1-vision/north-star.md).** Everything else answers to it.

---

## Is this a website or a desktop app?

**A web application that runs on your own machine.** The classroom UI, Core, speech,
and learner data are local. During the current transition Hermes may call a hosted
model under the minimal-data policy in the Option B decision; primary lesson flow
never depends on that connection.

```
open Chrome  →  http://127.0.0.1:3000/classroom  →  press F11  →  plug in the projector
```

That is the product. On the finished appliance the only difference is that Chromium starts by itself in kiosk mode:

```bash
chromium --kiosk http://127.0.0.1:3000/classroom
```

The teacher sees a lesson. Not Chrome, not an address bar, not Linux. **Nobody needs to learn desktop app development** — a native wrapper (Tauri) is a packaging option we may never need. Full reasoning: [3-design/runtime-topology.md](3-design/runtime-topology.md).

The one thing that *is* unusual: **nothing listens on the internet.** Every service binds `127.0.0.1`. Your machine is both the server and the client.

---

## Running it

```bash
./scripts/fetch-models.sh     # once — Piper voices, Whisper, Live2D  (~1.7 GB)
cp .env.example .env          # once — add LLM_API_KEY
./scripts/dev.sh              # start everything
./scripts/dev.sh status       # what is up
```

| | |
|---|---|
| `http://127.0.0.1:3000/classroom` | the projector view |
| `http://127.0.0.1:3000/control` | the teacher's panel — on the laptop screen, extended display |

Services: `speech :8001` · `core :8004` · `ui :3000` · optional Hermes `:8642`.
Set `BRIGHT_AGENT=hermes` for the Option B runtime, `scripted` for deterministic
rehearsal, or `off` for the authored-only path. Legacy `BRIGHT_AGENT=1` maps to
the older DirectAgent compatibility path, not the production primary.

---

## Where things are

```
docs/
├── 1-vision/      why this exists. Changes rarely. The north star governs everything.
├── 2-decisions/   choices made, with evidence. Read before re-litigating one.
├── 3-design/      how it works. Architecture, topology, what we reuse and why.
├── 4-build/       what we are doing. Plans, open questions, and two LIVING docs.
├── 5-research/    external research and code-grounded audits.
└── journals/      concise records of decisions, deviations, and lessons learned.
```

### 1-vision
| | |
|---|---|
| [north-star.md](1-vision/north-star.md) | **The bible.** Thesis, who the real user is, five non-negotiable principles, the locked stack, pedagogy, definition of success |

### 2-decisions
| | |
|---|---|
| [hermes-over-openclaw.md](2-decisions/hermes-over-openclaw.md) | Why one agent runtime, not two — with file:line evidence. Patterns worth borrowing from the loser |
| [fact-check-gpt-brief.md](2-decisions/fact-check-gpt-brief.md) | The original GPT brief, claim by claim: 25 verdicts, and the two that could have burned days |
| [option-b-classroom-runtime.md](2-decisions/option-b-classroom-runtime.md) | **Current runtime decision.** Hermes sidecar, Core/MCP authority, speech ownership, privacy, failure policy, and local-Gemma seam |

### 3-design
| | |
|---|---|
| [architecture.md](3-design/architecture.md) | Two control tiers, the tool contract, event bus, identity fusion, speech, content model, ownership boundaries |
| [runtime-topology.md](3-design/runtime-topology.md) | Web-first / local-first / appliance-final. Two screens one backend, service map, Stage layers, boot sequence |
| [reusing-airi-and-friends.md](3-design/reusing-airi-and-friends.md) | What to take from each cloned repo, and what to leave |

### 4-build
| | |
|---|---|
| [state-of-the-project.md](4-build/state-of-the-project.md) | 🔴 **LIVING. Read this first if you want the honest picture.** What is proven, what is not, what to do next |
| [tracker.md](4-build/tracker.md) | 🔴 **LIVING.** Status board, definition of done per component, integration tests, measured facts, risks |
| [phase-1-plan.md](4-build/phase-1-plan.md) | Historical Phase-1 plan. Hosted model seam, agent loop and memory schema; superseded where it conflicts with v3 status/roadmap |
| [execution-plan.md](4-build/execution-plan.md) | Adversarial review. What actually kills this project, and milestone ordering |
| [open-questions.md](4-build/open-questions.md) | Eleven spikes with kill criteria, plus decisions that need a human |
| [option-b-implementation-status.md](4-build/option-b-implementation-status.md) | **Current implementation handoff:** delivered slices, verification evidence, and remaining release blockers |
| [autonomous-classroom-roadmap.md](4-build/autonomous-classroom-roadmap.md) | **Current product roadmap:** dependency-ordered gates from Option B to a competition-ready autonomous classroom |

### 5-research
| | |
|---|---|
| [2026-08-11-edge-stack-viability.md](5-research/2026-08-11-edge-stack-viability.md) | Gemma-on-Intel throughput, ASR/TTS options, constrained decoding. **Contains one correction issued the same day by direct measurement** |
| [PROMPT-avatar-decision.md](5-research/PROMPT-avatar-decision.md) | Ready-to-run deep-research prompt: which avatar format, and which character for Vietnamese children |
| [2026-08-12-codebase-exploration.md](5-research/2026-08-12-codebase-exploration.md) | Code-grounded audit of the interrupted implementation; historical observations, not runtime doctrine |
| [2026-08-12-cto-autonomous-classroom-audit.md](5-research/2026-08-12-cto-autonomous-classroom-audit.md) | CTO audit of product, architecture, classroom validity, appliance, local Gemma, governance and competition evidence |

### Journals
| | |
|---|---|
| [260812-autonomous-classroom-roadmap.md](journals/260812-autonomous-classroom-roadmap.md) | Decision record: autonomous classroom as release unit, Option B retained, evidence-gated execution |
| [260813-ideal-composed-evidence.md](journals/260813-ideal-composed-evidence.md) | One hosted synthetic adult composed turn: exact evidence, privacy observation and remaining room gates |

### Outside `docs/`
| | |
|---|---|
| [`packages/contracts/PROTOCOL.md`](../packages/contracts/PROTOCOL.md) | **The wire contract.** Lives with the code because code must not drift from it. Change this *before* changing any implementation |

---

## The five principles

1. **NS-1** — The lesson runs even when the LLM is dead. `classroom-core` is a complete program without one.
2. **NS-2** — Two control tiers. The reflex tier (<100 ms) never routes through a model.
3. **NS-3** — The agent acts on semantics, never on the DOM. Core validates every proposal; streamed assistant text is the single adaptive voice source.
4. **NS-4** — The runtime is replaceable; the contract is not.
5. **NS-5** — Chat history is not the source of truth. State lives in Core, in a schema.

---

## Status

```
✅  protocol/runtime floor Protocol v3, class sessions, leases, capture correlation
✅  Option B live boundary one terminal Hermes proposal tool; Core commits after playback
✅  product lesson draft   41.0–44.7 minute Market Food paths; eight authored individual oral turns and recovery paths terminate headlessly
✅  mechanical evidence   Core 242; agent 83; AIRI 169; Chromium v3 2; content contract 9 + hardened acceptance harnesses green
⚠️  release verification  one synthetic adult Chromium → Whisper/Core → hosted Hermes/MCP → Piper/AIRI turn has causal ACK/commit evidence; full Market, physical-room and child proof do not
🔴  approval/governance    curriculum approver, child-room evidence and ship rights remain
```

Agent evidence excludes four live-provider tests. The Chromium v3 test is a mocked
browser contract flow, not real audio or Hermes evidence. Test counts in older build
documents are historical snapshots; use repository commands and release gates at the
commit being evaluated.
