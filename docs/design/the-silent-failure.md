# The silent failure

> A value arrives, is used for one purpose, and is then discarded by a guard —
> with no log, no fallback, and no visible sign — while a sibling path rescues
> the identical condition.

This file exists because on 2026-08-21 that one shape cost most of a day, over
and over, in six different components. Every instance looked like a different
bug. None of them raised anything. Several had a working rescue sitting twenty
lines away.

If you are debugging this system and something "just does nothing", read this
before you read anything else.

---

## Why it is expensive

A failure that raises gets fixed in minutes. This class never raises. It
produces a room that is *plausibly working*:

- the board updates, so the WebSocket is clearly fine
- the subtitle appears, so the teacher clearly spoke
- the census says `ok=True`, so the turn clearly succeeded
- `hermesUp` reads green, so the model is clearly alive

…and the child heard nothing. Every instrument agrees, and every instrument is
measuring the wrong side of the guard.

## The tell

**Two paths, one condition, one rescue.** Every instance found had a sibling
that handled the same case correctly. That asymmetry is the strongest signal
available, and it is greppable: find the guard, then look for its twin.

## What it cost, concretely

| what happened | what it looked like | what it was |
|---|---|---|
| Her opening greeting was never synthesised | She started a lesson and refused to speak | `speech.say` only spoke if it already held the audio lease. `speech.turn.started`, twenty lines below, took the lease when it did not. |
| An hour spent chasing a "flaky model" | `"teacher agent did not say"` | `402 Insufficient credits`, flattened into one string that stands in front of every possible cause. `hermesUp` still green. |
| Every successful preparation reported failure | The nightly job "had never worked" | It judged itself by the harness's terminal-`say` contract — and `say` is what `PREPARE_TOOLS` forbids. The plan was on disk the whole time. |
| Whisper took 11.4s on 3.4s of speech | "The model is slow, we need a better box" | Six temperature re-decodes of the same window. 16s of clean audio decoded in 2.3s. |
| Ten of twelve clips were room noise posted as a child's turn | She answered things nobody said | `no_speech_probability` was computed by the service and parsed by the browser, and nothing read it. |
| A child spoke and was ignored, all session | The microphone is broken | Silero VAD stripped 100% of ordinary-volume speech before Whisper saw it. peak/RMS proved the mic was fine. |
| A diagnostic that never produced a file | "the dump does not work" | It was pasted into the TTS route, where `audio` is not in scope. `NameError` into a bare `except: pass`. It failed exactly the way the bug it was built to find fails. |

## The rules that came out of it

1. **A guard that drops something must say so.** Not necessarily to the child —
   to the log, to `/teacher/status`, to *someone*. A drop nobody can observe is
   indistinguishable from the feature never having been asked for.
2. **When you write a guard, find its sibling.** If another path handles the
   same condition, they must agree, or the difference must be written down.
3. **Never flatten a cause.** `"teacher agent did not say"` was true and useless.
   Say whether she called any tool at all, and what she was told when refused.
4. **A dead safety net is worse than none.** A `PendingSpeech` queue existed with
   a flush wired into `enableAudio`, and nothing ever assigned to `pending`. It
   read as though the race was handled, so nobody looked. Delete or complete.
5. **Judge a thing by what it leaves behind**, not by a contract borrowed from
   somewhere else. Preparation is judged by the plan on disk.
6. **A diagnostic that cannot report its own breakage is not a diagnostic.**
7. **When a value is computed, ask who reads it.** Written first in STATE.md §2e
   after the fifth instance in one day; it kept being right.

## Where the instruments are now

- `peak` / `rms` on every ASR call (`services/speech/app.py`). Separates "the
  microphone sent nothing" from "the microphone sent speech a threshold
  rejected". Two numbers. They would have saved an afternoon.
- `room stayed asleep: <why>` (`teacher_os._asleep_because`). Five mutually
  exclusive reasons used to collapse into `asleep/tick` every ten seconds.
- MCP refusals log before they vanish (`mcp_server.py`). A `TurnRejected` means
  `os_.execute` never ran, so the refusal reaches no census — `tools=0
  refusals=-`, identical to a model that chose to call nothing.
- The turn-failure detail distinguishes "no tool call at all" (look outside the
  room) from "refused" (look inside it).

## Still open, and known

- **Success is reported before the child hears anything.** `_handle_teacher_turn`
  returns `ok=True` the moment the `say` tool returns — before the browser has
  fetched, synthesised or played a syllable. A client-side TTS failure never
  reaches the model, the census, or `/teacher/status`, and `LAST_SAY=` tells her
  next turn that she already said it. This is the largest remaining instance of
  the whole class.
- **`close_period` swallows its only fallible write.** `db.end_session` sits in a
  bare `except: pass` with no log, while `last_close_at` and `teacher_os = None`
  are set regardless. If that write fails, the next lesson RESUMES the finished
  period instead of starting the next one, `PERIODS_HELD` stays undercounted,
  and the lobby leaves the next card locked — self-healing only after the 2h
  resume window expires.
- **`bus.publish` returns a fan-out count** that all ~15 call sites discard. A
  working "did anyone actually hear this" signal, wired to nothing.
- **`speech.say` is dead in production.** Only `/dev/say` emits it; the live path
  is `speech.turn.started` + `speech.text.delta`. Its comment reads as though it
  protects the opening greeting. It does not — the other two handlers do.
- **`RoomDock`'s `noSpeechProbability < 0.9` check can never be false**, because
  `stt.ts` already throws at `>= 0.6` two layers earlier. The incident comment
  above it describes enforcement that has silently moved.

## Found in the first take's audit, 2026-08-21

Five more of the same shape, from the 30-minute filmed lesson. The full
reckoning is in `what-the-first-take-taught-us.md`; these are the instances.

- **The day's objectives are parsed and then dropped before she sees them.**
  `library.py:177` extracts `Objectives in play` from the unit map; `list_periods`
  is imported in exactly one place — `app.py:595`, the route that draws the lobby
  cards. `teacher_os.py:1512` sends the model *all six* unit objectives with no
  mark of which two belong to today. She repeated one objective forty times and
  never attempted the other, and nothing anywhere reported a problem. The
  curriculum said it, the parser read it, the front page showed it, the teacher
  never got it.
- **A missing `learnerId` is answered with someone else's record.**
  `app.py:600` falls back to `settings.default_learner_id` — a scaffold value
  with no rows — so `/library/periods` returns a confident `covered: []` for a
  child with seventeen `correct` observations. 30 of 32 calls during the take
  omitted the parameter. An endpoint that silently substitutes a different
  subject is worse than one that errors.
- **A poll budget re-armed by a re-render.** `useIdentify.ts` promises to stop
  after `MAX_TRIES = 10`; `StudentCamera.tsx:79` passes a fresh inline arrow as
  `onIdentified`, which is in the effect's dependency array, so every re-render
  resets `done.current` and `tries.current`. It ran 55 times in 31 minutes,
  burning the CPU the decoder was short of. `LobbyRoute.tsx:150` — twenty lines
  away, same pattern — wraps it in `useCallback` and stops correctly. The
  textbook sibling-rescue tell.
- **The TTS failure log is written only on success.** `app.py:557` logs the
  character count *after* `_synthesize` returns, so the two chunks that crashed
  with `wave.Error: # channels not specified` left no record of what she was
  trying to say. We know two of her sentences were lost. We cannot know which.
- **`LobbyCamera`'s `catch {}` does not count the miss.** `misses.current` is
  incremented only in the `recognised: false` branch, never in the network-error
  branch — so if vision is down, the door never reaches `STRANGER_TRIES` and the
  "I'm new" enrolment offer never appears. A child stands in front of a camera
  that is looking at nothing, with no way in.

And one more, adjacent: **`RoomDock`'s status-poll `catch` rescues exactly one
phase.** `if (phaseRef.current === 'asleep') setDock('fault')` — every other
phase keeps its stale label. If `/teacher/status` dies while the dock says
"listening", the projector goes on saying "listening" for the rest of the class.

Fixed since: **a lost microphone reported to nobody.** `micRecorder` detected
`device_lost` and called `onDeviceFailure`, which had no listener anywhere in the
app; `ensureStream()` then handed the same dead device back forever. A projector
unplugged mid-session made the room permanently deaf while the dock still said
"Tới lượt con nói". `ec87dbd`.
