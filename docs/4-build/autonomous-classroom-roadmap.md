# Execution roadmap — teacher loop first

**Updated:** 2026-08-16  
**Authority:** current execution order  
**North Star:** [1-vision/north-star.md](../1-vision/north-star.md) still wins on product thesis  
**Research:** [5-research/2026-08-16-teacher-loop-roadmap.md](../5-research/2026-08-16-teacher-loop-roadmap.md)

This file replaces feature-count planning and the older G0–G8 “do everything at once”
order. The destination is unchanged: one autonomous AI teacher for 20–40 children on
a shared board, later offline on cheap Intel hardware. The build order is now the
smallest teacher loop first.

Do not declare a later layer while its evidence is fake.

---

## 1. Destination (unchanged)

We are not building a chatbot with an avatar.

We are building:

> An autonomous teaching system that runs offline on cheap hardware, remembers each
> student, prepares its own lessons, drives one shared board, and adapts from what
> the class actually does.

Success is still the five North Star tests: plug in and it teaches; unplug the
network and it still teaches; children are known over time; agent failure does not
stop the class; hardware is cheap enough to give away.

1:1 text is the maturity wedge, not a product fork.

---

## 2. Locked sequence

```text
0  Floor already in repo     Core lesson_run, protocol v3, authored fallback
1  Text teacher brain        Hermes + 1 MCP tool, 1 learner, hosted API
2  Thin text station         /learn + TeacherContext + local assets
3  Voice                     TTS of teacher_line, then Bright ASR
4  Body                      AIRI lipsync on Stage (not a second agent)
5  Classroom                 20–40, fairness, optional student detector
6  Local mind                Gemma 4 behind the same Hermes profile
7  Giveaway                  consent, licences, appliance, locale
```

Hosted API now. Local Gemma later. Same Core, MCP, protocol, UI, and curriculum.

AIRI, ASR, detector, and legal work are real, but they are not the current
critical path.

---

## 3. Tool and board contract

Three classroom capabilities are required for a real lesson:

| Capability | Owner | Hermes sees |
|---|---|---|
| Show / crop an image | Core + Stage | a legal `move_id`, never a filesystem path |
| Play / pause authored audio | Core + Stage | a legal `move_id` such as `replay_model` |
| Write dialogue / words on the board | Core + Stage | a legal `move_id`; Core already holds the lines |

Live Hermes keeps **one** terminal tool:

```text
classroom_propose_move(turn_id, move_id, teacher_line)
```

Core computes `available_actions[]` from `lesson_run.json`. Hermes chooses one
legal pedagogical move and one short teacher line. Core turns that move into
image / audio / board updates.

Rejected live tools (teammate draft and chatbot demos):

- `display_image(path)`, `play_audio(path)`, `write_class_memory`
- free chat (“Ask Gemma about an animal”)
- Hermes TTS / STT / filesystem / browser
- AIRI `core-agent`

Adaptive teaching means: repeat, scaffold, replay the model track, zoom the
current panel, invite a pair, or stay on the task cycle. It does not mean
inventing a new slide or a new vocabulary item.

Assets are `asset://id` in a local store. Google Drive is an ingest source only.

---

## 4. Data layer

```text
content/lessons/     authored units (locked vocabulary, TBLT phases)
assets/              local images, audio, video (hashed, offline)
data/runs/           compiled lesson_run.json + preloaded media
data/students/       Core semantic memory only
```

Persist:

- class unit progress, function mastery, pacing notes
- optional per-student `demonstrated | emerging | not_observed` and
  `confidence_trend` when identification and consent exist

Do not persist:

- raw classroom video / audio beyond the session
- chat transcripts as memory
- face boxes, match percentages, or ranks on the projector

Student detector / face+seat fusion is a Layer 5 input to Core. Hermes receives
an opaque learner id, never pixels. Identity is never drawn on the shared board.

---

## 5. Layers and exit gates

### Layer 0 — Floor (keep; do not expand)

Already true enough to build on: Core can play an authored `lesson_run.json`
with Hermes dead; Protocol v3 exists; pinned Hermes sidecar and one proposal
tool exist; one hosted composed turn has historical evidence.

Exit: do not regress the LLM-free path. No new foundation features until
Layer 1 is green.

### Layer 1 — Text teacher brain  **NOW (tool-call gate green)**

Baseline: clean `main`, pinned `0.20.0+bright.2` **wire-only** (exact
`tool_choice` for `mcp__bright_classroom__classroom_propose_move`). Do not
bring the parked 1:1 `/learn` pile.

How to run:

```bash
./scripts/hermes-layer1-probe.sh bootstrap
./scripts/hermes-layer1-probe.sh run
```

Evidence:

| Run | Result |
|---|---|
| `bright.1` + `tool_choice: required` (`…T153445Z…`) | 9/10 live legal MCP; `wrong-3` completed with 0 tools |
| `bright.2` exact function (`…T155028Z…`) | **10/10 live + reconnect**; timeout fail-closed in 81 ms; no sentinel leak |

Root cause of the miss: MiMo can return `completed` with no function call
when the wire only says `required`. Pinning the exact terminal tool cleared
it on the second live sample. First turn ~15 s (cold); later turns ~2–4 s.

Layer 1 is **not** finished. Remaining exit:

- repeat this probe until no-tool stays at 0 across two consecutive green runs
- one learner finishes a 25-minute **text** lesson three times (Layer 2 attach)

Parked, not deleted: `wip/20260814-1to1-text-unproven`.

### Layer 2 — Thin text station

Cherry-pick from the parked branch only after Layer 1 is green:

- `/learn` as a child text station, not a chat product
- `TeacherContext`, mastery, legal moves
- first real unit (Market Food 1:1 or compiled Global Success *Hello*)

Board image / audio / text appear because the **current activity** says so,
or because Hermes chose a legal move that Core already knows how to render.

Exit: one child completes the text lesson without an adult teaching decision.

### Layer 3 — Voice

Same loop, new channel.

1. TTS of the validated `teacher_line` (and authored tracks). Stage is the
   only speaker.
2. Then Bright ASR for assigned turns. Not Hermes voice tools. Not AIRI’s
   streaming server.

Exit: one learner, multi-turn speech; half-duplex; echo does not grade;
authored narration continues if Hermes dies.

### Layer 4 — AIRI body

From `references/airi` take Live2D/VRM + wLipSync + playback queue.

Do not take `core-agent`, Tamagotchi, Telegram, or the 900-line Vue stage
app. AIRI renders a speech turn Core already committed.

Hiyori sample licence is not shippable at donation scale. Choose a
distributable character before a public demo.

### Layer 5 — Classroom 20–40

Same Core / Hermes / Stage. Add fairness, named callouts, one mic, pair
tasks, facilitator emergency in Vietnamese.

Optional student detector feeds Core identity fusion only after consent.
No ranking. No biometric overlay on the projector.

Exit: 35–45 minute lesson, 20–40 learners, AI teaches, adult does not Skip.

### Layer 6 — Local Gemma

Change Hermes `provider` / `model` / `base_url` only. Re-run the Layer 1
and Layer 3 conformance suites.

Probe OpenVINO / Gemma 4 E4B **in parallel after Layer 1 is green**. It
must not reorder Layers 1–2. E4B is small; the one-tool contract is what
makes it usable. SKU purchase waits for measured RAM / tokens / thermal.

### Layer 7 — Giveaway

- Child data: written guardian consent; additional child consent if aged 7+;
  silence is not consent. Confirm against the current Vietnamese personal-data
  decree (NĐ 13/2023, successor NĐ 356/2025) with a human lawyer before any
  real-child detector/ASR store.
- Textbook assets: Global Success pages/tracks are prototype-private until
  NXB GD + Macmillan permission, or replace with original media.
- Locale is configuration, not hardcoded Vietnamese.
- Appliance, power-loss, SBOM, signed updates.

Hermes cron / skills may prepare tomorrow’s `lesson_run` in a **separate**
trust domain. They stay out of the live classroom profile.

---

## 6. First unit (content, not chat)

The teammate Global Success Grade 3 Unit 1 *Hello* package is a valid
**curriculum spec**: TBLT phases, locked vocabulary, local asset manifest,
no public marks, choral-before-individual, escalation to the facilitator.

Compile it to `lesson.md` + `lesson_run.json` + `asset://…`. Do not paste
the long system prompt into live Hermes. Core owns phase order, timers,
and fallbacks. Hermes only chooses among legal moves for the current step.

Do not teach *What’s your name?* in this unit. That is Unit 2.

---

## 7. Explicitly out of the current critical path

- New `/learn` features, browser acceptance as “Hermes proof”
- AIRI polish, face boxes, Ask-Gemma chat
- Extra Hermes MCP tools
- Claiming “Hermes reliability completed” without repeated live evidence
- Auth, appliance, SBOM, and licence work as a substitute for a working teacher
- Developing on the dirty 1:1 WIP tree

---

## 8. Historical G0–G8 map

The 2026-08-12/14 gates remain useful as **later evidence labels**, not as
this week’s order:

| Old gate | Lives in |
|---|---|
| G0 product truth / compiler | Layer 0, keep green |
| G1 one teaching product | Layer 2 + Layer 6 content |
| G2 class controller | Layer 5 |
| G3 oral interaction | Layer 3 |
| G4 product UX | Layers 2 and 5 |
| G5 composed room evidence | Layers 3–5 |
| G6–G8 local Gemma, appliance, governance | Layers 6–7 |

---

## 9. Next action

Layer 1 tool-call gate is green on `0.20.0+bright.2`. Next: a second
consecutive green probe, then cherry-pick Layer 2 (`/learn` text station)
from `wip/20260814-1to1-text-unproven`. Still no AIRI, ASR, or extra MCP tools.
