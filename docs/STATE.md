# STATE — the one living document

**Updated:** 2026-08-18
**This file is the only living execution doc.** It replaces the former
`HANDOFF.md`, `autonomous-classroom-roadmap.md` and `teacher-agent-status.md`,
all three of which now sit in [`archive/`](archive/).

**Paste this file into a new agent chat.** Nothing else is required reading.

---

## 0. What Bright is, in one paragraph

An autonomous AI English teacher for remote, under-resourced classrooms, meant
to be **given away**. Hermes is the teacher — a coding-agent-shaped harness with
a curriculum library instead of a repo. Classroom Core is the room's operating
system: I/O, clock, database, safety, restart. It never teaches. When the AI
dies, the room stays up, the adult is told, and the AI restarts. **There is no
lesson tape.**

Bar for "done": **switch it on and it teaches.**

---

## 1. Read order

| # | File | Why |
|---|---|---|
| 1 | [NORTH-STAR.md](NORTH-STAR.md) | The bible. NS-1…NS-5. If anything contradicts it, it loses. |
| 2 | [decisions/teacher-agent-not-cassette.md](decisions/teacher-agent-not-cassette.md) | Hermes = teacher, Core = OS, fail → notify + restart |
| 3 | [decisions/2026-08-18-room-runs-itself.md](decisions/2026-08-18-room-runs-itself.md) | No product buttons. The pulse opens the class |
| 4 | [decisions/2026-08-18-three-stores.md](decisions/2026-08-18-three-stores.md) | Storage direction + the kill list |
| 5 | **This file** | What is actually wired, and what to do next |

Only if the task touches that area:

| Touching | Read |
|---|---|
| Ports, Hermes sidecar, privacy | [decisions/option-b-classroom-runtime.md](decisions/option-b-classroom-runtime.md) |
| Why not OpenClaw | [decisions/hermes-over-openclaw.md](decisions/hermes-over-openclaw.md) |
| Stage, two screens | [design/runtime-topology.md](design/runtime-topology.md) |
| The workflow + what happens when it breaks | [design/teaching-loop.md](design/teaching-loop.md) |
| Adding or changing a tool | [design/tool-surface.md](design/tool-surface.md) |
| Tools, bus, ownership | [design/architecture.md](design/architecture.md) |
| AIRI attach | [design/reusing-airi-and-friends.md](design/reusing-airi-and-friends.md) + `packages/airi-bridge/` |
| Wire protocol, seq, speech frames | [`packages/contracts/PROTOCOL.md`](../packages/contracts/PROTOCOL.md) |
| Curriculum on disk | `content/library/` + `content/README.md` |

Everything in [`archive/`](archive/) is historical. It is kept for provenance,
not for instruction. Never cook from it.

---

## 2. Who owns what

```text
content/library/       curriculum — index, conduct, skills, units
content/media/         asset://… images + clips
Hermes sidecar :8642   the teacher
Bright MCP             her hands — 9 typed tools
classroom-core :8004   the OS — I/O, clock, DB, reject, restart
Stage /classroom       THE room. Board + speaker + body. The only page children see
packages/airi-bridge   the body (Live2D + lipsync) — nothing else
speech :8001           Piper TTS + faster-whisper ASR
/control               adult console, separate tab. Never on the projector,
                       never makes a teaching move
```

**The nine live tools.** Do not add a tenth without a decision doc.
[Why exactly these nine.](decisions/2026-08-18-show-exercise-tool.md)

```
read_library  search_library  write_board    read_board
show_image    show_exercise   play_clip      say
record_evidence
```

`present` and `open_response` appear in older docs and in a compatibility branch
of `teacher_os.execute`. They are **not** the live surface — `write_board` and
`show_image` replaced `present` on the wire.

**Memory shape.** SQL `observations` (with `mode ∈ name|point|ask`) →
`SKILL_CARD` + `PAST` on every turn, scoped to one `student_id` across all
sessions. RAM `BEATS` is the last 8 teaching beats. Raw child words appear only
as `STUDENT_SAID` for the current turn (NS-5). No raw child speech in SQL.

---

## 3. Layer status — honest

| Layer | Status | Truth |
|---|---|---|
| 0 OS | ✅ | bus, session, DB, leases. **The cassette was deleted 2026-08-18** — see §3c |
| 1 Teacher text | ✅ closed 2026-08-17 | Hermes + library teaches 1:1. Live chats `minh-show` / `minh-c3` |
| 2 Thin station | ⬛ removed | `/learn` was deleted 2026-08-18. One page: `/classroom` |
| 3 Voice | ✅ wiring closed 2026-08-18 | Stage speaks `say` via Piper; ASR → `/teacher/turn`. Piper picks en/vi **per line by script**, which is not real bilingual — see §7 |
| 4 Body + room | 🔴 **NOW** | Live2D + wall + board on Stage: done. **Autonomy: not done.** RoomDock buttons survive only until the presence gate replaces them |
| 5 Class of 20–40 | ⬜ | fairness, camera → `student_id` only |
| 6 Local Gemma | ⬜ | swap the Hermes provider profile. Hosted MiMo now, **max 1 concurrent turn** (429 on overlap) |
| 7 Giveaway | ⬜ | Hiyori licence, locale-as-config, consent, appliance image |

---

## 3b. The gap, stated as the north star states it

[NORTH-STAR.md](NORTH-STAR.md) §2 models the teacher's **working day**.
**Updated 2026-08-19 — four of five boxes now exist:**

```
BEFORE      prepare for a period nobody has arrived at yet     ❌ absent
ARRIVAL     notice a person, greet them                        ✅ presence gate
THE PERIOD  open, teach, judge, adapt, pace, close             ✅ turn loop + rhythm
CLOSE       end it herself, on time                            ✅ say(closing)
AFTER       write up evidence; it changes next time            ✅ evidence writes
```

Only **BEFORE** is missing, and it is missing for one reason: nothing in the
system knows when a class is. That is the day clock below, not a gap in the
teaching loop.

Within THE PERIOD, the rhythm is no longer a single constant: she waits ~7s
after asking (one nudge, then the long floor), reads PERIOD_MINUTES to judge
when time is up, and an interrupted period resumes instead of restarting.

And one of three clocks is missing entirely:

| Clock | Owner | State |
|---|---|---|
| Reflex < 100 ms | Core | ✅ |
| Turn, seconds | `pulse_teacher` | ✅ built and **already running** |
| **Day, minutes → hours** | `scheduler.py` | ⚠️ the socket is wired; **nothing is plugged into it**. This is the last missing clock, and it is what BEFORE needs |

### How close this actually is — traced 2026-08-18

The autonomy gap is far smaller than it looks. Three of the four pieces already
run with no human involved:

| Piece | Evidence |
|---|---|
| **Presence is already sensed** | `BusProvider.tsx:41-58` sends `capability.report` automatically on WS connect and every 4 s. Core grants the stage-audio lease with no click. Kiosk loads `/classroom` by itself (`infra/kiosk/kiosk.sh:12`) |
| **The pulse already runs** | `app.py:686-688` starts `teacher_heartbeat_loop` unconditionally on every Core boot — no env flag. It ticks every 10 s forever (`teacher_os.py:675-684`) |
| **The pulse already knows how to stay quiet** | `pulse_teacher` returns `HEARTBEAT_OK` without spending a model turn unless silence ≥ 45 s and ≥ 20 s since the last pulse (`teacher_os.py:634-672`) |
| **A day-clock socket already exists** | `scheduler.py:108-114` runs a `prepare_next` cron at 03:00 via APScheduler — and it calls `AgentSeam.prepare_next`, which is **a no-op by default** (`scheduler.py:43-53`). The hook was built and never filled |

**The single blocker:** `start_teacher_session()` has exactly one caller —
`POST /teacher/session` (`app.py:747-755`) — and the only thing that sends that
request in the kiosk path is the `Start class` button
(`RoomDock.tsx:100`, `onClick` at line 242).

So the pulse ticks every 10 s next to a room that has already reported presence,
and does nothing, because no session exists and only a human click can create
one. Closing that is roughly: *if no session, and the stage lease is held, and
Hermes and speech are up → open the session and fire `[sat_down]` yourself.*

The rest of Layer 4 autonomy — open-mic instead of hold-to-talk — is genuinely
new work: `micRecorder.ts` is strictly press/release, and `captureEndpoint.ts:4`
explicitly disclaims being VAD. **No VAD exists anywhere.**

---

## 3c. The cassette is gone — 2026-08-18

Core used to load **two teachers into one process**. `app.py` constructed a
`LessonRunner` + `ClassSessionController` whenever a `lesson_run.json` happened
to exist on disk — and one did. Both held `publish_speech` and wrote to the same
bus and store as the teacher agent. `BRIGHT_AGENT` gated only the *agent
adapter*, never Core. Nothing switched between them.

Deleted:

| | Lines |
|---|---|
| `runner.py` · `class_session.py` · `agent_bridge.py` · `sample_lesson_run.json` | 4,711 |
| cassette tests (`test_runner`, `test_class_session`, `test_drag`, `test_immediate_response`, `test_agent_turns`, `test_memory_loop`) | 1,733 |
| `bright_agent/scripted.py` | 547 |
| root `tests/` integration suite (18 files) + `harness/` + `fixtures/` | — |
| `tools/lesson-{compile,lint,play}` · `content/lessons/` · `plans/` | — |
| 8 cassette scripts (`ideal-hosted`, `product-smoke`, `composed-smoke`, …) | — |
| `routes/learn/` · `useVoiceInput` · `captureEndpoint` · `answerStationActivity` · `VoicePanel` · `ListeningIndicator` | — |

`app.py` 1,600 → 1,053 lines. `CapabilityLeaseRegistry` survived, extracted to
`leases.py` — the Stage still must claim the audio lease before Piper speaks.
`BRIGHT_AGENT` now means `hermes` or off.

**Kept deliberately:** `bright_agent/direct.py`. It is not in Core's boot path —
Core only ever constructs `HermesAgent` — but the SP-3 model-evaluation suite
(~2,500 lines, the NS-4 asset that tells us which models are usable) is built on
it. Deleting it means deleting the evals. Not cassette; revisit separately.

### What the removal cost, and what was restored

- **The health probe.** `build_agent_seam` lived in `agent_bridge.py` and was
  not cassette — it supplied `AgentSeam.probe`, which drives `ModeController`.
  Without it the mode never leaves OFFLINE. **Restored** in `app.py` as a
  latency probe against the Hermes sidecar. It measures the process, never the
  model's answer — a probe that spent a turn would compete with the teacher for
  the single hosted slot.
- **The 30-s post-session summariser.** Also lost with `build_agent_seam`. Not
  restored: `teacher_os._close_open_teacher_sessions` already writes a summary
  when the next session opens, so the memory loop survives. The scheduled write
  does not. Note it before relying on same-day summaries.
- **Barge-in cannot succeed** for teacher speech, and could not before either —
  `publish_speech` registers scope `(None, None)` while the payload requires a
  non-empty `activityId`. Pre-existing; barge-in is a non-goal (half-duplex).
- **`config.py` still carries dead settings** with no reader: `lesson_run_path`,
  `autostart_lesson`, `silence_timeout_s`, `reveal_hold_s`,
  `speech_correct_confidence`, `capture_ready_timeout_s`,
  `playback_ack_timeout_s`. Harmless; clean when convenient.

**Tests: 274 → 111 in classroom-core** (the drop is the deleted cassette suite),
91 + 4 skipped in agent, UI typecheck clean.

---

## 3d. She teaches — proved live 2026-08-18

Run end to end against a real Chromium on `/classroom` holding the audio lease.
Nothing in code knew which lesson it was; `library.list_units()` discovers units
on disk and `app.py` no longer names one.

```
reads   how-to-teach.md -> skills/index.md -> units/gs3-u1-hello/map.md
        -> skills/open-a-period/SKILL.md -> index.md -> exercises.md
board   "## Hello, I'm..."  rendered as chalk, not literal ## and **
image   asset://gs3/panels/u1l1-dialogue-a.jpg   GET /assets/... 200
audio   asset://gs3/audio/track-05.mp3           GET /assets/... 200 (real
        recording, not TTS reading a transcript)
speech  POST /audio/speech 200 -> Piper -> Live2D ParamMouthOpenY
choice  "Which pair is speaking?" with the two ex.4 panels, no grade on the board
evidence greet-and-name / correct / mode=name, with a validated student_id
```

Screenshots in `tests/.artifacts/board-*.png`. Rehearsal harness:
`scripts/rehearse-lesson.sh` (it sends only things a child would say -- no stage
directions, so a pass means she chose the moves).

### What this cost to get working, and why

Four defects that no unit test could have caught, because all four are about
time or ordering:

| | |
|---|---|
| **`turn_id` TTL was 60 s** | The hosted model takes ~175 s to its first tool call. The token expired before she used it, every tool came back `unknown or expired turn_id`, the turn died mid-stream, and the provider's single run stayed open -- so the NEXT turn got 429. Now 900 s. The registry still scopes every call to session + learner, and the turn is retired explicitly, so a long TTL costs nothing |
| **`HERMES_API_TIMEOUT_S` was 60 s** | Same failure from the client side. Now 300 s |
| **The board ranked sources instead of honouring recency** | `last_images` / `last_exercise` persist across turns so `read_board` can report them. Under a fixed ranking a picture shown minutes earlier beat writing she had just chalked, and **her writing never reached the projector.** `_push_stage` now follows the last hand that touched the board |
| **A refusal she could not act on cost her the whole move** | Observed live: she reached for `show_exercise`, was told only `correct_id must equal one option id`, could not fix it, and fell back to talking. Refusals must name the legal values |

### Latency — the real risk, and it is not our code

`token-plan-sgp.xiaomimimo.com` stalls. Hermes logs
`Stream stale for 180s -- no chunks received. Killing connection`, then retries.
She only makes ~3 model calls per turn (`api_calls=3/8`), so batching tool calls
is not the lever.

```
turn 1 (cold)   8m01
turn 2          4m56
turn 3          3m14
turn 4          0m49    <- prompt cache warm
turn 5          1m21
```

It warms up to roughly a minute. **Moving off the token-plan tier is the single
biggest remaining improvement, and it is a purchasing decision, not a code
change.** Do not spend engineering time on turn latency before that is settled.

## 3e. The brain, the rhythm and the record — 2026-08-19

### The brain moved twice, by measurement

MiMo (hosted, token-plan) stalled 180s at a time and wrote Han characters onto
the projector. DeepSeek was faster and wrote pinyin instead. Both are
Chinese-trained; the script guard caught both, and every catch costs a whole
round-trip, so the leak was a latency bug as well as a safety one.

Benchmarked with the **real** harness prompt and all nine tool schemas, five
calls each:

```
model                          p50      p95   tools/msg  turn_id ok
google/gemini-3.7-flash       1.85s    8.68s      6.6      5/5   <- shipped
deepseek/deepseek-v4-flash   16.89s   29.80s      5.8      5/5
google/gemini-2.5-flash-lite 20.04s   66.55s      2.2      2/5
openai/gpt-5-nano                 —        —        —        —   reasoning mandatory
```

Teaching turns: **48–92s → 11–28s**, 2–3 round-trips instead of 3–8, zero
Chinese across ten bilingual turns. Provider variance is wide; 11s was a good
run, not the number to quote.

**Gemini is a bridge, not the destination.** The endgame is Gemma on the
appliance. Nothing in the tree may assume this provider.

### Prompt-cache injection: built, measured, rejected

Handing her `how-to-teach.md` + `skills/index.md` + the active map instead of
spending a round-trip reading them is sound in principle — a coding agent does
not `read_file` its own CLAUDE.md every session. It rests entirely on the
prefix being cached.

**It is not.** Three identical 4,163-token requests to gemini-3.7-flash through
OpenRouter each reported `cached_tokens: 0`. The injection cost ~2,400 tokens
on every call and bought back one round-trip once: turns went 41/11/14s →
46/38/27s. Removed the same day.

This is a fact about **one provider**. llama.cpp and OVMS keep a prefix KV
cache, so the idea may well win on local Gemma — where round-trips are CPU we
own and worth more, not less. Before rebuilding it, confirm
`cached_tokens` is non-zero on a repeat call. The reasoning is kept where the
code would have gone (`teacher_os.py`).

### The four-condition ASR bake-off the research asked for

One concatenated clip, "This is a banana. Chuối. This is a banana.":

| condition | transcript | time |
|---|---|---|
| auto / our clamp | "This is a banana. **Joy**, this is a banana." | 2.9–3.9 s |
| forced `en` | identical | **2.0 s** |
| forced `vi` | "Tại sao? Tại sao?" — English lost | 4.4 s |

The clamp costs ~1s for a detection pass and buys nothing measurable here. It
is retained only against the failure it was built for — a Vietnamese clip
decoded as Spanish — and is a candidate for removal once a real corpus exists.
Mixed recognition fails under every policy: "Chuối" became "Joy" every time.
Concatenated Piper audio is not a person code-switching; indicative only.

**Corrected doctrine:** our own brief claimed a mid-sentence switch "cannot be
transcribed correctly by construction". That is wrong. The language token
conditions decoding; it is not a vocabulary gate.

### The lesson has a rhythm now

- **Wait like a teacher.** The map says "four seconds of wait after a
  question"; the system waited 45. `say(awaiting_answer)` gives one nudge at
  ~7s, then the long floor. She sets it — Core does not guess from a question
  mark, because "Now you try" expects an answer and carries no "?".
- **She closes her own period.** `say(closing)` ends the session after the
  goodbye is spoken. There was no way to end one before, which is why the live
  database holds 33 sessions nobody closed. The room then refuses to reopen for
  ten minutes, or she would greet the same class three seconds later forever.
- **An interrupted period resumes.** The presence gate re-attaches to an open
  session and fires `[heartbeat]`, not `[sat_down]` — she looks up rather than
  greeting a class she is already teaching. Bounded to two hours: longer than a
  period, shorter than overnight, because a session left open on Tuesday is
  abandoned, not interrupted. (`session_checkpoints` was the obvious home for
  this and is a dead end — `save_session_checkpoint` has no callers at all.)

## 4. Roadmap to a complete demo

**The bar:** a judge walks up to a machine nobody is touching, and watches a
teacher teach. Not a scripted run. **Nothing in code may know which lesson it
is.**

Ordered by value, so it can be cut at any line and what remains is still
coherent. Estimates are working days for one focused person; the three tracks in
§4.6 run in parallel.

### 4.1 P0 — Pay the debt that blocks curriculum  ·  0.5 day

Both are contract-shaped: they get more expensive with every unit authored.

| | |
|---|---|
| **`record_evidence` gains `student_id`** | MCP schema + `teacher_os.execute` + PROTOCOL + turn prompt. One constant learner today — the point is that the *shape* is right |
| **Delete the confidence number** | `_name_skill_stats` reaches 1.0 at four attempts. Replace with coverage counts in `SKILL_CARD`: supported / contradicted / no_decision, dates, elicitation seen |

*Gate:* evidence rows name their subject; nothing in the tree claims certainty
from four observations.

### 4.2 P1 — She starts by herself  ·  **DONE 2026-08-18**

Proved live: the stack was restarted, a browser opened `/classroom`, and
**nothing else was touched** -- no button, no `POST /teacher/session`. Within
one pulse she opened the class, greeted the room, and continued the unit:

> "Hello again! You say \"Hello, I'm [name]\" so well. Now listen -- Ben says
> \"Hello, I'm Ben.\" Then Mai says \"Hi, Ben. I'm Mai.\" She uses Ben's name!"

She resumed from the previous session's evidence and moved to the next
objective (`answer-a-greeting`) on her own.

- `teacher_os._open_on_presence()` -- the gate. **The cheap local lease check
  runs first**, so an empty room never costs a health probe, let alone a turn.
- Core still refuses to pick a lesson: it opens only when `list_units()`
  returns exactly one. Several authored units means an adult chooses (NS-7).
- The Start pill is gone from `RoomDock`; the dock is a status chip now.
- Tests: `test_pulse_opens_the_class_when_the_room_is_there`,
  `test_pulse_will_not_open_a_class_into_a_dark_room`.

*(original plan below)*

### 4.2b P1 — the original plan  ·  1 day

Everything needed already runs. The Stage announces presence every 4 s
(`BusProvider.tsx:41-58`); the pulse ticks every 10 s (`app.py:686-688`). The
only reason nothing happens is that `start_teacher_session()` has one caller —
the button.

- Presence gate inside `pulse_teacher`: *no session · stage lease held · Hermes
  up · speech up* → open the session and fire `[sat_down]`.
- Remove the Start pill. `RoomDock` keeps only a fault banner and a fading
  "I heard …" chip.
- One audio-unlock gesture at kiosk boot, by the adult, once.

*Gate:* power on, touch nothing, she greets the room.

### 4.3 P2 — The room listens  ·  **DONE 2026-08-18**

`apps/classroom-ui/src/speech/voiceGate.ts` — energy VAD with an adaptive
ambient floor, hysteresis, and endpointing on 800 ms of trailing silence.
`RoomDock` has no microphone button any more; hold-to-talk is deleted.

- **One microphone stream.** The gate is handed the `MicRecorder` the page
  already owns and drives it; it never calls `getUserMedia` itself.
- **Half-duplex.** It never opens while `avatar.speaking` is true, and abandons
  a capture in flight if she starts talking, with a 400 ms trailing guard for
  reverb. Otherwise Piper's output feeds back into Whisper and she answers
  herself.
- Clips under 600 ms are discarded (Whisper invents words on them); clips are
  capped at 15 s.
- Test: `tests/node/voice_gate_playwright.mjs`, driving Chromium with
  `--use-file-for-fake-audio-capture`. Gated pass produced 0 clips despite loud
  speech; ungated pass produced exactly one clip of the right length, 3/3 runs.

**Validated against synthetic Piper audio, not against children in a room.**
Clean TTS cannot separate a good VAD from a mediocre one. `OPEN_MULTIPLIER`,
`CLOSE_MULTIPLIER` and `FLOOR_ADAPT_RATE` are unproven and will need retuning
on real classroom audio. Say so in the submission rather than implying
otherwise.

### 4.3b P2 — the original plan  ·  1.5 days

No VAD exists anywhere. `micRecorder.ts` is press/release; `captureEndpoint.ts:4`
explicitly disclaims being VAD.

- Energy VAD + endpointing, open **only while she is not speaking** (half-duplex
  — the Stage is the only loudspeaker).
- Discard clips under ~600 ms; Whisper invents words on them.
- Barge-in is explicitly out of scope.

*Gate:* a child speaks with no button, in a real room with real noise, and she
answers. Measured, not assumed.

### 4.4 P3 — She finishes, and survives  ·  1.5 days

- **Close the period herself.** Exit detection from evidence coverage plus a
  period budget, using the `close-a-period` skill. She ends on time whether or
  not the material is finished.
- **Resume after a restart.** `session_checkpoints` is written and never read at
  startup (`db.py:112,423,453`; nothing in `app.py` lifespan calls it). Core must
  find the open session and resume the period — same unit, same objective, same
  board — **not greet the class again.** Re-greeting is the tell that it is a
  machine.
- **Honest faults.** `/control` shows real state; sidecar restarts; the room
  stays up.

*Gate:* kill Hermes mid-lesson → honest banner → restart → she continues the same
period. Then pull the power and repeat.

### 4.5 P4 — Prove it is an agent  ·  1 day

This is the phase that answers *"is this hardcoded?"* — and it is the one most
likely to be skipped under pressure. Do not skip it.

- **A second unit, authored from the same textbook, with zero code change.**
  We hold 80 pages and 108 tracks. Extend `test_no_unit_pedagogy` so the claim is
  enforced, not asserted.
- **Let the judge choose the unit at the machine.** Nothing in code knows which.
- **A rehearsed off-script moment.** A child asks something not on the map; she
  reads the library and answers as a teacher, then comes back to the lesson.
- **Evidence across sessions.** Session two opens by reviewing what they actually
  did — named versus only pointed at.

*Gate:* the same binary teaches a lesson it was never built for.

### 4.6 P5 — Rehearse  ·  1 day

Two full runs in the real room, recorded and measured. Failure drills: unplug
speech, kill Hermes, pull power mid-period. The numbers that go in the
submission come from here, not from adjectives.

---

### Parallel tracks

| Track | Owns | Phases |
|---|---|---|
| **A — Core** | `teacher_os`, `app.py`, `db.py`, MCP schema | P0, P1 presence gate, P3 restore |
| **B — Stage** | `RoomDock`, `micRecorder`, speech | P1 chrome removal, P2 VAD |
| **C — Content** | `content/library/`, demo script | P4 second unit, off-script rehearsal |

A and B both touch the moment the class opens — the gate is Core's, the chrome
is Stage's. Nothing else overlaps.

**~5.5 focused days serial; roughly 3–4 calendar days across three tracks.**

---

### Deliberately NOT before the demo

Each is a real improvement. None of them is what makes a judge believe it is an
agent, and each carries risk we cannot absorb now.

| | Why not now |
|---|---|
| **VieNeu-TTS bilingual** | A new model on unproven hardware. Piper picks one voice per line, so a code-switched sentence is mispronounced — real, but rare if the school language stays a late rung. Two days of risk for a defect a judge will not hear |
| **Camera / identity** | Demoted to a fallback anyway. A named probe answers "who" without a camera |
| **The two-axis evidence model** | Locked today and correct — but it is a refactor, not a capability. Nothing in the demo shows it |
| **`:::item` / `:::family` syntax** | Needed when a second author arrives, not for one unit |
| **Multigrade, FTS5, the 11-tool set** | Real, later, none demo-visible |

**The one thing that would change this order:** if the remaining time is under
three days, cut P3's restore work and P5's second run — but never cut P4. A demo
that cannot survive a restart is a weakness; a demo that is secretly hardcoded is
a lie.

## 5. Boot and prove

```bash
# conda base
./scripts/teacher-up.sh
#   speech :8001 · core :8004 · hermes :8642 · vite :3000
#   nothing teaches until a session opens

#   room:     http://127.0.0.1:3000/classroom
#   adult:    curl -s http://127.0.0.1:8004/teacher/status
```

```bash
cd services/classroom-core && python -m pytest \
  tests/test_teacher_os.py tests/test_teacher_heartbeat.py \
  tests/test_teacher_voice.py tests/test_no_unit_pedagogy.py \
  tests/test_library.py tests/test_bus.py -q
cd services/agent && python -m pytest tests/test_hermes.py -q
```

```bash
# live Chromium — the owner often will not click; you must
export PLAYWRIGHT_CORE=file://$PWD/.tools/node_modules/playwright-core/index.mjs
export CHROME_PATH=$HOME/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome
# tests/node/teacher_e2e_playwright.mjs    /classroom (needs updating: it drove /learn)
# tests/node/teacher_room_playwright.mjs   Start + mic — goes stale when buttons die
```

Restart **Core only** after Python changes (`teacher-up.sh start` also reloads
Whisper). Vite HMR covers the UI. **One hosted turn at a time.**

### Endpoints

| Method | Path | Role |
|---|---|---|
| GET | `/teacher/status` | `phase`, `hermesUp`, `speechUp`, `stageAudioOwner`, `readyToStart`, `sessionOpen`, `turnBusy`, `lastSay`, `lastFault`, `silenceMs` |
| POST | `/teacher/session` | open an OS session; `open:true` runs `[sat_down]` **synchronously** (slow) |
| POST | `/teacher/turn` | student text, or a system token `[sat_down]` / `[heartbeat]` |
| POST | `/teacher/heartbeat` | `pulse_teacher` (optional `force`) |
| WS | `/ws` | Stage events. An unknown `EventType` must be refused **before** `next_seq` |

---

## 6. Map of the live code

```text
services/classroom-core/teacher_os.py   TeacherOS, 8 tools, pulse_teacher, status
services/classroom-core/library.py      read/search library, unit_catalog
services/classroom-core/app.py          /teacher/*, heartbeat loop in lifespan
services/classroom-core/bus.py          refuses unknown EventType before seq
services/classroom-core/db.py           observations, skills, sessions, memories_fts (unused)
services/classroom-core/mcp_server.py   MCP tool surface
services/agent/bright_agent/hermes.py   render_teacher_turn, EVENT=heartbeat|class_start
infra/hermes/patches/0002-teacher-multi-tool.patch  8 iterations, tool_choice required, exit on say
scripts/teacher-up.sh
apps/classroom-ui/src/stage/Stage.tsx   wall + board slot + AIRI + RoomDock
apps/classroom-ui/src/stage/RoomDock.tsx        product-wrong; next cook removes
apps/classroom-ui/src/speech/speakingDriver.ts  TTS + wLipSync mouth
packages/airi-bridge/                   the attach (not references/airi/apps/stage-web)
content/library/                        maps, keys, how-to-teach
```

There is no second teacher in the tree any more. See §3c.

---

## 7. Landmines — do not re-learn these

- **The hosted model writes its own language onto the board.** MiMo is a
  Chinese model and put "不用唱出来，听听就好" on the projector in a Vietnamese
  classroom. A prompt instruction is not a control for this. Core now refuses
  any script the authored library does not itself use (`_alien_script`), for
  `write_board`, `say` and every `show_exercise` string. The permitted set is
  **derived from the curriculum, not hardcoded** — NS-7 — so a deployment that
  teaches in another script gets it automatically.

- **The hosted model is slower than every timeout you will guess.** Anything
  that expires in about a minute -- `turn_id` TTL, HTTP read timeouts -- will
  fire mid-turn and look like a logic bug. It is not.
- **`teacher-agent-l1.sh start` also stops Vite**, because `teacher-up.sh`
  stores the UI pid in the same runtime dir. Re-run `teacher-up.sh` after a
  stack restart or `/classroom` will refuse the connection.
- **The panels are as sharp as the source allows.** The PDF's embedded page
  images are 1151x1622 at 100 ppi -- *lower* than the 1683x2379 exports the
  crops come from. Re-extracting at a higher DPI gains nothing.

- **`board.present` is not an `EventType`.** Publishing it allocated a `seq`,
  then died; Stage saw a gap and dropped `speech.turn`. The bus now refuses
  unknown types *before* allocating. `_push_stage` must publish `scene.update`.
- **Stage must `capability.report {audio_output:true}`** or Piper never starts
  (`speakingDriver` stays disabled). Leases now always exist, with or without a
  `lesson_run`.
- **`seq` is per connection.** Every extra page is another socket and therefore
  another potential loudspeaker. `/classroom` is the only page that may play
  audio; `test_there_is_exactly_one_room_page` enforces it.
- **Piper picks one voice per line** by counting Latin vs Vietnamese letters —
  but `how-to-teach.md` *mandates* code-switching inside one line
  ("This is a banana. Chuối — banana."). She therefore mispronounces her own
  pedagogy. The bilingual research recommends VieNeu-TTS v3 Turbo (Apache-2.0,
  ONNX INT8) as the replacement. **This is a pending decision, not open
  research** — see [research/external/](research/external/).
- **Whisper `small.en` invents words** on clips under ~1 s (`BANANO`, `Happy!`).
- **Hiyori: use the unpacked runtime**, `models/live2d/hiyori_pro_zh/runtime/…model3.json`
  (~4.8 MB). The 33 MB zip triggers a Chrome "Network error" on Windows.
- **Live2D must not remount** when `scene.update` arrives — `AvatarLayer` stays
  mounted in `Stage.tsx`.
- **Vite duplicate `speak` import** in `wiring.ts` = PARSE_ERROR.
- **Do not block off-unit images by keyword.** The owner rejected that as bot
  behaviour. Core must not invent Vietnamese fallback lines either.
- **`agy --print` must be last** if you call Gemini; nested heredocs broke an
  apply script once.
- **Never `pkill -f <pattern>`** in an agent shell — the pattern matches the
  agent's own command line and it kills itself, and often the speech service.

---

## 8. Git

```text
teacher-agent   HEAD 623f024   WORK HERE. Almost all Layer 1–4 cook is UNCOMMITTED
main            623f024        same commit; local main is 3 ahead of origin/main
origin/main                    3 behind
```

There is **no commit** for the library teacher, voice, the AIRI room, RoomDock,
or the heartbeat. `git status` on `teacher-agent` is the real status.

Do not create a branch, commit, or merge to `main` unless the owner asks.

---

## 9. Open risks the competition will probe

| Risk | State |
|---|---|
| Avatar licence — Hiyori is Live2D sample material, and donating at scale is distribution | Unresolved. Layer 7. Demo first, per owner |
| Fallback language hardcoded to Vietnamese | `index.md` declares `home_language` / `target_language`; the TTS/ASR side does not honour it yet |
| Ecological validity — passing every gate while failing with real children | Unaddressed |
| MiMo API key rotation before any public demo | Pending |
| Whisper on real child L2 speech | No model validated for this; `small.en` is a demo choice, not a production claim |
