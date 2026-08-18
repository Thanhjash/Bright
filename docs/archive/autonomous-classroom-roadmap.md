# Execution roadmap — teacher agent first

**Updated:** 2026-08-18  

**Authority:** current execution order  
**Bible:** [north-star.md](../NORTH-STAR.md)  
**Correction:** [teacher-agent-not-cassette.md](../decisions/teacher-agent-not-cassette.md)

This file replaces the 2026-08-16 *teacher-loop-first* order that treated a
1-tool wire probe and a `lesson_run.json` graph as the teacher. Destination
is unchanged: one autonomous AI teacher for 20–40 children, later offline.
The teacher is an **agent**, not a cassette.

---

## Do not re-bias

Future agents (and tired humans) will want to put the graph back. Don't.

| Temptation | Why it is wrong |
|---|---|
| “Lesson must run when the LLM is dead” via `lesson_run.json` | That makes Core the teacher. Owner rejected it. Fail → notify + restart AI |
| Layer 1 = 10/10 `classroom_propose_move` | That proved a wire, not a teacher |
| Adaptive = pick `goto:apple_scaffold` | Hardcoded unit workflow. Dies when we add subjects |
| One live MCP tool forever | Then we did not need Hermes |
| Extra Hermes `display_image(path)` / filesystem | Teammate soup. Library tools return `asset://` ids |
| Chatbot + face + llama.cpp | Anti-pattern. Agent teaches; AIRI is a body |

---

## Destination (unchanged)

An autonomous teaching system that remembers learners, drives one shared
board, and adapts from what they actually do. Adult boots the room. The AI
is the teacher.

1:1 text is only the cheap **channel** to prove the agent. It is not a
chat product and not a fork.

---

## Locked sequence

```text
0  Classroom OS floor     bus, session, board I/O, semantic DB
1  Teacher agent (text)   Hermes reads the library and teaches one learner
2  Thin station           /learn is a mouth + eyes, not a second brain
3  Voice                  TTS of say(), then Bright ASR
4  Body                   AIRI lipsync on Stage
5  Classroom              20–40, fairness
6  Local mind             Gemma 4 behind the same Hermes tools
7  Giveaway               consent, licences, appliance, locale
```

Hosted model now. Local Gemma later. Same OS, same library, same tools.

---

## Who owns what

```text
curriculum md + maps + assets + keys     library (codebase)
Hermes sidecar                           teacher (coding-agent analog)
Bright MCP tools                         hands
Classroom Core                           OS (I/O, clock, DB, restart)
Stage                                    board / speaker
AIRI                                     body only
```

General teaching loop (every subject):

1. Observe student act (text now, speech later)
2. Evaluate against the active objective / rubric
3. Retrieve more library only if needed
4. Present + say
5. Record evidence (facts, not chat)
6. Open the next response window

Sidecar crash → notify + restart is OS hygiene. It is not a layer and
not the next cook.

---

## Layers and exit gates

### Layer 0 — Classroom OS (keep; strip the cassette)

Keep: protocol v3, session, bus, Stage I/O, semantic DB, Hermes sidecar
process, MCP auth.

Stop treating as product: `lesson_run.json` as the teacher, authored-tape
fallback, Core-computed `available_actions[]` as pedagogy.

Exit: a script can drive board + say + persist evidence **without** walking
a Market Food graph.

### Layer 1 — Teacher agent  **CLOSED 2026-08-17 (text 1:1)**

**Old claim (FALSE):** 10/10 live `classroom_propose_move` = teacher brain.
That is a **harness smoke test**. Keep the pin as plumbing.

**Real Layer 1 (met):** Hermes, with library tools, teaches one concept to one
learner in text. It reads a map, goes deeper when needed, talks, presents
an asset, records evidence. No `if wrong goto X`. Live chats
(`minh-show` / `minh-c3`) closed the gate. Memory lock:
[layer-1-memory-is-enough.md](../decisions/layer-1-memory-is-enough.md).

How we will know:

```text
child says something off-script (not only "banana")
  → agent reads unit map / key if it must
  → agent answers as a teacher
  → optional present(asset://…)
  → record_evidence is categorical
```

Non-goals: voice, AIRI, 20–40, new Node product surface, generic FS tools.

### Layer 2 — Thin station  **exit met — do not polish as a product**

`/learn` renders what the agent presented and ships learner text to Core.
It does not grade or invent a reply.

Exit: one child finishes a short unit through the station with no adult
teaching decision. That happened. Ugly UI is accepted. Do not grow
`/learn` into a chat product.

### Layer 3 — Voice  **CLOSED 2026-08-18**

`say` is audible on Stage (Piper). `/learn` Hold-to-talk is Whisper →
`/teacher/turn`. Not Hermes voice tools. Not AIRI’s streaming server.

### Layer 4 — AIRI body + Stage as a real room  **NOW (demo bar)**

Body is `airi-bridge` on `/classroom` (same SpeechPlayer). Hiyori mouth
proven. Do **not** mount AIRI `stage-web` / `core-agent` as a second app.

**2026-08-18:** `/classroom` is the room. `/learn` is a leftover mouth.
Start + Hold-to-talk was a misread — owner wants **no product buttons**;
heartbeat opens class (OpenClaw shape, not the WS ping). RoomDock is
temporary chrome. Handoff: [HANDOFF.md](HANDOFF.md).

Still missing for a competition room:

- Hiyori reliably on the judge’s Chrome (unpacked model; not the 33 MB zip)
- Character reads as a person in the room (scale, light, lipsync). Swap
  model if Hiyori is too toy — demo first, licence later (Layer 7)
- Heartbeat prompt quality (does she actually look up after silence?)

### Layer 5 — Classroom 20–40 + who is speaking

Same agent. Fairness and named callouts. Camera / face / voice embedding
only binds `student_id` after consent — it does **not** invent memory
(NS-5). Detector never on the projector.

### Layer 6 — Local Gemma

Change Hermes provider/model/base_url. Re-run Layer 1–3 gates. Do not
narrow tools back to `propose_move` “because E4B is weak” — tighten
schemas and reject invalid tool args instead.

### Layer 7 — Giveaway

Consent, licences, locale-as-config, appliance. Unchanged.

---

## First unit (library, not a rail)

Keep the teammate Global Success / Market Food **curriculum** (locked
vocab, TBLT intent, local assets, no ranking).

Store it as:

```text
content/library/
  index.md                 map of units
  units/market-food/map.md objectives, vocab, pointers
  units/market-food/*.md   tasks, rubrics, keys
  assets/                  asset://… only
```

Do not compile that into a graph the agent must walk. A `lesson_run.json`
left on disk is a historical artifact, not the live teacher.

---

## Explicitly out of the current critical path

- Growing `/learn` into a chat product
- AIRI polish, face boxes
- Restoring authored-tape fallback
- Calling the 10/10 probe “reliability completed”
- Auth / SBOM / licences as a substitute for a teacher
- Per-unit Core state machines

---

## Next action

**Layer 4 autonomy, not more chrome.** Stage lease + Hermes up → Core
wakes the teacher (`[sat_down]`). Room listens when she is silent. No
Start / Hold contract. Same 8 tools. Do not deepen Store B. Do not run
AIRI as a second brain.

Paste: [HANDOFF.md](HANDOFF.md)
