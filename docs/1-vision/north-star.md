# 00 — NORTH STAR (Bible)

> **Runtime doctrine update (2026-08-12):** the authoritative live integration is
> [Option B](../2-decisions/option-b-classroom-runtime.md): Hermes is a sidecar,
> Classroom Core is the sole authority, Bright MCP is the only action boundary,
> Stage is the sole audio owner, and dedicated ASR remains primary. Hosted inference
> is pseudonymous/minimal now; a later local Gemma switch happens behind the Hermes
> profile and must pass the same provider and room gates.

> This is the root document. Every other technical decision must answer: *what does it serve here?*
> If another document contradicts this file, this file wins.

**Updated:** 2026-08-12
**Status:** direction locked; v3 autonomous vertical slice mechanically green, release gates open

---

## 1. Product thesis

We are **not** building:

- an English-learning chatbot with an avatar
- a personal English practice app (Duolingo / ELSA clone)
- a toy robot

We are building:

> **An autonomous teaching system that runs fully offline on cheap hardware, remembers each student, prepares its own lessons before class, drives a shared interactive board, and adapts the lesson based on what the class actually does.**

English here is not a "chat feature." English is **an interactive environment**: listening, seeing, speaking, pointing, touching, playing, roleplaying, and exploring the world.

### The setting: an Intel competition; exact programme attribution must be verified

This is built as an Intel-focused competition entry. Earlier project notes described
it as an **Intel × United Nations** programme, but the official Intel festival page
reviewed on 2026-08-12 does not by itself establish UN co-ownership. Use the exact
organizer wording from the entry rulebook in every public claim. The Intel/local and
child-centred/global constraints below remain product requirements regardless of the
final event name, and they reorder two things:

**1. Running locally on Intel hardware is part of the argument, not a later phase.**

Phase 1 deliberately used a hosted model (MiMo) to take plumbing off the critical path, and that was right for building. But an entry to an *Intel* programme that calls a cloud API has thrown away its own strongest claim. **OpenVINO + Gemma 4 on an Intel edge device is the showcase**, and SP-1/SP-2 are promoted from background plumbing to part of the submission.

The architecture is ready for it: Bright calls the Hermes sidecar rather than a
provider endpoint. Hosted → local changes the pinned Hermes classroom profile
(`provider`, `model`, and `base_url`) plus deployment resources, not Core, MCP,
protocol, UI, or curriculum. What is missing is measured local-Gemma conformance.

**2. The UN framing makes "global" a criterion, not an ambition.**

Two things follow immediately, and both get more expensive the longer they wait:

- **The fallback language is currently hardcoded to Vietnamese** — the scaffolding ladder, the TTS voice, and an English-only STT model. It has to become configuration.
- **The avatar's licence.** Hiyori is Live2D Inc. sample material with commercial use restricted. Selling has a revenue threshold to hide behind; **donating at scale is distribution, and that threshold does not help.** Presenting a humanitarian product at a UN programme with a character we may not distribute is a real exposure. See [tracker](../4-build/tracker.md) P1 and the research prompt.

**3. A competition also judges what it can see.** Working software is necessary and not sufficient: the demo has to run reliably in a room full of strangers, and the claims have to be evidenced. That is why measurements live in the docs instead of adjectives.

---

### Why it exists

This is meant to be **given away**, not sold. The goal is that a child in a village with no teacher, no internet and no textbook can still learn — and through English, reach everything else. The population this is aimed at is on the order of **40 million children** in remote and under-resourced areas.

That intent is not decoration. It constrains engineering directly:

| Because it is donated, and global | The system must |
|---|---|
| No licence revenue, ever | Cost per classroom is the binding constraint, not margin. Every megabyte and every watt is somebody's budget |
| Deployed where nobody can support it | Survive with no IT, no network, no updates for months, and a power cut mid-lesson |
| Not only Vietnam | Treat the fallback language as **configuration**, never a hardcoded assumption. Vietnamese is the first, not the only |
| Given to institutions | Every dependency must be legally shippable at zero cost. "Free for now" is a liability, not a saving |
| A scale of 40M | One authored lesson has to serve very many children. Content **leverage** matters more than content volume |

**Vietnam is the first deployment, not the scope.** Where a decision would be cheaper by assuming Vietnam only, prefer the one that does not.

This also settles a question that kept resurfacing: *what is the bar for "done"?* Not "impressive in a demo." The bar is **switch it on and it teaches** — and it keeps doing that when everything around it fails.

### The AI is the teacher. The adult is support.

This is the target, stated plainly because it is easy to drift from:

> **The AI teaches the class.** A human is present and supports from outside the lesson — sets it up, handles the room, steps in if something goes wrong. They are not co-teaching, and the system must never *require* them to.

The distinction matters because it changes what has to be built. A tool that assists a teacher can leave gaps for the teacher to fill. An autonomous teacher cannot.

**Autonomy demands four things.** The v3 slice establishes their deterministic
contracts, but does not yet prove a whole autonomous classroom:

| Requirement | Where we are |
|---|---|
| **Runs a whole session unattended** — paces 35–45 minutes and closes it | A 41.0–44.7 minute compiled lesson and session controller exist. Stage budgets/checkpoints are metadata, but full pacing policy is not yet executed or soak-proven |
| **Handles what is not in the script** — questions, noise, confusion | `uncertain`/`unhandled` branches and safe defaults exist. Eight authored selected-individual oral turns now have bounded recovery and Core will not open capture before its exact spoken callout is ACKed. Conversational recovery is not composed or room-proven |
| **Manages a class, not a student** — calls learners fairly and attributes evidence | Roster, attendance, deterministic fairness/cooldown, assignments and participation ledger exist. Longitudinal class-aware memory is incomplete |
| **Recovers on its own** — wrong branch, failed activity, lost capability | Capability loss and playback failure enter explicit recovery/safe pause. Recovery metadata is not yet fully executed, and a saved checkpoint is not restored after Core restart |

**What stays true regardless:** NS-1. An autonomous teacher that stops when the model is unavailable is not autonomous — it is fragile. Autonomy is built *on top of* a lesson that runs without intelligence, never instead of it.

**And the human's console is not a co-pilot seat.** It is observability plus an emergency lever. If a design ever needs the adult to make a teaching decision for the system to work, that design is wrong.

---

## 2. Who the real user is

This constraint decides everything below it:

| | |
|---|---|
| **Learners** | 20–40 students per class, sharing one projected screen |
| **Operator** | one teacher/facilitator, **not** an engineer |
| **Network** | assume **no internet** |
| **Hardware** | see below — two targets, decided at different times |
| **Context** | under-resourced schools, low budget, no on-site IT |
| **Reach** | Vietnam first; the design target is remote and under-resourced classrooms anywhere |

### Two hardware targets

```
BUILD & DEMO  (now)        a developer laptop. Windows or Linux.
                           No RAM ceiling, no cost ceiling, no SKU decision.

PRODUCTION    (later)      a cheap box, decided AFTER we measure what the
                           finished system actually needs.
```

**Do not pick production hardware before the product exists.** Published Gemma 4 throughput numbers all come from premium Core Ultra silicon (18.5 tok/s on Arc 140V iGPU); the number for budget N-series does not exist publicly ([research](../5-research/2026-08-11-edge-stack-viability.md) §1). Choosing a SKU now means guessing at a workload we have not built.

The offline constraint still holds from day one — it is an *architectural* property, not a hardware one, and retrofitting it is expensive. The 16 GB figure remains the **design intent** that keeps us honest about footprint. It is not a demo constraint.

For contrast: Pika is *1 child + 1 robot + at home*. Our problem is *1 agent + 30 children + 1 shared screen + offline*. Their architecture does not transfer.

---

## 3. Five non-negotiable principles

### NS-1 — The lesson must run even when the LLM is dead

This is **requirement #1**, not a footnote. It is the direct answer to the "students in poor schools" constraint.

Before class, the agent compiles a `lesson_run.json` (activities, media, ordering, questions, answers). During class:

- **LLM healthy** → agent orchestrates freely, redirects based on the class
- **LLM slow** (weak box, thermal throttling, RAM pressure) → the system plays `lesson_run.json` sequentially; the agent only intervenes at decision checkpoints
- **LLM dead** → the class **still runs end to end**; only adaptivity is lost

Architectural consequence: `classroom-core` must be a complete program that runs **without an LLM**. The LLM is an *enhancement* layer, never the *foundation* layer.

**This also fixes the build order, and the order is not negotiable:**

```
1. FOUNDATION    board · lesson runner · speech · avatar · the appliance
                 A complete, solid product with no intelligence in it.

2. INTELLIGENCE  the agent deciding, memory, adaptation.
                 Added on top of something that already worked without it.

3. HARNESS       inherit Hermes' agent harness — skills, cron, subagents —
                 once there is a working product for it to run inside.
```

Reversing this builds a clever thing on an unfinished thing. The layer that must never fail gets finished first, precisely because it is the layer a village school actually depends on. **When in doubt about what to work on next, the answer is whatever makes the LLM-free path more solid.**

### NS-2 — Two control tiers, never mixed

Gemma 4 E4B scores **42.2%** on Tau2 (agentic tool-use benchmark). That is the real number from the model card. It is **not reliable enough** to sit in a reflex loop.

```
REFLEX TIER  (< 100 ms)         PEDAGOGY TIER  (seconds)
──────────────────────────      ────────────────────────────
Deterministic code              Hermes + Gemma 4 E4B
No LLM                          LLM in the loop

student points → highlight      pick the next activity
drag & drop cards               decide scaffolding level
grade a multiple choice         recast the student's sentence
timers, step advance            decide who to call on
audio playback, animation       update belief about a student
```

**Never** route a student gesture through the LLM before something happens on screen.

### NS-3 — The agent acts on semantics, never on the DOM

The agent does **not** generate HTML. It does **not** call `eval()`. It does not know CSS exists.

The live agent proposes one bounded move from the opaque options Classroom Core issued:

```
classroom_propose_move(turn_id, move_id, teacher_line)
  → exactly one terminal proposal; Core revalidates and commits after playback
```

For the live Option B runtime, streamed Hermes assistant text is the only adaptive
free-text speech source. `classroom_say` is not exposed there; keeping both would
double-speak. Authored Core narration remains the deterministic fallback.

Rendering primitives (`show_vocabulary`, `ask_choice`, `sentence_builder`, …) belong to Core and are driven by `lesson_run.json`. **The model never names them.**

The renderer decides the UI. This is the single most important boundary in the system: it keeps a small model usable, and it keeps the UI testable without an LLM. Full tool contract and the fallback ladder: [architecture](../3-design/architecture.md) §3.

### NS-4 — The runtime is replaceable; the contract is not

The live runtime pins `hermes-agent 0.20.0+bright.1` to upstream commit
`03fa32c92dd445eb64c7f67434dd91b32c40701d`. Hermes is young and fast-moving;
if it stops fitting, we must be able to swap it in days, not rewrite the product.

Therefore **our actual assets** are:

1. `classroom-mcp` — the semantic tool contract
2. `classroom-core` — state machine + event bus + source of truth
3. `content/` — curriculum, lessons, media
4. `data/` — student model, skill estimates
5. `evals/` — the measurements that tell us which model is usable

Hermes, AIRI, and OpenVINO are all *swappable*. Those five are not.

### NS-5 — Chat history is not the source of truth

Classroom state lives in `classroom-core` (a schema'd DB), not in a model's context window. The model is *shown* state; it does not *own* state.

Consequence: restarting the agent mid-class does not lose Core's live lesson state.
Core now persists a controller checkpoint, but startup restore is not implemented;
power-loss/Core-restart resume remains a release gate.

---

## 4. Locked stack

```
              Hosted model now / Gemma local later
                    behind Hermes profile
                            │
                            ▼
                   HERMES SIDECAR ─ teacher brain
                   narrow live profile; broader authoring later
                            │
                     Classroom MCP        ◄── our contract
                            │
                            ▼
                   CLASSROOM CORE         ◄── source of truth
                   state machine · event bus
                   (runs without an LLM)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   Learning Stage      Perception           Speech
   (React board)       camera/face/hand     VAD·STT·TTS·Pronunciation
        │
        └── AIRI (avatar, lipsync, animation)
                            │
                            ▼
                       PROJECTOR
```

**OpenClaw is not in the runtime.** Full reasoning in [01-decision-hermes-vs-openclaw.md](../2-decisions/hermes-over-openclaw.md). It stays in `references/` as a pattern source.

Each component, in one line:

| Component | Role |
|---|---|
| **Hosted model now; local Gemma later** | raw reasoning capability behind the Hermes provider profile |
| **Hermes** | the live cognitive sidecar; broader planning/authoring profiles stay separate from the classroom trust domain |
| **Classroom MCP** | the world the agent is allowed to act on |
| **Classroom Core** | the physics of that world — and the part that runs when the agent is absent |
| **Learning Stage** | the interactive board, the class's shared stage |
| **AIRI** | the agent's body |
| **Curriculum + Student DB** | purpose and continuity |

---

## 5. Pedagogical philosophy

### Scaffolding — do not fall back to Vietnamese immediately

```
explain in English
      ↓ still lost
simpler English
      ↓ still lost
image / gesture
      ↓ still lost
concrete example
      ↓ still lost
Vietnamese hint
      ↓ still lost
Vietnamese explanation
```

The goal is for students to gradually **think in English**, not translate in their heads.

### EXPLORE mode — English as a window onto the world

A student learns `penguin`. The agent does **not** stop at "penguin = chim cánh cụt."

```
penguin → Antarctica → ice → ocean → climate
```

This is the philosophical break from every English-practice app: we are not teaching vocabulary, we are using vocabulary to open the world. For students in under-resourced schools this is the real value — **getting out of the bottom of the well**.

### Lesson flow

```
HOOK → INPUT → GUIDED PRACTICE → RETRIEVAL → INTERACTION
     → PRODUCTION → ROLEPLAY → EXPLORE → EXIT CHECK
```

The agent may route dynamically between these stages, always within the compiled `lesson_run.json`.

---

## 6. Definition of success

This system succeeds when:

1. A teacher who cannot code plugs it in, turns it on, and the class runs
2. The class still runs with the network cable pulled
3. Students are addressed by name, and the lesson remembers what they struggled with last week
4. When the agent fails, the class **does not stop**
5. Hardware cost is within reach of an under-resourced public school

Any feature that does not serve those five gets cut.

---

## 7. What we will NOT do

- ❌ No agent-generated arbitrary HTML/JS
- ❌ No gesture/click inside the LLM loop
- ❌ No raw transcripts as long-term memory
- ❌ No real learner identity or prior raw transcripts sent to a hosted model
- ❌ No second physical audio owner; only the Stage may play classroom speech
- ❌ No stacking two agent runtimes (see 01)
- ❌ No internet dependency on any primary path
- ❌ No pronunciation scores like `83.716253%` before calibration
- ❌ No raw video of students stored by default

---

## Navigation

| Doc | Contents |
|---|---|
| [Hermes decision](../2-decisions/hermes-over-openclaw.md) | Hermes vs OpenClaw decision + evidence |
| [fact check](../2-decisions/fact-check-gpt-brief.md) | Claim-by-claim verification of the GPT brief |
| [architecture](../3-design/architecture.md) | Detailed architecture, tool contract, event bus |
| [reusing AIRI](../3-design/reusing-airi-and-friends.md) | What to reuse from the three cloned repos |
| [open questions](../4-build/open-questions.md) | Open questions + spikes to run before building |
