# Decision: the room has a front door, and enrolment happens there

**Date:** 2026-08-21 · **Status:** adopted
**Amends:** [2026-08-18-room-runs-itself.md](2026-08-18-room-runs-itself.md) (scope) and
[2026-08-18-identity-is-perception.md](2026-08-18-identity-is-perception.md) (where enrolment lives)

## The decision in one line

`/` lists the periods this appliance has installed and lets a child press the
next one; the camera at that page resolves who they are, and — with an explicit
consent step — is the only place a face is ever enrolled. **Inside `/classroom`
nothing changes.**

## Why this is not a reversal of "no product buttons"

`room-runs-itself` is LOCKED and it is right. What it forbids is **an adult
inside the teaching loop**: `Start class` and `Hold-to-talk` made a human
responsible for each turn of a lesson, which is NS-1 inverted. Both are still
gone. Inside the room there is no Start, no hold-to-talk, no step navigation,
and `_open_on_presence` is untouched — not one line.

The picker is on the other side of that boundary. It is the same act as *"the
adult boots the appliance"*, given a face and handed to the child instead. Once
they press it, the room runs itself exactly as before: the Stage claims the
audio lease, the pulse opens the period, she greets, and the room listens while
she is not speaking.

Two things forced it, and neither is cosmetic.

**The room had no beginning.** A period started because a ten-second heartbeat
noticed that a browser was holding the audio lease. Nothing announced itself and
nothing was chosen, so the first ~70 seconds — during which she reads the map
and writes a plan — read as a hang, and the lesson read as one that had already
started without you. The owner's words after sitting in front of it: *"it just
starts, so it feels broken."*

**The library could not grow.** `_open_on_presence` returns `None` unless
exactly one unit is authored (`teacher_os.py:1898`), with the correct reasoning
that *Core must never pick a favourite lesson (NS-7)*. The consequence nobody had
stated: **authoring a second unit breaks auto-open entirely.** NS-7 says a human
chooses — and until this page there was no human who could. The front door is
the missing half of a rule we had only implemented one side of.

## The shape, and why each part of it is defensive

- **HTTP only. No bus.** The stage-role socket is what claims the audio lease,
  and Core opens a class the moment the lease exists. A stage socket on the
  lobby would make her greet an empty page and then fight the real classroom
  window for the microphone. Asserted by a test.
- **It opens no session.** Pressing a card navigates; the pulse does the rest.
- **It cannot lie about which period this is.** Exactly one card is pressable —
  the period after the last one Core has closed — and both the card and the
  teacher read the same `held` count. A finished period is deliberately *not*
  re-pressable: it would offer Period 1 and open Period 3. Re-teaching means
  resetting what the room witnessed, which is an adult's decision.
- **Rollback is one line.** Delete the `/` route and the old redirect is back.

### The trap that nearly shipped

`unlockAudioOnFirstGesture` arms a `{ once: true }` listener for the *next*
pointerdown, and only `ClassroomRoute` calls it. The press on a period card
happens on the lobby, *before* that route mounts — so the listener would be
installed after the only gesture there was, and then wait for one that never
comes. Silent room, no error anywhere, which on a projector reads as a teacher
who will not speak. `unlockAudioNow()` spends the gesture it is standing in.

## Enrolment moves to the door

`identity-is-perception` says enrolment is *"a deliberate consented act on the
adult console, never on the projector, and never inferred during a lesson."*
Three of those four still hold exactly. The one that changes is **which screen**:
it is the front door, not a separate adult console.

The reason is that the adult console did not exist. `POST /vision/enroll` had
been shipped for days with a consent schema good enough to copy, and **zero
callers** — no UI, no CLI, no script. `data/faces.db` was empty, so every match
failed, so every session in the room's history opened as the configured default
learner. A rule about where enrolment happens is not a rule if enrolment cannot
happen.

What is kept, and what is added:

| | |
|---|---|
| The camera **matches**; it never enrols by itself | two failed matches produce an *offer*, never a record |
| Consent is in the request **type**, not a policy document | `consent_confirmed: Literal[True]` + a reference |
| Embeddings only; no photograph is written | unchanged |
| Never on the projector, never during a lesson | the door is a different page, before the class |
| **New:** Core mints the id and hands vision the same one | `students.id` and `subjects.subject_id` are equal by convention and nothing in SQL enforces it. A browser-minted id would create a second, empty child with the same face, silently |
| **New:** the learner row exists at consent, not at first lesson | an adult can see who consented before anyone is taught |

It also closes a race that made recognition useless even once someone was
enrolled: the room used to identify six seconds *after* the session had already
opened as the default learner, so the answer arrived too late to decide whose
memory to write. From the door, the child is placed before the audio lease
exists — which is before `_open_on_presence` can run.

## What this does not do

- It does not make the room multi-learner. A session still holds one
  `learner_id`.
- It does not add an adult console for enrolment. That is still worth building:
  a school enrolling thirty children wants a roster screen and a deletion
  control, and the reference implementation's `manage_faces.py` is the shape.
- It does not calibrate the recognition threshold. Bright ships 0.363 — OpenCV's
  published operating point — where the reference deliberately ran the more
  conservative 0.45. Still an open item, and still un-measured on real classroom
  images at real distances.
