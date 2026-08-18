# Decision: the classroom is the room

**Date:** 2026-08-18  
**Status:** HALF-SUPERSEDED the same day  
**Still true:** `/classroom` is the room; `/learn` is not the product; copy OpenClaw heartbeat *shape*  
**Wrong:** Start class + Hold-to-talk as the teaching contract  

Owner 2026-08-18: autonomous teacher, sometimes **no buttons**, like a human.
Heartbeat must open the class. See `docs/STATE.md` §1.

---

## The product a judge should touch

One projected surface. The teacher is already in the room. You talk to her.

```
/classroom   THE room     board + body + Start + hold-to-talk
/control     adult only   observability + emergency. Never a teaching move
/learn       leftover     cheap 1:1 mouth from Layer 2. Not the demo path
```

`/learn` stays wired so we can still drive Hermes without a mic. It is not
where class happens.

---

## Interaction (what a child or facilitator actually does)

```text
ASLEEP     teacher standing, board empty or last scene
           one pill: Start class
           tiny light: green = Hermes + Stage ready; amber = wait

WAKING     Start pressed (or adult boots the appliance)
           Core checks Hermes / speech / Stage
           then wakes the same teacher session  ([sat_down])
           she greets and begins. No second “type to your teacher” window

SPEAKING   she talks (Piper on Stage). Mouth moves. Mic is dead
           (half-duplex. Stage is the only loudspeaker)

LISTEN     she asked something. Mic glows. Hold to speak
           Spacebar is the same press (demo / facilitator)

HEARING    you are holding. Amber ring. Release to send

THINKING   Whisper → POST /teacher/turn → Hermes tools
           board and voice update on this same screen

HEARTBEAT  class silent too long after her last line
           Core pulses the same session ([heartbeat])
           if nothing to do she stays quiet (HEARTBEAT_OK)
           if she should prompt or move, she uses the same tools

FAULT      Hermes or the speaker is down
           room stays. OS notifies + retries. No cassette
```

No chat log on the projector. A fading “I heard …” chip is allowed so the
speaker knows the mic worked. Subtitles stay on the board, not as bubbles.

---

## What OpenClaw heartbeat actually is (and what we copy)

OpenClaw’s heartbeat is **not** the 5 s WebSocket ping (`heartbeat` /
`heartbeat.ack` in PROTOCOL.md). That ping only keeps the socket alive.

OpenClaw heartbeat (`references/openclaw/docs/gateway/heartbeat.md`) is:

- a **periodic main-session agent turn** (they default 30 m; we are a live class)
- the same agent, same tools, same memory
- **skip if busy** (defer while a turn is in flight)
- **stay quiet** if nothing needs attention (`HEARTBEAT_OK`)
- **wake now** on an event (Start class, student speech)
- health / inbox checks; it does **not** invent a second teacher

Bright maps that onto a classroom:

| OpenClaw | Bright classroom |
|---|---|
| cron tick | Core `pulse_teacher` every ~10 s |
| inbox / calendar | silence after last `say`, Hermes up, speech up, Stage lease |
| HEARTBEAT_OK | no `say`, no new board, no evidence |
| wake now | Start class → `[sat_down]`; mic release → student text |
| defer if busy | `asyncio.Lock` around the Hermes turn |
| do not extend chat freshness | heartbeat is not a student utterance and not evidence |

Health probes **do not** call the model. Only “the class has been silent
long enough that a teacher would look up” calls Hermes.

Silence floor is ~45 s after the last teacher line or student act. Hosted
MiMo is one-at-a-time: a heartbeat must never overlap a live turn (429).

---

## Who owns the clock

Core. The projector can die and the OS still knows the class is open.
The Stage posts `/teacher/heartbeat` as well, so a live room can poke
sooner, but the loop does not depend on a React interval.

Hermes remains the only teacher. Core does not pick the next activity
when the pulse fires.

---

## Non-goals

- Always-on VAD / barge-in (half-duplex hold-to-talk is the demo contract)
- Camera / `student_id` (Layer 5)
- Growing `/learn` chrome
- OpenClaw as a runtime (already rejected)
- A second agent inside AIRI
