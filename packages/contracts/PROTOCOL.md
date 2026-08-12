# Bright Protocol

Single source of truth for every wire format in the system. **Both sides of every boundary code against this file.** If you are an agent working on one service, do not invent fields — add them here first.

Version: `2`. Every envelope and scene carries `v: 2`. A receiver that sees an unknown version **rejects loudly** rather than guessing. Version 2 adds production lesson start, activity/utterance correlation, streamed speech turns, and physical playback acknowledgements.

---

## 0. Topology recap

```
Hermes :8642  ──SSE──►  Bright adapter  ──►  classroom-core :8004  ──WS──►  classroom-ui :3000
     │                                      ▲              │
     └──────── authenticated Bright MCP ────┘        lesson_run.json
```

`classroom-core` is the only writer of state. Everything else proposes or renders.

---

## 1. Event envelope

Every message on the WebSocket bus. No exceptions.

```ts
interface Event<T = unknown> {
  v: 2
  type: EventType        // dotted, see catalog
  seq: number            // monotonic per connection, gap = you missed something
  stateVersion: number   // bumps on every state mutation
  ts: number             // epoch ms
  payload: T
}
```

`seq` and `stateVersion` are load-bearing. On reconnect the client sends its last `stateVersion`; if the server's is higher the client **discards local state and takes a full snapshot**. Never patch across a gap.

### Event catalog

Direction: `↑` client→server, `↓` server→client, `↕` both.

| Type | Dir | Payload |
|---|---|---|
| `scene.update` | ↓ | `Scene` — full scene, never a diff |
| `scene.snapshot` | ↓ | `{ scene: Scene, lesson: LessonPosition }` — reply to `client.hello` |
| `speech.say` | ↓ | legacy full-text adapter: `{ text, audioAsset?, turnId, conversationId?, replyToUtteranceId? }` |
| `speech.turn.started` | ↓ | `{ speechTurnId, behavior, source, conversationTurnId, activityId?, activityGeneration?, audioAsset? }` |
| `speech.text.delta` | ↓ | `{ speechTurnId, delta }` |
| `speech.turn.ended` | ↓ | `{ speechTurnId, status: 'completed'|'cancelled'|'error', reason? }`; producer terminal, not playback proof |
| `speech.cancel` | ↓ | `{ speechTurnId, reason? }`; exact and idempotent |
| `speech.barge_in.ack` | ↓ | `{ requestId, speechTurnId, accepted, reason? }`; correlated terminal reply to one Control request |
| `avatar.act` | ↓ | `ActPayload` — out-of-band emotion (prefer inline `<\|ACT\|>`) |
| `lesson.position` | ↓ | `LessonPosition` |
| `lesson.started` | ↓ | `{ requestId, sessionId, conversationId, lessonId, studentId?, index, stateVersion }` |
| `student.response.accepted` | ↓ | `{ utteranceId, outcome }`; only this resolves the matching client wait |
| `mode.changed` | ↓ | `{ mode: 'FULL' \| 'DEGRADED' \| 'OFFLINE', reason: string }` |
| `error` | ↓ | `{ code: string, message: string }` |
| `heartbeat` | ↓ | `{ ts: number }` — see §9.8. Consumes no `seq` |
| `heartbeat.ack` | ↑ | `{ ts: number }` |
| `speech.playback.started` | ↑ | `{ speechTurnId }`; Stage only, on first real audio |
| `speech.playback.finished` | ↑ | `{ speechTurnId, status: 'completed'|'cancelled'|'failed', reason?, metrics? }`; Stage only, one terminal ACK |
| `speech.barge_in` | ↑ | `{ requestId, speechTurnId, activityId, activityGeneration }`; Control-only request to cancel that exact active teacher turn before opening the mic |
| `client.hello` | ↑ | `{ role: 'stage' \| 'control', stateVersion?: number }` |
| `interaction.choice` | ↑ | `{ optionId: string, studentId?: string }` |
| `interaction.point` | ↑ | `{ targetId: string, x: number, y: number }` |
| `interaction.drag` | ↑ | `{ fromId: string, toId: string }` |
| `control.command` | ↑ | `{ cmd: 'pause'\|'resume'\|'skip'\|'repeat'\|'back'\|'takeover', arg?: string }` |
| `lesson.start` | ↑ | `{ requestId, index?, studentId?, studentName? }`; Control only, including production |
| `student.speech.final` | ↑ | `{ utteranceId, activityId, activityGeneration, text, studentId?, confidence }` |

`Stage` is the only physical audio owner and playback-ACK sender. `Control` is
the mic/control owner. Core rejects spoofed roles, unknown turns, illegal ACK
transitions, and stale activity generations.

### Push-to-talk barge-in

When Control is asked to record while teacher audio is active, it MUST NOT
open the microphone immediately or issue a global stop. It sends one
`speech.barge_in` correlated to the exact `speechTurnId`, activity, and
generation. Core accepts only a Control client and only while that exact turn
is non-terminal in the current activity generation. Acceptance logically
cancels the active agent task, publishes the exact `speech.cancel`, and replies
to the requesting Control with `speech.barge_in.ack`. Duplicate `requestId`s
are idempotent and receive the original reply; stale or mismatched requests are
rejected without affecting audio or lesson state.

Control may open the microphone only after an accepted ACK and local proof
that Stage reported the matching playback terminal cancellation (including
the echo tail). If either half of the handshake times out, recording stays
closed. Late provider deltas and tool mutations remain fenced by the activity
generation and retired agent turn.

One logical child→teacher exchange has a `conversationTurnId`; one mic capture
has an `utteranceId`; every independently queued/cancellable teacher utterance
has a `speechTurnId`. They are not interchangeable. A new activity generation
fences late ASR, agent deltas, tool results, and playback ACKs.

---

## 2. Scene

What the board shows. `classroom-core` owns it; the UI is a pure function of it.

```ts
interface Scene {
  v: 2
  stateVersion: number
  kind: SceneKind
  props: SceneProps          // discriminated by kind
  overlay?: {
    subtitle?: string
    studentName?: string
    listening?: boolean
    modeBadge?: 'DEGRADED' | 'OFFLINE'   // never shown in FULL
  }
}

type SceneKind =
  | 'idle'
  | 'text'
  | 'image'
  | 'video'
  | 'vocabulary'
  | 'choice'
  | 'matching'
  | 'sentence_builder'
  | 'pronunciation'
  | 'roleplay'
  | 'explore'
```

### SceneProps by kind

```ts
// idle
{}

// text
{ text: string; size?: 'sm' | 'md' | 'lg' | 'xl' }

// image  |  video
{ asset: string; caption?: string; autoplay?: boolean }

// vocabulary
{
  items: Array<{ id: string; text: string; asset?: string; audioAsset?: string }>
  interaction: 'none' | 'point' | 'tap'
  highlightId?: string
}

// choice
{
  prompt: string
  options: Array<{ id: string; text?: string; asset?: string }>
  revealed?: { correctId: string; chosenId?: string }   // set only after an answer
}

// matching
{
  left:  Array<{ id: string; text?: string; asset?: string }>
  right: Array<{ id: string; text?: string; asset?: string }>
  solved: Array<[string, string]>
}

// sentence_builder
{ tokens: Array<{ id: string; text: string }>; placed: string[]; target?: string }

// pronunciation
{
  word: string
  phonemes: Array<{ symbol: string; status: 'pending' | 'good' | 'retry' }>
}

// roleplay
{ environment: string; aiRole: string; studentRole: string; targetPhrases: string[] }

// explore
{ topic: string; nodes: Array<{ id: string; label: string; asset?: string }>; focusId?: string }
```

**Rules**

1. `asset` is always `asset://<id>`. The UI resolves through `/assets/<id>`; it never sees a filesystem path.
2. Scenes are sent whole. No patching — a 2 KB JSON blob is cheaper than a desync bug.
3. Unknown `kind` → the UI renders a visible error card. Never a blank screen in front of a class.

---

## 3. LessonPosition

```ts
interface LessonPosition {
  lessonId: string
  classId: string
  activityIndex: number
  activityCount: number
  stage: string          // HOOK | INPUT | PRACTICE | ... free string
  activityId: string
  activityGeneration: number
  currentStudentId?: string
}
```

---

## 4. lesson_run.json

The compiled, playable lesson. **Must be sufficient to run a full class with the LLM switched off** (NS-1).

```ts
interface LessonRun {
  v: 2
  lessonId: string
  classId: string
  title: string
  focus: string[]
  review: string[]
  studentsToCheck: string[]
  activities: Activity[]
  mediaManifest: string[]        // every asset:// referenced anywhere
}

interface Activity {
  id: string
  scene: SceneKind
  props: SceneProps              // the scene to render
  narration?: Narration[]        // what the teacher says, in order
  durationS?: number             // auto-advance; omit = wait for interaction
  expect?: Expect                // how to grade
  branches?: Branch[]            // where to go next
}

interface Narration {
  text: string
  audioAsset?: string            // PRE-RENDERED at authoring time. Present = no live TTS.
  act?: ActPayload               // emotion/motion to fire after this line
}

interface Expect {
  kind: 'choice' | 'point' | 'drag' | 'speech' | 'none'
  correct?: string | string[]    // id(s), or accepted transcripts for speech
  acceptFuzzy?: string[]         // near-miss transcripts → 'near' outcome
}

interface Branch {
  on: 'correct' | 'near' | 'wrong' | 'silence' | 'timeout' | 'always'
  goto: string                   // activity id
  narration?: Narration[]        // said before jumping
}
```

**Authoring rule enforced by `lesson-lint`:** every activity with an `expect` must cover `wrong` **and** the no-answer case, or carry `always`. A branch point without a default is not authorable — remove it.

Which outcome "no answer" produces depends on timing, and only one of the two can ever fire:

| The activity has | No-answer outcome |
|---|---|
| `durationS` set | **`timeout`** |
| no `durationS` | **`silence`** — after `CORE_SILENCE_TIMEOUT_S` |

Authoring both is harmless and is the safe habit — a lesson stays correct if someone later adds or removes a `durationS`. The linter accepts either the live one alone or both, and *warns* which one is actually reachable so nobody believes a dead branch is protecting them.

> An earlier version of this rule demanded `silence` unconditionally, which made every timed activity carry a branch that could never fire. Corrected 2026-08-11 after `lesson-lint` surfaced it.

### ⚠️ Parsing lesson YAML: `on:` is not a string

A bare `on:` key is parsed by YAML 1.1 as the **boolean `true`**, not the string `"on"`. Since `Branch.on` is the natural spelling for a branch condition, a standard YAML load silently discards **every branch in the file** — and the failure looks like an author who forgot their branches, not like a parser bug.

Anything that reads lesson YAML must normalise boolean-ish keys back to strings (`on`/`off`/`yes`/`no`/`true`/`false`). `tools/lesson-lint/parse.py` does this in `_unbool_keys`; reuse it rather than writing a second parser.

---

## 5. ACT tokens — the Hermes ↔ avatar bridge

This is the mechanism that makes the avatar react to what the agent is doing. Borrowed from AIRI, and the reason its whole audio pipeline works for us unchanged.

Tokens are embedded **inline in the text stream**, so they ride the same ordered queue as the audio and fire in sync with speech.

```
<|ACT {"emotion":"happy","motion":"nod"}|>
<|ACT {"emotion":{"name":"think","intensity":0.6}}|>
<|DELAY 1.5|>
```

### Grammar

- Open `<|`, close `|>`. Both required.
- `ACT` payload is a JSON **object**. All fields optional.
  - `emotion`: a string, or `{ name, intensity }` with `intensity` in `[0,1]` (default `1`).
  - `motion`: free-form string, a Live2D motion group name. Ignored on VRM.
- `DELAY` payload is a bare positive number, space-separated. Seconds.
- An unterminated token is dropped at stream end, never emitted as text.

### Emotions — exactly 9, no others

```
happy · sad · angry · think · surprised · awkward · question · curious · neutral
```

Live2D motion group = capitalized name, **except `neutral` → `Idle`**.

### Parser requirements (do not skip these)

1. **Retain a 5-character tail** when scanning for `<|`. A token split across two SSE chunks must not leak as spoken text. This is the single most common bug in reimplementations.
2. Strip reasoning/`<think>` content **before** text reaches the TTS chunker, not after.
3. Back-pressure: `await` the parser on every delta. The whole pipeline depends on it.

### How the adapter generates them

`hermes-adapter` translates Hermes SSE into a single annotated text stream:

| Hermes event | Emitted |
|---|---|
| `function_call` → a board tool | `<\|ACT {"emotion":"think"}\|>` + a `scene.update` event |
| `function_call_output` where result is a correct answer | `<\|ACT {"emotion":"happy"}\|>` |
| `function_call_output` where result is wrong | `<\|ACT {"emotion":"curious"}\|>` |
| `response.output_text.delta` | the text verbatim |
| `response.completed` | `<\|ACT {"emotion":"neutral"}\|>` |

The Responses stream does not guarantee a `hermes.tool.progress` event; do not
depend on one. The agent itself may also emit ACT tokens in its own text. Both
sources merge into one stream — that is the point of doing it in-band.

---

## 6. Audio pipeline invariants

Reimplemented from AIRI's `pipelines-audio`. Preserve these or you get audible bugs:

1. **Chunker `boost = 2`** — the first two segments bypass the minimum-word rule, to cut time-to-first-audio.
2. **TTS runs 4-way concurrent; playback is scheduled strictly in text order.** A failed segment stores `null` so the sequence gate advances instead of deadlocking.
3. **A special token attached to a segment fires *after* that segment's audio finishes.** Emotion lands on the right sentence.
4. **Muting audio must still dispatch specials.** Otherwise muting freezes the avatar.
5. Lip-sync `getMouthOpen()` returns **0…0.7** and is written raw to `ParamMouthOpenY` (which expects 0…1). Do not rescale.

---

## 7. Modes

```
FULL      agent responding < 3s        agent drives
DEGRADED  agent slow / erroring        core plays lesson_run, agent advisory only
OFFLINE   agent unreachable            core plays lesson_run alone
```

`classroom-core` switches modes on measured latency and emits `mode.changed`. The Stage shows a badge only in DEGRADED/OFFLINE. **The teacher is never asked to care.**

---

## 8. Asset resolution

```
asset://apple.webp   →   GET /assets/apple.webp   (served by classroom-core)
```

Pre-rendered narration audio lives here too: `asset://narration/<activityId>-<n>.opus`.

---

## 9. Clarifications — settled 2026-08-11

The first three implementations each hit the same gaps and interpreted them
independently. These are now **normative**. Where an implementation already
guessed, its guess is recorded as accepted.

### 9.1 Reconnect and resnapshot

There is deliberately **no "request snapshot" event**. To resnapshot, a client
**re-sends `client.hello`** carrying its last `stateVersion`.

> **The server MUST answer every `client.hello` with a `scene.snapshot`** —
> unconditionally, including when the client's `stateVersion` equals or exceeds
> the server's. A client's version is a reason to *take* a snapshot, never a
> reason to skip one.

Skipping would deadlock gap recovery: the client discards state, asks again, and
waits forever. **Verified against the live server 2026-08-11** for
`stateVersion` = 0, equal-to-server, and far-ahead. All three answered.

### 9.2 Client→server envelopes

Client messages are full `Event<T>` envelopes. The client keeps its **own `seq`
counter, reset per connection**, and sets `stateVersion` to the highest it has
seen. The server ignores client `seq`; it may use client `stateVersion` for
staleness checks.

### 9.3 Interaction geometry

`interaction.point.x` / `.y` are **normalised 0…1 within the tapped element**,
not viewport pixels. The server does not know the projector resolution.

A `vocabulary` scene with `interaction: 'tap'` emits **`interaction.point`**.
There is no separate tap event.

### 9.4 Grading outcomes

| Situation | Outcome |
|---|---|
| `durationS` set, no `expect` | auto-advance: take the `always` branch, else the next activity |
| `durationS` set, `expect` present | `timeout` |
| `expect` present, no `durationS` | `silence`, after `CORE_SILENCE_TIMEOUT_S` |
| neither | wait for a control command |

`acceptFuzzy` is generalised beyond speech: it also matches option/target ids so
`choice`, `point`, and `drag` can grade `near`. `drag` matches either `toId` or
the pair form `"fromId>toId"`.

Speech `correct` requires a **normalised exact match** and calibrated ASR confidence
at or above `CORE_SPEECH_CORRECT_CONFIDENCE` (default `0.75`). A low-confidence
exact match is `near`; missing confidence is conservative and also `near`.
Containment is never `correct`, so extra or negating clauses cannot turn a wrong
answer into a false accept. Edit-distance similarity applies only to
`acceptFuzzy`, which yields `near`.

### 9.5 Media props

`image` and `video` are **separate shapes**. `autoplay` exists on `video` only;
`ImageProps` has no `autoplay`. The TS types are authoritative here; the §2
grouping was shorthand.

### 9.6 Subtitle precedence

`scene.overlay.subtitle` is authoritative. `speech.say` fills the subtitle in
when the overlay omits it. A new scene retires the previous spoken line unless
an utterance is still in flight.

### 9.7 `LessonPosition.stage`

`LessonRun` carries no stage field, so the server **derives** `stage` from scene
kind and index: `HOOK / INPUT / PRACTICE / PRODUCTION / EXPLORE / WRAP / DONE`.

### 9.8 Liveness — the board must notice a dead link

A silent link is the dangerous failure, not a closed one. Measured: with bytes dropped but nothing closed, the stage reported `connection.state === 'open'` for **~32 seconds** with a frozen board, waiting on the server's ping timeout. If the FIN is lost too, nothing client-side ever fires and it waits forever.

Thirty children watching a frozen board while the teacher has no idea anything is wrong is exactly the failure a school cannot diagnose.

**Both sides therefore prove liveness at the application layer** — WebSocket ping/pong is not enough, because it is handled below the application and a proxy can keep it alive over a dead session.

| Event | Dir | Payload | Rule |
|---|---|---|---|
| `heartbeat` | ↓ | `{ ts: number }` | Server sends every **5 s**, regardless of other traffic |
| `heartbeat.ack` | ↑ | `{ ts: number }` | Client echoes the `ts` it received |

- **Client:** no frame of any kind for **12 s** ⇒ treat the link as dead. Close it, show a visible "reconnecting" state, and reconnect. Do not wait for the transport.
- **Server:** no `heartbeat.ack` for **15 s** ⇒ drop that subscriber and reclaim its queue.
- `heartbeat` does **not** consume a `seq` and does not bump `stateVersion`. It is out-of-band by design: a heartbeat must never look like state, or a reconnect would see a phantom gap.
- The round trip is worth surfacing on the facilitator console. A link at 400 ms is still working; a link at 4 s is about to fail, and a teacher deserves that warning before the room notices.

### 9.9 Backpressure

If a client's send queue overflows, the server **closes the socket with 1011**
rather than emitting a `seq` gap. A closed socket triggers a clean reconnect and
resnapshot; a silent gap does not.

### 9.10 Default mode

With no agent seam injected, the server boots in **OFFLINE** — which correctly
puts a badge on the stage from the first frame. `CORE_MODE=FULL` pins it for
development. A mode change emits **both** `mode.changed` and `scene.update`,
because the badge lives in the scene overlay.

### 9.11 One adaptive source of spoken text

Hermes plain assistant text deltas are the sole adaptive human-facing speech
source in the live Option B profile. `classroom_say` is not exposed there;
otherwise tool speech and assistant text can be spoken twice. Core-authored
narration uses the same v2 speech-turn pipeline and remains the deterministic
fallback. Inline `<|ACT|>` tokens are parsed in `airi-bridge`, fire after the
associated audio segment, and never reach TTS as literal text.

Opening a speech turn suppresses the mic. Core opens listening/timers only from
the matching terminal playback ACK (plus the configured echo tail), never merely
because it published text. Until measured full-duplex support exists, PTT is
half-duplex and refuses capture while output is active.
