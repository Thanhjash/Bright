# Bright — documentation

An autonomous AI English teacher for remote, under-resourced classrooms, built
to be given away. **The AI is the teacher** — Hermes, an agent harness, reading a
curriculum library the way a coding agent reads a repo. Classroom Core is the
room's operating system and never teaches. If the model dies, the room stays up,
the adult is told, and the AI restarts. There is no lesson tape.

---

## Two files, in order

| | |
|---|---|
| 🔵 [**NORTH-STAR.md**](NORTH-STAR.md) | The bible. Why this exists, the teacher's working day, who the real user is, NS-1…NS-7. Changes rarely. If anything contradicts it, it loses. |
| 🔴 [**STATE.md**](STATE.md) | The only living execution doc. What is wired, what is next, how to boot and prove it, and the landmines. **Paste this into a new agent chat.** |

Everything else is supporting material. You do not need it to start.

---

## How this folder is organised

```
docs/
  NORTH-STAR.md    the bible                  — 1 file, rarely changes
  STATE.md         the living execution doc   — 1 file, changes constantly
  decisions/       append-only. One choice per file, dated, with evidence.
                   Read before re-litigating one. Never edited in place —
                   a reversal is a NEW file that says what it supersedes.
  design/          how the machine is put together
  research/        external research and code-grounded audits
  journals/        dated records of what happened and what it cost
  archive/         superseded. Kept for provenance. NEVER cook from it.
```

### Five rules that keep this from rotting again

It rotted once: thirteen dead files sat beside live ones, four claimed to be the
current status at the same time, and the bible listed tools that had not existed
for a week. These rules exist because of that, not in the abstract.

1. **Exactly one living document.** `STATE.md`. If a plan needs writing, it goes
   in a journal or in `STATE.md`, and is deleted when absorbed. A second "current
   status" file is how the last set drifted into thirteen.
2. **`decisions/` is append-only.** Never edit a decision to reverse it — write a
   new dated file that says what it supersedes. A stale detail inside a
   still-valid decision gets a dated correction banner, not a rewrite.
3. **Archive on the day it stops being true**, not later. `archive/README.md`
   must say what each file is wrong about.
4. **Research is evidence, not doctrine.** A finding becomes binding only when a
   `decisions/` file adopts it. Keep the three research subfolders separate:
   `prompts/` (questions we send out), `external/` (answers we commissioned),
   `notes/` (what we found ourselves).
5. **Every claim carries its source.** `file:line` for code, a citation for
   research, or the word "unproven". A number with no method behind it is a
   defect — we have shipped three wrong measurements already.

### On `references/`

The cloned repos under `references/` are **reference only**. Read them to answer
*"has anyone solved this, and how?"* — never to inherit a structure. Every one of
them was built for a different room: one learner, one device, a keyboard, the
internet. Adopting their shape quietly imports that room into ours. Take a
syntax, a process pattern, or a warning. Never an architecture, and never a
change to the north star.

---

## decisions/

| | |
|---|---|
| [teacher-agent-not-cassette.md](decisions/teacher-agent-not-cassette.md) | **2026-08-16.** Hermes is the teacher; Core is the OS; no authored-tape fallback |
| [layer-1-memory-is-enough.md](decisions/layer-1-memory-is-enough.md) | **2026-08-17.** Stop deepening the student store |
| [2026-08-18-room-runs-itself.md](decisions/2026-08-18-room-runs-itself.md) | **2026-08-18.** No product buttons. The pulse opens the class |
| [2026-08-18-three-stores.md](decisions/2026-08-18-three-stores.md) | **2026-08-18.** Three stores, three kinds of truth, and the kill list |
| [2026-08-18-evidence-and-practice.md](decisions/2026-08-18-evidence-and-practice.md) | **2026-08-18.** Abundant practice, sparse evidence, honest uncertainty. The two-axis evidence model, item families, and no cameras for attribution |
| [2026-08-18-teacher-skills.md](decisions/2026-08-18-teacher-skills.md) | **2026-08-18.** The profession lives in the library as skills, not in Hermes' skills dir |
| [2026-08-18-identity-is-perception.md](decisions/2026-08-18-identity-is-perception.md) | **2026-08-18.** A separate CPU service answers "which `student_id`". The model never recognises anyone |
| [2026-08-20-the-room-knows-who.md](decisions/2026-08-20-the-room-knows-who.md) | **2026-08-20.** Perception picks the learner before the class opens; a twelfth tool reads that child's own record |
| [2026-08-21-the-front-door.md](decisions/2026-08-21-the-front-door.md) | **2026-08-21.** `/` lists the real periods and a child presses the next one; enrolment lives there, consented. Inside the room, nothing changes |
| [option-b-classroom-runtime.md](decisions/option-b-classroom-runtime.md) | Process topology: Hermes sidecar, MCP hands, Stage owns audio, local-Gemma seam |
| [hermes-over-openclaw.md](decisions/hermes-over-openclaw.md) | Why one agent runtime, not two — with file:line evidence |
| [fact-check-gpt-brief.md](decisions/fact-check-gpt-brief.md) | The original brief, claim by claim: 25 verdicts |

## design/

| | |
|---|---|
| [data-and-content.md](design/data-and-content.md) | **Where the data is.** The curriculum on disk, the child's record in SQLite, faces in a third store, and how any of it reaches her prompt |
| [teaching-loop.md](design/teaching-loop.md) | **The workflow.** The day, one turn in full, the board, and the failure/restart doctrine |
| [tool-surface.md](design/tool-surface.md) | **Her hands.** What teaching requires, the four gaps, the proposed 11 tools, and what she deliberately never gets |
| [architecture.md](design/architecture.md) | Two control tiers, tool contract, event bus, identity, speech, ownership boundaries |
| [runtime-topology.md](design/runtime-topology.md) | Local-first → appliance. Two screens, one backend, service map, boot sequence |
| [reusing-airi-and-friends.md](design/reusing-airi-and-friends.md) | What to take from each cloned repo, and what to leave |

The wire contract lives with the code, not here:
[`packages/contracts/PROTOCOL.md`](../packages/contracts/PROTOCOL.md). Change it
*before* changing any implementation.

## research/

| | |
|---|---|
| [Practice, Assessment, and Evidence for an Autonomous Whole-Class Teacher.md](research/external/Practice,%20Assessment,%20and%20Evidence%20for%20an%20Autonomous%20Whole-Class%20Teacher.md) | Whole-class evidence, item families, the two-axis evidence model. Acted on in [evidence-and-practice](decisions/2026-08-18-evidence-and-practice.md) |
| [Offline bilingual classroom speech IO for Bright.md](research/external/Offline%20bilingual%20classroom%20speech%20IO%20for%20Bright.md) | VieNeu-TTS v3 Turbo + faster-whisper `small` multilingual. **A pending decision, not open research** |
| [2026-08-18-changemakers-inputs.md](research/notes/2026-08-18-changemakers-inputs.md) | The teammate package + 80-page textbook and 108 audio tracks. What to adopt (safety escalation, three languages, consent law, TBLT) and the one shape conflict |
| [2026-08-18-teaching-agent-repos.md](research/notes/2026-08-18-teaching-agent-repos.md) | LiaScript's markdown quiz syntax (worth taking) and a shipped product whose "adaptive difficulty" is one string in a prompt (worth avoiding) |
| [2026-08-11-edge-stack-viability.md](research/notes/2026-08-11-edge-stack-viability.md) | Gemma-on-Intel throughput, ASR/TTS options. Contains one same-day correction by measurement |
| [2026-08-11-codex-deadline-review.md](research/notes/2026-08-11-codex-deadline-review.md) | Adversarial deadline review |
| [2026-08-11-second-opinion-fable.md](research/notes/2026-08-11-second-opinion-fable.md) | Independent second opinion |
| [2026-08-12-cto-autonomous-classroom-audit.md](research/notes/2026-08-12-cto-autonomous-classroom-audit.md) | Product, architecture, classroom validity, governance, competition evidence |
| [2026-08-12-codebase-exploration.md](research/notes/2026-08-12-codebase-exploration.md) | Code-grounded audit of the interrupted implementation |
| [PROMPT-classroom-assessment.md](research/prompts/PROMPT-classroom-assessment.md) | **Ready to run.** Practice items, quizzes and evidence for 30 children on one shared screen. Feeds the open half of the tool surface |
| [PROMPT-avatar-decision.md](research/prompts/PROMPT-avatar-decision.md) | Ready-to-run prompt: which avatar format, which character |
| [PROMPT-bilingual-speech.md](research/prompts/PROMPT-bilingual-speech.md) | The prompt that produced the speech research above |

Research is dated by nature. A finding here is evidence, not doctrine — doctrine
only exists once a `decisions/` file adopts it.

## journals/

Dated records, newest last. Read one when you need to know *why* something was
done, not *what* is true now.

## archive/

Fifteen superseded documents, kept so the reasoning trail survives. Each one is
wrong about something. [`archive/README.md`](archive/README.md) says which.

---

## Running it

```bash
./scripts/fetch-models.sh   # once — Piper voices, Whisper, Live2D  (~1.7 GB)
cp .env.example .env        # once — add LLM_API_KEY
./scripts/teacher-up.sh     # speech :8001 · core :8004 · hermes :8642 · ui :3000
```

| | |
|---|---|
| `http://127.0.0.1:3000/classroom` | the room — projector view |
| `http://127.0.0.1:3000/control` | the adult's console — laptop screen, never the projector |

It is **a web application that runs on your own machine.** Nothing listens on the
internet; every service binds `127.0.0.1`. On the finished appliance the only
difference is that Chromium starts itself in kiosk mode. Full reasoning:
[design/runtime-topology.md](design/runtime-topology.md).

---

## The principles

1. **NS-1** — The AI is the teacher. If it dies: notify, keep the room, restart the AI. No cassette.
2. **NS-2** — Two control tiers. Reflex I/O never waits on the model. Pedagogy is the agent.
3. **NS-3** — The agent acts on semantics, never on the DOM. Typed tools. No HTML.
4. **NS-4** — The runtime is replaceable; the contract is not.
5. **NS-5** — Chat history is not the source of truth. Durable facts live in the DB.
6. **NS-6** — The profession is data, not code. Teaching lives in skills, not Python.
7. **NS-7** — The deployment declares itself. Software never names a language or a subject.
