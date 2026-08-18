# Decision: the room runs itself — no product buttons

**Date:** 2026-08-18
**Status:** LOCKED (owner correction)
**Supersedes:** `classroom-is-the-room.md` interaction contract (archived) — Start class + Hold-to-talk as the teaching contract
**Authority:** [NORTH-STAR.md](../NORTH-STAR.md) §1 "The AI is the teacher. The adult is support."

---

## Decision

The adult boots the appliance. Nothing else. **The teacher opens her own class,
and the room listens when she is not speaking.**

`Start class` and `Hold-to-talk` were a misread of the north star. They put an
adult inside the teaching loop — precisely what NS-1 forbids. They ship today as
`RoomDock.tsx`; they are temporary chrome, not the product.

```text
Adult boots the appliance  (teacher-up / kiosk Chromium)
  → Stage connects, claims the audio lease
  → Hermes healthy + speech healthy
  → Core opens the class itself                      [sat_down]
  → she greets, writes the board, teaches
  → while she is not speaking, the ROOM listens       (VAD, no button)
  → silence too long → the same pulse: prompt, move on, or HEARTBEAT_OK
  → she closes the period
  → /control is observability + emergency only
```

**The one permitted gesture:** browser autoplay and microphone permission may
require a single pointer event at kiosk boot. That is an operating-system fact,
performed once by the adult who plugged the machine in. It is not a
per-utterance product button.

---

## What "heartbeat" means here

Two different things share the word. Do not confuse them.

| | What it is | Where |
|---|---|---|
| **WebSocket heartbeat** | 5 s ping / `heartbeat.ack`, keeps the socket alive, consumes no `seq` | `PROTOCOL.md` §9.8 |
| **Teacher pulse** | a periodic *agent turn* on the main session — the OpenClaw shape | `teacher_os.pulse_teacher()` |

The teacher pulse is borrowed from OpenClaw's gateway heartbeat
(`references/openclaw/docs/gateway/heartbeat.md`). OpenClaw is **not** in the
runtime — see [hermes-over-openclaw.md](hermes-over-openclaw.md). Only the shape
is copied:

| OpenClaw | Bright classroom |
|---|---|
| cron tick | Core pulse every ~10 s (`HEARTBEAT_TICK_S`) |
| inbox / calendar | silence since last `say`, Hermes up, speech up, Stage lease held |
| `HEARTBEAT_OK` | no `say`, no board change, no evidence written |
| wake now | presence → `[sat_down]`; student speech → student turn |
| defer if busy | `asyncio.Lock` around the Hermes turn |
| does not extend chat freshness | a pulse is not a student utterance and never becomes evidence |

Health probes do **not** call the model. Only "the class has been silent long
enough that a teacher would look up" spends a turn. Silence floor is ~45 s
(`HEARTBEAT_SILENCE_S`), with a 20 s cooldown between pulses.

Hosted MiMo serves **one turn at a time** — a pulse must never overlap a live
turn or the provider returns 429.

---

## Who owns the clock

**Core.** The projector can die and the OS still knows the class is open. The
Stage may `POST /teacher/heartbeat` so a live room can poke sooner, but the loop
does not depend on a React interval.

Hermes remains the only teacher. When the pulse fires, Core does **not** pick
the next activity.

---

## What this requires that does not exist yet

Traced against the code on 2026-08-18. Most of the mechanism is already there.

**Already automatic, no human involved:**

| | Evidence |
|---|---|
| Kiosk opens `/classroom` by itself | `infra/kiosk/kiosk.sh:12` |
| The Stage announces presence and claims the audio lease | `BusProvider.tsx:41-58` — on connect and every 4 s |
| The pulse loop runs on every Core boot, ungated | `app.py:686-688` → `teacher_os.py:675-684`, 10 s tick |
| The pulse refuses to spend a model turn unless the room is really quiet | `teacher_os.py:634-672` — 45 s silence floor, 20 s cooldown |

**The single blocker:**

`start_teacher_session()` has exactly one caller — `POST /teacher/session`
(`app.py:747-755`) — and in the kiosk path only the `Start class` button sends
it (`RoomDock.tsx:100`, click handler at line 242).

The pulse therefore ticks every ten seconds beside a room that has already
announced itself, and does nothing. The fix is a presence gate inside
`pulse_teacher`: *no session + stage lease held + Hermes up + speech up → open
the session and fire `[sat_down]`.*

**Genuinely missing:**

| Gap | Today |
|---|---|
| Room listens with no button | No VAD anywhere. `micRecorder.ts` is strictly press/release; `captureEndpoint.ts:4` explicitly disclaims being VAD |
| Short-clip guard | Whisper `small.en` invents words on clips under ~1 s (`BANANO`, `Happy!`) — ignore anything below ~600 ms |
| Pulse prompt quality | `[heartbeat]` returns `HEARTBEAT_OK` correctly, but "does she actually look up after silence?" is unproven in a room |
| A day clock | Nothing in the system knows when a class is. See the timetable gap in [NORTH-STAR.md](../NORTH-STAR.md) §2 |

~~`/learn` stays as a debug mouth for driving Hermes without a microphone.~~
**Deleted 2026-08-18, later the same day.** The owner's direction is one page:
`/classroom`, with the board on it. `/learn` had to go for three reasons — it
opened a session merely by being loaded in a browser tab, it was a second
socket and therefore a second potential loudspeaker, and it taught the wrong
habit (typing to the teacher, when the product is speech). `RoomDock` may shrink to a fading
"I heard …" chip plus a fault banner, or disappear.

---

## Non-goals

- Barge-in while she is speaking (half-duplex: Stage is the only loudspeaker)
- Camera / `student_id` — that is Layer 5
- A chat log on the projector (subtitles live on the board)
- OpenClaw as a runtime — already rejected
- A second agent inside AIRI
