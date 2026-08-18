# The teaching loop — workflow and failure doctrine

**Date:** 2026-08-18
**Governed by:** [NORTH-STAR.md](../NORTH-STAR.md) §2 *The working day*
**Decisions:** [room runs itself](../decisions/2026-08-18-room-runs-itself.md) ·
[teacher, not cassette](../decisions/teacher-agent-not-cassette.md) ·
[skills](../decisions/2026-08-18-teacher-skills.md) ·
[three stores](../decisions/2026-08-18-three-stores.md)

This document is the **workflow**: what happens, in order, who acts, and what
happens when each part breaks. It is the operational reading of the north star.

---

## 1. The whole loop

```
        ┌──────────────────────── the day ────────────────────────┐
        │                                                          │
   [power on]                                                      │
        │                                                          │
        ▼                                                          │
   ┌─────────┐   timetable says a period is near                   │
   │ PREPARE │◄──────────────────────────────────────┐             │
   └────┬────┘   read roster + evidence + unit map   │             │
        │        stage the material. Nobody present  │             │
        ▼                                            │             │
   ┌─────────┐   Stage holds the audio lease         │             │
   │  READY  │   Hermes up · speech up               │             │
   └────┬────┘   board shows the room is awake       │             │
        │                                            │             │
        │  presence                                  │             │
        ▼                                            │             │
   ┌─────────┐   [sat_down] — she greets and opens   │             │
   │  OPEN   │                                       │             │
   └────┬────┘                                       │             │
        │                                            │             │
        ▼                                            │             │
   ┌──────────────────────────────┐                  │             │
   │          THE PERIOD          │                  │             │
   │                              │                  │             │
   │  child acts ──┐              │                  │             │
   │               ├──► one turn  │                  │             │
   │  silence ─────┘              │                  │             │
   │       (pulse, ≥45s)          │                  │             │
   └──────────────┬───────────────┘                  │             │
                  │ EXIT met, or time is up          │             │
                  ▼                                  │             │
             ┌─────────┐                             │             │
             │  CLOSE  │  she ends it herself        │             │
             └────┬────┘                             │             │
                  │                                  │             │
                  ▼                                  │             │
             ┌─────────┐  evidence → observations    │             │
             │  AFTER  │  session summary            │             │
             └────┬────┘                             │             │
                  └──────────────────────────────────┘             │
                                                                   │
        └──────────────────────────────────────────────────────────┘
```

Three of these boxes — `PREPARE`, `READY`→`OPEN` without a button, and `CLOSE` —
are the work of Layer 4. `THE PERIOD` and `AFTER` exist today.

---

## 2. One turn, in full

A turn is the atom. Everything else schedules turns.

```
trigger                 what Core does                        what she does
───────────────────────────────────────────────────────────────────────────────
child speaks       ──►  ASR → text                       ──►  reads the turn:
  or                    build TurnContext:                    UNIT, STUDENT_SAID,
room goes quiet         · unit + board state                  WRITING, IMAGES,
  (pulse ≥45s)          · SKILL_CARD + PAST (this learner)    LAST_SAY, SKILL_CARD,
  or                    · BEATS (last teaching moves)         PAST, BEATS, READS,
timetable fires         · skills index (tier 0)               skills index
                        register turn_id → TeacherOS
                        (TTL 60s, student-scoped)
                                  │
                                  ▼
                        Hermes: POST /v1/responses
                        stateless, stream, store:false
                        tool_choice: required
                        ≤ 8 iterations
                                  │
                        ┌─────────┴─────────┐
                        │  she calls tools  │
                        └─────────┬─────────┘
                                  │
     read_library / search_library ──► open a skill, the unit map, the keys
     write_board / read_board      ──► chalk on the board, and check what is there
     show_image / play_clip        ──► asset:// only; Core resolves it or refuses
     record_evidence               ──► one categorical fact, this turn
     say                           ──► ONE line. THIS ENDS THE TURN.
                                  │
                                  ▼
                        Core validates every call, may refuse,
                        publishes scene.update + speech
                                  │
                                  ▼
                        Stage: board redraws, Piper speaks,
                        Live2D mouth follows the audio
```

**`say` is the terminal tool.** The loop exits when she speaks — enforced in the
Hermes patch, not by convention. That is what makes a turn bounded: she can look
things up as much as eight iterations allow, but she leaves the turn by saying
one thing to a child.

### The board

The board is the shared surface, and it is hers:

| Tool | What it does | What Core refuses |
|---|---|---|
| `write_board` | short chalk markdown — headings, lists, emphasis | HTML, URLs, >400 chars, >8 lines, and **anything evaluative** (`✓`, `correct`, `well done`) |
| `read_board` | what is currently on it | — |
| `show_image` | one picture, or two side by side | anything that is not an `asset://` id that resolves to a real file |
| `play_clip` | an audio clip with its transcript | same |

The refusal of tick marks and "correct" is deliberate. **The board holds the
language, not a score.** Judgement lives in `record_evidence`, where it is
private, categorical, and attached to a learner — not chalked up in front of
thirty children.

`read_board` before `close` is a required habit, not a nicety: she should look at
what the room can actually see before she says goodbye to it.

---

## 3. Failure doctrine

The governing sentence, from NS-1:

> **If the AI is down, teaching pauses and the AI restarts.
> Nothing impersonates her.**

There is no cassette, no authored fallback, no "Core takes over for a bit". A
system that quietly substitutes something worse is a system nobody can trust,
because the failure is invisible exactly when it matters.

### What breaks, and what happens

| Failure | Detected by | The room | The adult sees | Recovery |
|---|---|---|---|---|
| **A tool call is illegal** — bad asset, off-map objective, evaluative board text | Core, synchronously | nothing changes | nothing | `{ok:false, reason}` goes back to her *inside the same turn*. She corrects and continues. This is not an incident |
| **She never says anything** in 8 iterations | Core, end of turn | board unchanged, silence | fault on `/teacher/status` | retry once. Then it is a model fault |
| **Hermes slow** | turn timeout | last board and last line stay up | "thinking" | the pulse will not overlap — one turn at a time |
| **Hermes dead** | `/health` probe, per pulse | **the room stays exactly as it is** — board, session, last visual | `phase: fault`, honest message | restart the sidecar; resume from the OS snapshot. Do not restart the *period* |
| **Provider 429 / rate limit** | turn error | as above | as above | do not retry into the limit. One model slot exists; the pulse defers |
| **Speech service dead** | `/health` probe | board still works; she is mute | `speechUp: false` | restart. A silent teacher with a working board is degraded, not dead |
| **Stage disconnects** (projector, browser) | audio lease expires | session survives in Core | lease lost | on reconnect the server sends a full snapshot; the Stage redraws |
| **Power cut mid-period** | — | — | — | **release gate, not met:** Core must restore the open session and resume the period, not start a new one |
| **ASR returns nonsense** on a <600 ms clip | length guard | discard | — | never send it to her. Whisper invents words on short clips |
| **Identity uncertain** | perception confidence | teaching continues | — | **no evidence write.** Losing a data point is cheap; attributing it to the wrong child is not |

### The three rules underneath the table

1. **The room outlives the brain.** Board, session, sockets and the last visual
   are Core's, and they survive a model that is dead, slow, or restarting. A
   child looking at the screen should not be able to tell the difference for the
   first few seconds.

2. **Tell the truth, immediately.** The adult console shows the real state. We
   have already been burned by a console reporting a healthy agent while it was
   dead, and by an SVG face standing in for a Live2D model that had failed to
   load for an entire session. **A visible failure is a feature; a papered-over
   one is a defect.**

3. **Restart the teacher, never the lesson.** Resuming means: same session, same
   unit, same objective, same board, same evidence. She picks up. She does not
   greet the class again as though nothing happened — that is the tell that
   something is a machine.

### What "restart and carry on teaching" actually requires

This is the part not yet built, stated concretely:

```
fault detected
   → adult is told (console, and a quiet fault banner on the Stage)
   → Core keeps: session row, unit, objective, board contents, evidence
   → sidecar restarted (supervised, bounded attempts)
   → health returns
   → next turn is built from the SAME OS snapshot
   → she resumes mid-period, with a one-line reorientation, not a greeting
```

The gap: NS-5 says durable state lives in the database, and Core does persist a
checkpoint — but **startup restore is not implemented**. Until it is, a Core
restart loses the period. That is the single most important reliability gate
before a classroom release, and it is more important than any feature.

---

## 4. Invariants a reviewer can check

Any change that breaks one of these is wrong, regardless of what it improves:

| # | Invariant |
|---|---|
| 1 | No adult decision sits on the teaching path — including a button to begin |
| 2 | Core never chooses what to teach next |
| 3 | Nothing plays a recorded lesson when the model is unavailable |
| 4 | `say` ends the turn; a turn is bounded |
| 5 | Every asset reaching the Stage is an `asset://` id Core resolved |
| 6 | The board never displays a grade |
| 7 | Evidence is categorical, tied to an objective printed in the active unit |
| 8 | No raw child utterance is written to durable storage |
| 9 | Uncertain identity ⇒ no student-memory write |
| 10 | Retrieval scopes to one `student_id` **before** it ranks anything |
| 11 | The Stage is the only loudspeaker |
| 12 | A failure is visible within one pulse |
