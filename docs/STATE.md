# STATE — the one living document

**Updated:** 2026-08-19
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
Bright MCP             her hands — 11 typed tools
classroom-core :8004   the OS — I/O, clock, DB, reject, restart
Stage /classroom       THE room. Board + speaker + body. The only page children see
packages/airi-bridge   the body (Live2D + lipsync) — nothing else
speech :8001           Piper TTS + faster-whisper ASR
/control               adult console, separate tab. Never on the projector,
                       never makes a teaching move
```

**The eleven live tools.** Do not add a twelfth without a decision doc.
[Why exactly these.](decisions/2026-08-18-show-exercise-tool.md) ·
[the eleventh](decisions/2026-08-19-she-can-call-the-adult.md)

```
LOOK UP    read_library  search_library  read_board
CHANGE     write_board   show_image      show_exercise  play_clip
INTEND     plan                                         ← hers; Core never reads it
REMEMBER   record_evidence
HAND OVER  call_the_adult(reason, detail?)              ← stops teaching; only a
                                                          person resumes her
SPEAK      say(…, wake_in_s?)                           ← ends the turn; may ask
                                                          the room for the next beat
```

**Whatever Core prints, Core must accept.** `ASSETS=` once listed the unit's
assets with `asset://` stripped, and every tool that takes one requires the
whole form — so she copied exactly what she was handed and was refused
`asset-malformed`: measured 2026-08-20 over a live period, `show_image` 4 of 5
and `play_clip` 3 of 3, with a blank board for the whole lesson. The round trip
is now a test (`test_every_id_core_hands_her_is_an_id_core_accepts`). Note
`_as_asset` deliberately does **not** also accept a bare id — two spellings of
one argument is the coin flip `show_image`'s `left`/`right` was deleted for.

**Length bounds never reach the wire.** The provider serving
`google/gemma-4-26b-a4b-it` returns HTTP 422 for the entire request on
`maxLength` in a tool schema, while Gemini accepted the identical schema all
day. Core validates from the same dicts and the limit arrives as prose — see
`wire_tools()` and `test_the_wire_schema_carries_no_length_bounds`.

Order is deliberate and identical in `mcp_server.TOOLS`, `hermes.TEACHER_TOOLS`
and the config include list: a model reads `tools/list` as a narrative, and the
terminal tool should be the last word.

`say` carries an optional `board_text` — she chalks in the same breath. It is
the one content field allowed on the terminal tool, because an invalid one is
**skipped and reported** while the class still hears her.
`write_board` is the other moment: writing goes up first, then she talks about
it, and a refusal comes back with a reason she can act on.

`present` and `open_response` were compatibility branches in
`teacher_os.execute`, reachable from no tool list. Deleted 2026-08-19.

A merge of five of these into one `teach` tool was tried and reverted the same
day. [Why flat won, and what the round-trip was actually
costing.](decisions/2026-08-19-flat-tools-and-bundling.md)

**Memory shape.** SQL `observations` (with `mode ∈ name|point|ask`) →
`SKILL_CARD` + `PAST` on every turn, scoped to one `student_id` across all
sessions. `PLAN` is the plan she wrote for this period, in the `lesson_plans` table —
[stored, never branched on](decisions/2026-08-19-she-keeps-her-own-plan.md). It
replaced the in-RAM `BEATS` log, which Core wrote *about* her and from which she
had to re-infer where she was every turn.
One census line per turn records tool names, count and `board_touched` — counts
only, no words — so a model that quietly stops bundling or stops using the board
is visible before a term of lessons has gone by. Raw child words appear only
as `STUDENT_SAID` for the current turn (NS-5). No raw child speech in SQL.

---

## 2b. What a rehearsed period actually looks like — measured 2026-08-19

`scripts/rehearse-period.py` drives a scripted pupil and scores the **period**,
not the turn, because the failure it was written for is invisible per turn.

Baseline, clean database, 12 pupil turns:

```
reads      how-to-teach.md, skills/index.md, map.md, keys.md
clips      track-05                     she DID play a recording
images     u1l1-dialogue-a              ONE picture, never changed
exercises  -                            show_exercise: zero
objectives greet-and-name               she did NOT leave Period 1
outcomes   {correct: 1, near: 1, wrong: 1}    marking is honest
skills opened: NONE
```

An earlier run in which she taught the whole three-lesson unit in six turns
turned out to be **ten stale `correct` rows from previous testing**: coverage
reported the unit mastered, so advancing was the rational move. That is fixed at
the source — see [Core is a witness](decisions/2026-08-19-core-is-a-witness.md).

What was fixed the same day: skills are named by Core in `READ_NOW` on a
witnessed event; `say(wake_in_s)` lets an activity last more than one exchange;
`exercises.md` payloads were not the shape `show_exercise` accepts, so a copied
block was refused and she fell back to talking; `READ_NOW` is capped at two
files a turn, because naming four on the opening turn spent the whole call
budget on reading and the class heard silence.

### Re-measured live 2026-08-20 — and the run before it was a blank board

The 2026-08-19 numbers above hid a worse failure that only shows in the census
`refusals` column. Over the live period of 2026-08-20 **before** the fixes:

```
show_image     5 calls   4 refused   asset-malformed
play_clip      3 calls   3 refused   asset-malformed
show_exercise  0 calls               never called in any census, ever
read_library  15 calls   vs 9 say
opened: conduct and skills only — 0 × exercises.md, keys.md, practice.md
```

Seven of eight media moves refused, so the board was blank and no recording
played for the whole lesson. Three independent causes, all now fixed:

1. **`ASSETS=` stripped `asset://`** and every tool requires it — Core refused
   the exact string Core had handed her. See §2 above.
2. **`WHISPER_MODEL` disagreed with itself in three places.** `app.py` defaulted
   to `small.en` and `infra/systemd/bright.env.example` — *the appliance that
   ships* — said the same, while `teacher-agent-l1.sh` exported `base`. Every
   dev run went through the launcher, so the `.en` default was masked on the one
   box nobody deploys. All three now say `base`; the Vietnamese table is in
   `services/speech/app.py`, and `small` lost it by returning an **empty**
   transcript for *"Con không biết"*, 3 runs of 3, at 3× the latency.
3. **The exercise path was a bootstrap requiring itself.** `READ_NOW` named
   `exercises.md` only `if this_period.strip()` — i.e. only after evidence
   existed, which needs a child to have answered, which an exercise is the
   cheapest way to cause. It was never a *candidate*, so the two-file cap was
   never what suppressed it.

Same harness, same pupil script, after — a whole period, 15 pupil turns:

```
PERIOD REPORT   turns=15  p50=16.4s  unit=gs3-u1-hello  minutes=7
  refusals   0            <- was 7 of 8 media moves
  clips      track-09
  images     char-group, u1l1-dialogue-b
  exercises  -
  objectives answer-wellbeing
  outcomes   {correct: 1, near: 1, wrong: 1}   <- UNDER-REPORTED, see below:
                                                  SQL held 10 wrongs, not 1
  reads      map.md, open-a-period, keys.md, judge-a-response, how-to-teach.md,
             skills/index.md, scaffold-down,
             put-up-an-exercise, units/gs3-u1-hello/exercises.md   <- FIRST TIME EVER

  PASS played a recording · opened a skill · read the key before judging
  PASS marking is not degenerate · she spoke every turn · no turn errored
  FAIL put up an exercise
  FAIL changed the picture            6/8 period properties hold
```

She said *"Fine, thank you"* in **14 of 15 turns**, and I first read that as bad
pacing. It was not. **Both of those FAILs were the harness judging the wrong
period, and the diagnosis changed twice under scrutiny:**

- `count_periods_held` returned **1**, so by the map this was **Period 2 — How
  are you? Goodbye**, whose objectives are exactly `ask-wellbeing`,
  `answer-wellbeing`, `take-leave` and whose recording is `track-09`. Her stored
  plan opens *"Period 2: …"* and she executed it faithfully all period. The
  scripted pupil is the one who was in Period 1.
- `exercises.md` was titled *"Exercises — Hello, **Lesson 1**"* and scoped to
  pages 10–11. **Periods 2 and 3 had no authored payloads at all.** She opened
  the file, found nothing for her period, and correctly declined. That is the
  deepest reason `show_exercise` was never called in any census — not
  prompting, not the two-file cap.

What *was* wrong was smaller and had been invisible for the same reason both
FAILs were: **our instruments were under-reporting.**

```
SQL observations   12 rows, all answer-wellbeing, 10 of them `wrong`
THIS_PERIOD        answer-wellbeing x2                    <- said 2
period census      outcomes {correct: 1, near: 1, wrong: 1}  <- said 1 wrong
```

`period_evidence` **deduplicated**, so ten identical failures collapsed to one
entry. Evidence is a tally of attempts, not a set of things touched, and the
unit map's whole pacing law is *"Time is not the measure; attempts are"*. Both
the fact she reads and the census the adult reads said the marking was healthy
while the child missed the same thing ten times running. Fixed at `add(...,
tally=True)`; `turn_recorded` already caps it at one row per objective per turn.

`THIS_PERIOD` also threw the outcomes away — it split `objective:outcome:mode`
and kept `[0]` — so *"tried five times"* and *"failed five times"* rendered
identically. It now carries them, and a witnessed `wrong` names
`skills/scaffold-down/SKILL.md` in `READ_NOW`, the exact mirror of the
`NO_REPLY` block. Presence, not a threshold: *"three wrongs means back up"* is
pedagogy, and NS-6 keeps pedagogy in the library.

Two more gaps closed while fixing this:

- **`OBJECTIVES=`** now sits beside `ASSETS=`. She opens `map.md` on turn one
  and never again — `already` is permanent and `store: false` keeps nothing — so
  from turn two her only continuity was one line of `PLAN` and `LAST_SAY`, which
  is why the last thing she said predicted the next thing she said.
- **The wire declared `required: ["id", "text"]`** on choice options while Core
  enforces `text` **or** `asset`, and `ex.4`'s two picture choices are
  asset-only. Both the tool and the file say *copy a block whole and send it* —
  so following the instruction produced a call the schema forbids. Same species
  as the `content: {}` bug. `test_authored_payloads_are_sendable.py` now runs
  every authored block through the wire schema **and** real Core, so *"never
  called"* can no longer quietly mean *"never callable"*.

Lessons 2 and 3 are now authored — the four-turn exchange and the visitor as
`roleplay`, the listening checks as text `choice`, the phrases and the two first
sounds as `vocabulary`. They carry no panels of their own (whole-page scans
only, and the map forbids projecting a page), which is what decided those
shapes.

### The run after that — 2026-08-20, same harness, still Period 2

```
PERIOD REPORT   turns=15  p50=15.5s
  periods held before this one: 1  (the map says what meeting #2 is for)
  her plan   Period 2: 1. Pre-task: Review greeting...
  exercises  vocabulary                    <- SHOW_EXERCISE FIRED. First time ever.
  objectives greet-and-name, answer-wellbeing, take-leave     <- three, was one
  outcomes   {correct: 3, near: 1, uncertain: 1, wrong: 8}    <- 13 rows, counted
  reads      ... put-up-an-exercise, exercises.md, scaffold-down
  refusals   0

  PASS put up an exercise · opened a skill · read the key before judging
  PASS marking is not degenerate · she spoke every turn · no turn errored
  FAIL played a recording
  FAIL changed the picture            6/8
```

The chain worked end to end and in order: a `wrong` put `scaffold-down` in
`READ_NOW`, she opened it, and the next outcome on that objective moved
`wrong → near`. She reached `take-leave` before closing — she left an objective,
which she had never done. Her Vietnamese asides landed where a stuck child
needs them (*"Không sao đâu."*, *"Mình khỏe, cảm ơn."*).

**Still 6/8, and honestly so.** She played **no** recording at all this period
(the last run did), and put up two pictures where the check wants three. And the
repetition is reduced, not gone: *"Fine, thank you"* is still most of what she
says for ten turns in the middle.

Chasing *that* turned up the fourth instance of the same pattern, and the most
embarrassing one. `period_census` has carried `clips` / `images` / `exercises`
since the day it was written, and its own docstring says why:

> *"No clip played all period is the finding, and no single turn can show it."*

That finding went to `/teacher/status`, for the adult, and **was never once
shown to the person who could act on it.** She had `images=` and `clip=` — the
*current scene* — and nothing at all about the twenty minutes before it. So a
period with `clips=[]` sat next to an `ASSETS=` line offering ten recordings and
she had no way to notice the gap.

`USED_SO_FAR=clips none; images char-mai, char-minh; exercises vocabulary` now
rides in the state block beside `OBJECTIVES=`. Same species as the three fixes
above, same fix: Core witnessed it, computed it, showed a human, and told her
nothing. It is the "shown state, not owned state" NS-5 asks for — a list of her
own moves, not a transcript.

### The run after that — 7/8

```
PERIOD REPORT   turns=15  p50=15.9s   refusals 0
  clips      track-09          <- played 6 times; last run played NONE
  images     char-mai, char-minh
  exercises  vocabulary
  outcomes   {correct: 2, near: 1, wrong: 10}     13 rows

  PASS played a recording   <- was FAIL
  PASS put up an exercise
  FAIL changed the picture                        7/8
```

She also used `write_board` for the first time in any of these runs, and the
`wrong → scaffold-down → near` chain repeated, so it is behaviour and not luck.

**The one that is left is the honest one.** She can now *see* `images char-mai,
char-minh` and still does not put up a third; she plays the same `track-09` six
times rather than reaching for `track-10`. Every fix so far worked by removing
a fact she was missing, and she is no longer missing this one — which is the
evidence that the remaining problem is not information. It is that she has no
reason to vary, and the map's pacing law ("two new items per ten minutes",
"three different partners is a good target") is a law about *variety* that
nothing has ever asked her to satisfy.

That is a pedagogy problem, so it belongs in a skill, not in Python. It went
into `scaffold-down`, which is already the skill Core names on a witnessed
`wrong`: a new section tells her to read `THIS_PERIOD` and `USED_SO_FAR`
together and answer the question no single turn can — *have I been going down a
rung, or saying the same rung again?* — and to change the **material** rather
than the wording when the count climbs and nothing on the board has moved.

---

## 2c. She held a spoken conversation — measured 2026-08-20

Every speech test before this one drove **one** utterance and stopped.
`tests/node/a_child_talks_to_her.mjs` drives a whole lesson through the
microphone: one WAV of the child's side with silence where she answers, the
real gate, the real Whisper, the real turn loop.

**Six spoken exchanges in a row**, and the census of that period:

```
reads      map.md, open-a-period, keys.md, judge-a-response, how-to-teach.md,
           skills/index.md, scaffold-down, put-up-an-exercise, exercises.md,
           take-the-floor, elicit-chorally, recover-a-wobble      (12 files)
clips      track-10          <- a LESSON 2 recording, unusable before today
images     char-group, char-ben
exercises  choice            <- the Lesson 2 ex.2 block authored the same day
outcomes   {wrong: 4, near: 1}   5 rows
lastSay    "Is it A: Fine, thank you, or B: Hello?"
```

That last line is the authored payload, on the board, for a child who spoke
into a microphone.

### The number nobody had measured: what the child actually waits

p50 turn latency is 15.9 s, but that is *model* time. The wait that matters runs
from the child stopping speaking to the teacher starting:

| | child waits |
|---|---|
| turn 1 | **75.7 s** — she is opening the class: reading the map, writing a plan |
| turn 2 | 23.3 s |
| turns 3–6 | 18.3 – 19.8 s, still falling |

Two consequences. **A real child waits ~19 s to be answered**, which is the
latency problem stated in child-time and the strongest argument for local
Gemma. And **the opening turn is long enough to swallow the next thing the
child says** — with a flat 40 s gap the fixture's second sentence landed inside
her first reply and was lost to half-duplex gating. The fixture now uses a
95 s first gap and 45 s after, both from the table above. A human in the chair
does not need this; they wait for her to finish. A recording cannot.

### One-word answers are below the floor

`"Hello"` renders in 592 ms and the gate drops anything under
`MIN_CLIP_MS = 600`, which exists because Whisper invents words on short takes.
A Grade-3 beginner's most likely utterance is one word. Not fixed — recorded,
because the fix is a real trade against hallucination and needs child audio to
settle.

**To re-run the live lesson:**

```bash
./scripts/teacher-up.sh
# the room only opens itself when someone is in it: the Stage must hold the
# audio lease, so keep a browser on /classroom for the whole rehearsal
python3 scripts/rehearse-period.py --pupil scripts/pupils/lesson1.txt
node tests/node/projector_reads_as_a_classroom.mjs      # no model needed
```

**To talk to her, which is the only test that really counts:**

```bash
./scripts/teacher-up.sh
python3 tools/build_pupil_conversation.py \
    --script scripts/pupils/spoken.txt -o /tmp/pupil.wav
PUPIL_WAV=/tmp/pupil.wav node tests/node/a_child_talks_to_her.mjs
```

Do **not** pipe that through `tail` — it buffers to EOF and you go blind for the
whole run. And do not delete a log the running service holds open: the fd stays
write-only, the file is unrecoverable, and the census for that run is simply
gone.

Read the result the way that audit did — `refusals=`, `reads=` and
`images=/clips=/exercises=` in the census, not the pass/fail of a test.

The two Playwright runs need `PLAYWRIGHT_CORE` and `CHROME_PATH` set — see
`.tools/run-headless.sh`.

---

## 3. Layer status — honest

| Layer | Status | Truth |
|---|---|---|
| 0 OS | ✅ | bus, session, DB, leases. **The cassette was deleted 2026-08-18** — see §3c |
| 1 Teacher text | ✅ closed 2026-08-17 | Hermes + library teaches 1:1. Live chats `minh-show` / `minh-c3` |
| 2 Thin station | ⬛ removed | `/learn` was deleted 2026-08-18. One page: `/classroom` |
| 3 Voice | ✅ wiring closed 2026-08-18 | Stage speaks `say` via Piper; ASR → `/teacher/turn`. Piper picks en/vi **per line by script**, which is not real bilingual — see §7 |
| 4 Body + room | ✅ wiring closed 2026-08-20 | Live2D + wall + board on Stage. **Autonomy done:** the presence gate opens her own class, the RoomDock buttons are gone, `voiceGate.ts` is a real VAD. Caveat that matters: *presence* is the Stage holding the audio lease, so an open browser tab counts as a class. A person in the room is Layer 5 |
| 5 Class of 20–40 | ⬜ | fairness, camera → `student_id` only |
| 6 Local Gemma | ⬜ | swap the Hermes provider profile. Hosted **Gemini 3.7 Flash via OpenRouter** now (§3e). MiMo's one-concurrent-run limit is gone with it — `max_concurrent_runs` is 4, and Core's `_TURN_LOCK` is what keeps her from speaking twice |
| 7 Giveaway | ⬜ | Hiyori licence, locale-as-config, consent, appliance image |

---

## 3b. The gap, stated as the north star states it

[NORTH-STAR.md](NORTH-STAR.md) §2 models the teacher's **working day**.
**Updated 2026-08-19 — all five boxes now exist:**

```
BEFORE      prepare for a period nobody has arrived at yet     ✅ nightly prepare
ARRIVAL     notice a person, greet them                        ✅ presence gate
THE PERIOD  open, teach, judge, adapt, pace, close             ✅ turn loop + rhythm
CLOSE       end it herself, on time                            ✅ say(closing)
AFTER       write up evidence; it changes next time            ✅ evidence writes
```

**BEFORE** runs on Core's own day clock at 03:00, or on demand via
`POST /teacher/prepare`. She reads the unit and the class's past properly —
nobody is waiting, so this is the only place an offline 4B is allowed to be
slow, and therefore the only place it is allowed to be thorough — and writes the
period's plan. She cannot speak, use the board or record evidence while the room
is empty; that is enforced in `execute`, not asked for in a prompt.

It deliberately does **not** use Hermes' `cron` or `delegate_task`:
[why the harness could not give us that
guarantee](decisions/2026-08-19-prepare-is-ours-not-hermes.md).

Within THE PERIOD, the rhythm is no longer a single constant: she waits ~7s
after asking (one nudge, then the long floor), reads PERIOD_MINUTES to judge
when time is up, and an interrupted period resumes instead of restarting.

All three clocks now run:

| Clock | Owner | State |
|---|---|---|
| Reflex < 100 ms | Core | ✅ |
| Turn, seconds | `pulse_teacher` | ✅ built and **already running** |
| **Day, minutes → hours** | `scheduler.py` | ✅ `prepare_next` at 03:00 drafts the period; `lastPrepare` on `/teacher/status` says whether it worked |

### How close this actually is — traced 2026-08-18

The autonomy gap is far smaller than it looks. Three of the four pieces already
run with no human involved:

| Piece | Evidence |
|---|---|
| **Presence is already sensed** | `BusProvider.tsx:41-58` sends `capability.report` automatically on WS connect and every 4 s. Core grants the stage-audio lease with no click. Kiosk loads `/classroom` by itself (`infra/kiosk/kiosk.sh:12`) |
| **The pulse already runs** | `app.py:686-688` starts `teacher_heartbeat_loop` unconditionally on every Core boot — no env flag. It ticks every 10 s forever (`teacher_os.py:675-684`) |
| **The pulse already knows how to stay quiet** | `pulse_teacher` returns `HEARTBEAT_OK` without spending a model turn unless silence ≥ 45 s and ≥ 20 s since the last pulse (`teacher_os.py:634-672`) |
| **A day-clock socket already exists** | `scheduler.py:108-114` runs a `prepare_next` cron at 03:00 via APScheduler — and it calls `AgentSeam.prepare_next`, which is **a no-op by default** (`scheduler.py:43-53`). The hook was built and never filled |

**The single blocker — RESOLVED 2026-08-19, kept for the trace:**
`start_teacher_session()` had exactly one caller —
`POST /teacher/session` (`app.py:747-755`) — and the only thing that sends that
request in the kiosk path is the `Start class` button
(`RoomDock.tsx:100`, `onClick` at line 242).

So the pulse ticks every 10 s next to a room that has already reported presence,
and does nothing, because no session exists and only a human click can create
one. Closing that is roughly: *if no session, and the stage lease is held, and
Hermes and speech are up → open the session and fire `[sat_down]` yourself.*

The rest of Layer 4 autonomy — open-mic instead of hold-to-talk — **is done**
(`voiceGate.ts`). When this was written it was: `micRecorder.ts` is strictly press/release, and `captureEndpoint.ts:4`
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

Benchmarked with the **real** harness prompt and the tool schemas as they stood
that day — nine of the current eleven — five calls each:

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
services/classroom-core/teacher_os.py   TeacherOS, 10 tools, pulse_teacher, prepare_period, close_period, status
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
- **Whisper invents words** on clips under ~1 s (`BANANO`, `Happy!`) — the voice
  gate discards anything shorter. The resident model is `base` (multilingual)
  since 2026-08-19: `small` was 2.3x slower for the same words, `tiny` heard
  "Ben" for "Minh".
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
| API key rotation before any public demo | **Two now.** The MiMo key, and an OpenRouter key that was pasted into a chat transcript on 2026-08-19. Rotate both |
| Whisper on real child L2 speech | No model validated for this; `base` is a demo choice, not a production claim. Mixed VI/EN in one sentence fails outright — "Chuối" is heard as "Joy" |

---

## 2d. ASR and TTS, measured without spending model credit — 2026-08-20

`tools/speech_roundtrip.py` synthesizes a line and reads it straight back
through our own ASR. The speech service is local and free; the teacher is not.
Every question about voice or hearing gets answered here, not by paying for a
live period to discover the microphone was wrong.

It measures **intelligibility**: if our own ASR cannot recover the words, a
child certainly cannot. It is a floor, not the acceptance gate — speaker
similarity, accent breaks and naturalness need bilingual human raters
(research §12), and nothing may be called *adopted* on machine evidence alone.

```
kind  voice   asr      lang  words   line -> heard
en    en     2293ms    en    2/2     Hello. I'm Ben.      -> "Hello, I'm Ben."
en    en     2425ms    en    3/3     How are you?         -> 'How are you?'
en    en     2681ms    en    3/3     Fine, thank you.     -> 'Fine, thank you.'
en    en     2430ms    en    1/1     Goodbye.             -> 'Goodbye.'
en    en     2500ms    en    6/6     Listen and repeat: Fine, thank you.
vi    vi     2744ms    vi    3/5     Con chưa hiểu bài này  -> 'Bỏ chứ hiểu bài này'
vi    vi     2463ms    vi    2/4     Con không biết cô ạ    -> 'và không biết của anh.'
vi    vi     2715ms    vi    0/3     Không sao đâu.         -> ''          <- EMPTY
mix   en/vi  2516ms    en    6/9     Không sao đâu. Say with me: Fine, thank you.
mix   en/vi  4461ms    vi    5/12    How are you? Mình khỏe, cảm ơn. Listen and say: ...
                                     content words recovered: 31/48 (65%)
```

**English is solid: 15/15 content words, four of five lines verbatim.** The
target language — the thing a child copies and the thing we mark them on — is
heard correctly. That is the half that had to work.

**Vietnamese is the weak link: 5/12**, and a short line came back **empty**.
Same failure shape as the `small` weights: silence and "the child said nothing"
are indistinguishable to the room.

**Mixed lines lose whichever half the clamp did not pick.** The decoder
conditions one language over the whole utterance, so `en` swallowed
*"Không sao đâu"* and `vi` mangled *"Listen and say"*. This is the ASR mirror of
the TTS bug fixed in `a4268ab`, and the research predicted it exactly:
*"utterance-level language conditioning can bias code-switched decoding"*. Now
confirmed on our own audio rather than quoted.

It does **not** justify swapping the ASR family — the research is explicit that
nothing changes before the 72-child locked evaluation. It does say where the
next real work is: per-span decoding, or PhoWhisper as the cheap bake-off.

### The board fight `say` was losing

Recorded live: she called `show_exercise(choice)` and said *"Look at the board.
How does Mai answer? A or B?"* in one message — and the board showed her
`board_text` instead, so the class was asked to choose between options it could
not see. Our own standing prompt causes it (*"Put every tool call you already
know you need in ONE message — including say"*) and warns about the outcome two
paragraphs later.

A deliberate hand now beats the convenience one: when `show_exercise`,
`show_image` or `write_board` ran this turn, `say(board_text)` is **skipped and
reported** instead of overwriting. She still speaks; the board keeps what she
put there; the result says why.


---

## 2e. What a real person found in ten minutes — 2026-08-20

The owner sat down with a webcam and a microphone and used it. Three things came
out that no test and no scripted rehearsal had produced.

**The camera loop works with a real face.** Self-view in the corner, the choice
exercise on the board with the correct option ticked, the heard-echo chip
showing what he said. That is the whole perception seam running end to end with
a person in front of it.

**"Fine, thank you" came back as "Thank you." — and the ASR model is innocent.**
`voiceGate` calls `mic.start()` only *after* energy clears `floor × 2.2`, and
`start()` is async. So the sound that opens the gate is the one sound never
recorded. "Fine" is short with a soft onset, exactly the shape that gets eaten.
Whisper never heard the word; the audio did not contain it. The fix is a
pre-roll buffer — record continuously, keep the last ~300 ms before the gate
opened — which is a restructure of `micRecorder`, not a constant to tweak.
**Not done.** Written here so nobody spends another day blaming the model.

**She answered things nobody said.** Whisper returns
`no_speech_probability`, `stt.ts` parses it, and `RoomDock` never looked at it:
**ten of twelve clips in that session came back `no-speech 1.000`** — a chair, a
cough, the tail of her own reverb — and every one was posted as a turn. That is
why she asks "Hi, how are you?" into an empty room. Now guarded at 0.9. The
threshold errs toward dropping a real sentence, because the child repeats it and
the alternative is a teacher talking to furniture.

That is the fifth and sixth instance of one pattern in a single day: **the
system measures something, and never tells the part that could act on it.** It
is worth naming as a review question rather than a series of bugs — when a value
is computed, ask who reads it.
