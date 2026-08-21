# What the first take taught us

A 30-minute lesson was filmed on 2026-08-21: a real child enrolled at the door,
entered the room, and was taught Period 1 of `gs3-u1-hello` end to end. It
worked. It was also the first time the whole machine ran long enough for its
slow faults to show, and this is what they were.

Everything below is measured from the take's own logs, frozen at the time. Where
a number is an inference rather than a measurement, it says so.

---

## The take, in numbers

```
61  ASR calls        min 3.2s   p50 4.1s   p90 17.4s   max 20.3s
224 TTS calls        2 failed (HTTP 500)
62  teacher turns    61 ok=True, 1 ok=False
51  student turns
40  observations written to the record
55  face identifications   (the budget was 10)
 0  refusals, 0 websocket drops, 0 wrong-name identifications
```

The lesson held for half an hour without a crash, a stuck turn, or a
misidentified child. What follows is what sat underneath that.

---

## 1. Why she kept asking the same question

The owner's words, watching live: *"sao nó hỏi hoài"*.

All **40** evidence rows in the record are the same objective:

```sql
select distinct skill from observations;   -- greet-and-name
```

Period 1 has two objectives. `answer-a-greeting` was never attempted — not once
in 51 student turns, not in the database, not in the log.

This looks like the model choosing badly. It is not. **The model was never told
which objectives belong to today's period.**

`teacher_os.py:1512` builds the per-turn context:

```python
text="OBJECTIVES=" + ", ".join(catalog["objectives"]),
```

`catalog["objectives"]` is *every objective in the unit* — all six, spanning all
three periods. Nothing in it says which two are in play today.

The period-scoped list does exist. `map.md` states it plainly, and `library.py`
parses it:

```python
_IN_PLAY = re.compile(r"^Objectives in play:\s*(.+?)\s*$", re.M)   # library.py:177
```

But `list_periods` — the only function that reads it — is imported in exactly
one place in the whole service:

```
services/classroom-core/app.py:595:  from library import list_periods, list_units
```

The HTTP route that draws the lobby cards. **The curriculum states the day's
objectives, the parser extracts them, the front page displays them, and the
teacher never sees them.**

So she did the only thing the context supported: she re-ran the beat she had
evidence for, with four different character portraits, forty times.

Two things make it worse rather than cause it:

- `format_skill_memory` (`teacher_os.py:1341`) shows per-turn stats only for
  objectives already attempted. Having attempted one, she saw one. It is
  circular: the card can never point at the thing not yet tried.
- Nothing gates progression. `record_evidence` accepts any objective in the unit
  catalogue, unlimited repeats, with no notion of "this one is covered, move on".

**The fix is one line of plumbing, not a prompt.** Put the period's own
`Objectives in play` into the turn context, and mark which are already covered.
The curriculum already says it; only the wire is missing.

---

## 2. Silence is the slowest thing to transcribe

The counter-intuitive one, and the cause of every visible freeze on camera.

Whisper has no reason to stop early on an empty clip. With nothing to
transcribe it rambles to the end of its 30-second window — so **the quieter the
audio, the longer the room freezes on it.**

Measured live during the take:

| peak | what it was | infer |
|---|---|---|
| 0.756 | real speech | 3.9s |
| 0.920 | real speech | 3.3s |
| 0.072 | room noise | 17.4s |
| 0.019 | near-silence | 18.1s |
| 0.019 | near-silence | 19.7s |

Eleven of the 61 clips were silence. **Eight of those eleven scored below the
no-speech threshold**, meaning the room would have posted them to the teacher as
a child's turn — she answers furniture, in front of a class.

Fixed in `ec87dbd`: peak amplitude is already computed for the log line, so it
costs nothing to check it first. Below `SILENCE_PEAK` (0.10) the clip never
reaches the model. The margin is four-fold — the quietest real utterance on this
microphone peaked at 0.435, the loudest silence at 0.072. Deliberately a peak
and not an RMS: one word spoken into a quiet room has a low RMS and a high peak,
and one word is what a beginner's answer looks like.

**This closes 7 of the 8 stalls, not 8.** One remains unexplained and is written
down here rather than rounded away:

```
17:42:06   8.5s of real speech, peak 0.484, no-speech 0.156   ->  18.2s
           8.5s of real speech, peak 0.138                    ->   4.8s
```

Same length, four times apart. One real utterance in fifty. Not diagnosed.

---

## 3. Two of her sentences never reached the room

Two TTS calls returned 500 with `wave.Error: # channels not specified` from
`app.py:459`. The same two seconds appear in the browser log as
`[airi-bridge] TTS failed for a segment; skipping it` — one event seen from both
ends. **Two of the teacher's lines were silently dropped mid-lesson.**

Root cause, verified in piper's own source: `synthesize_wav()` sets the WAV
header *inside* the loop over synthesized chunks. Text that espeak cannot voice
— pure punctuation, a lone emoji, a `"?!"` split off by the sentence regex —
yields zero chunks, so the loop never runs, the header is never written, and
closing the file raises.

The guard at `app.py:409` only drops chunks that are empty after `.strip()`.
`"…"` survives it.

A second gap made this hard to see: the log line carrying the character count is
written *after* a successful synthesis, so a failing request leaves no record of
what it was asked to say. We know two lines were lost. We do not know which.

---

## 4. The room kept asking who the child was, all lesson

`useIdentify.ts` is built to stop: `MAX_TRIES = 10`, and a comment stating
*"it stops entirely as soon as the room is confident, because re-identifying the
same child for the rest of the period is pure cost."*

It ran **55 times across 31 minutes.**

`StudentCamera.tsx:79` passes a fresh inline arrow as `onIdentified`, which sits
in the effect's dependency array. Every re-render tears the effect down and
rebuilds it, resetting `done.current = false` and `tries.current = 0`. The budget
is re-armed forever.

Twenty lines away, the lobby gets it right — `LobbyRoute.tsx:150` wraps the same
callback in `useCallback(..., [])`, and its poller stops as designed.

Nothing errored. Nothing logged. The safety net was simply dead, burning CPU for
the whole lesson — on the same CPU Whisper was short of.

---

## 5. Nobody could see the child's progress, ever

`/library/periods` reports `covered: []` for a child with 17 `correct`
observations on file. The computation is right; re-running it by hand against
the live database returns `covered: ['greet-and-name']`.

The fault is `app.py:600`:

```python
learner = (learnerId or "").strip() or core_.settings.default_learner_id
```

Omit the query parameter and the route answers `200 OK` for `learner-1` — a
deployment scaffold with no rows — instead of saying it does not know who is
being asked about. Of 32 calls during the take, **30 omitted it**, including one
mid-lesson.

An endpoint that silently substitutes a different subject and returns a
confident empty answer is worse than one that returns an error.

---

## 6. What the recording itself cost

The owner filmed with OBS, with the webcam live, with a browser and an IDE open.
That is not a footnote:

```
machine idle       40.4s of audio  ->  5.6s     7.25x faster than real time
during the take    49 real clips   ->           1.34x faster than real time
```

**A three-fold slowdown, present the entire session.** It does not appear as a
trend — the 5-minute medians stay flat at 3.3–4.8s — because a constant load
raises the whole floor rather than tilting it. It is only visible against an
idle baseline, which is why it was missed twice while reading the log alone.

The lesson for future measurement: *a flat median does not mean there is no
contention.* Always compare against a known-idle run.

---

## The shape all of these share

Every finding above is the same bug, wearing different clothes — the one
`the-silent-failure.md` already names:

> a value arrives, is used for one purpose, and is discarded by a guard with no
> log, no fallback and no sign to the user, while a sibling path rescues the
> identical condition.

- The period's objectives are parsed, then dropped before the model sees them.
- A learner id is optional, and its absence is answered with someone else's data.
- A face-poll budget is reset by a re-render, silently.
- An unvoiceable chunk 500s, and the log of what it said is written only on success.
- A microphone dies, reports it, and the report has no listener. *(fixed, `ec87dbd`)*

And two more, found in this audit, not yet fixed:

- `RoomDock`'s status-poll `catch` rescues exactly one phase (`asleep`). If
  `/teacher/status` fails while the dock says "listening", it goes on saying
  "listening" for the rest of the class.
- `LobbyCamera`'s `catch {}` does not increment the miss counter. If the vision
  service is down, the door never reaches `STRANGER_TRIES`, so **the "I'm new"
  enrolment offer never appears** — a child stands in front of a camera that is
  looking at nothing, forever.

---

## What to do next, in order of what it buys

**1 · Tell her what today's objectives are.** (§1) The single highest-value
change in this document: it is the difference between a lesson that progresses
and one that loops. Wire `list_periods`' `inPlay` into the turn context, and mark
covered ones. One line of plumbing; the curriculum already carries the data.

**2 · Never answer for a learner nobody asked about.** (§5) Make `learnerId`
required, or return an explicit "unknown learner" rather than a confident empty.

**3 · Guard the unvoiceable chunk, and log what failed.** (§3) Skip spans that
phonemize to nothing; move the character-count log *before* synthesis so the next
failure says what it was trying to say.

**4 · Memoize `onIdentified`.** (§4) A one-line fix that returns CPU to the
decoder for the length of every lesson.

**5 · Give the failing paths a voice.** The two open silent failures above, plus
the five already catalogued in `the-silent-failure.md`.

**6 · Measure against an idle baseline, always.** (§6)

---

## The open design questions

These are not bugs. They are the things the take showed are not yet good enough,
and they need a decision before they need code.

### Two speeds, one teacher

The owner's proposal: a fast model for immediate response, the current agent for
the real teaching. The problem it addresses is real — a hosted turn takes 7–19
seconds, and the room is mute for all of it.

The trap is obvious once stated: **two voices that can contradict each other.**
If the fast lane says anything pedagogical — praises a wrong answer, accepts a
mispronunciation, commits to a next activity — the slow lane arrives seconds
later and either repeats it or contradicts it in front of the class. That is
worse than silence.

So the split should not be by speed. It should be **by authority**:

- The fast lane *holds the floor*. It acknowledges, it echoes back what was
  heard, it says "let me think about that" — and it never judges, never teaches,
  never decides what comes next.
- The slow lane keeps every pedagogical decision it has today.

And once the fast lane is forbidden from teaching, most of it does not need a
model at all. Holding lines are curriculum, not computation — they belong in
`map.md` beside the arrival and rescue lines already there (NS-6: profession is
data, not code; NS-7: software never names a language). A second model, if it
earns its place later, should *select* among curriculum-authored lines rather
than generate pedagogy.

Start with the zero-model version. It is cheaper, it cannot contradict anyone,
and it removes the dead air — which is the actual complaint.

### Which sentence is she answering?

*"không xác định được agent đang nói cho câu nào"* — with a 7–19 second gap
between a child speaking and the teacher replying, and a child who may speak
again inside that gap, nothing on screen pairs an answer with its question.

The material for the fix already exists: `speech.say` carries a `turnId`, and
the heard-chip is built per utterance. What is missing is that they are never
shown as a pair. The chip should hold the sentence it belongs to until *its*
answer arrives, and her reply should be visibly anchored to it — not merely the
most recent thing either party said.

This also disposes of a real hazard, not just a cosmetic one: today, a child who
speaks twice in the gap gets one answer, and cannot tell which sentence it
belongs to.

### The gate still opens on nothing

Eleven silent clips in half an hour means the energy gate opened eleven times on
a room where nobody was speaking. The peak guard (§2) stops those clips reaching
the model, but it treats the symptom — the gate should not have opened. The
threshold constants have never been measured against a real classroom's noise
floor, only against this room's.

### The live-text lane, still owed

*"nói tới đâu, speech-to-text tới đó"* — attempted, reverted before filming
because chunked decoding cost accuracy (*"I am 9 years old today"* became
*"I am not ironier as a soldier today"*). The design that survives is: phrases
drive the on-screen chip, the whole clip is what reaches the teacher. The
peak/RMS instrumentation added since exists precisely to measure the next
attempt.

---

## Still true, still unfixed, carried forward

- Rotate the OpenRouter and MiMo API keys.
- Close the microphone while she *thinks*, not only while she speaks.
- `services/speech` has tests but no `pytest` in its venv, and the core venv
  lacks `python-multipart` — so the speech suite ran in neither. The silence
  guard shipped verified by measurement and import only. **Fix the venvs before
  trusting that suite again.**
- Hermes healed 47 empty assistant messages during the take
  (`Pre-call sanitizer: healed N empty non-final message(s)`), roughly three in
  four multi-tool turns. Nothing broke. It is the exact shape that becomes a
  stuck teacher on a stricter provider — worth watching, not yet worth acting on.
- 34% of turns compose a `board_text` that is then discarded because the same
  turn also called `show_image`. Graceful, but wasted generation on every third
  turn.
- `.wslconfig` now sets `swap=0` and `memory=24GB`, permanently. Swap on a full
  C: was killing the VM; see `wsl-crashes-on-swap`.


---

## What was done about it — 2026-08-22

Everything above is now fixed, in five commits. What is worth carrying forward is
not the list but the two things the fixing taught.

**The plumbing was the pedagogy.** §1 read like a model behaving badly and was a
missing wire. The curriculum stated the day's objectives, the parser extracted
them, the front page displayed them, and no line of code carried them to the one
reader who needed them. Before blaming a model for a teaching decision, check
that it was told the thing it would have needed to decide differently.

**A new rule, and the reason it had to be written down.** The holding lines are
the first text in this system that becomes speech without the model in the loop
— necessarily, since they exist to cover the wait *for* it. That is a door into
"Python decides the lesson", so it is bounded explicitly:

> **Core may quote the curriculum. Core may never compose.**

The sentence is read verbatim from the unit map, by the same kind of parser that
already reads period titles and card art, with the same authority as an arrival
line. Core chooses only *which* of the author's sentences, and only in rotation.
The map itself says what may not go in that table — no praise, no questions —
because a question the room asks in her name is a question she did not ask.

This is also why the owner's two-tier idea was implemented as *no second model*.
Splitting by speed puts two voices in the room that can contradict each other:
the fast one accepts a wrong answer and the slow one corrects it four seconds
later, in front of a class. Splitting by **authority** cannot — the holding line
says nothing about what the child said. If a fast model earns a place later, it
should *select among authored lines*, never generate pedagogy.

### Fixed

| § | What | Commit |
|---|---|---|
| 1 | The period's objectives reach her; the catalogue lists only declared ids | `3b6db5a` |
| 2, 5 | No answering for a learner nobody asked about; four silent guards | `c013e7f` |
| 3, 4 | Holding lines; the chip paired with the answer to it | `32f4a11` |
| 6 | Unsayable text no longer 500s; the log records the attempt, not the success | `0af2941` |
| — | A lost microphone reports; silence never reaches the decoder | `ec87dbd` |

`services/speech`'s suite ran for the first time in the process — its venv had no
pytest, and borrowing core's fails because that one has no `python-multipart`.
Thirty tests, including the route-level regression for the two requests that
crashed on camera.

### Deliberately not done

**The live-text lane** (*"nói tới đâu, speech-to-text tới đó"*). Attempted and
reverted before filming: chunked decoding cost accuracy — *"I am 9 years old
today"* came back as *"I am not ironier as a soldier today"*. With §3 pairing the
answer to its question and §4 filling the silence, the *perceived* latency
problem is largely addressed without it. Re-land it with time to measure. The
peak/RMS instrumentation exists for exactly that.

**The gate's constants.** Eleven of 61 clips were an empty room, so the gate
opened eleven times on nobody. The peak guard stops those reaching the model but
treats the symptom; the thresholds have never been measured against a real
classroom's noise floor, only this one's.

**The eighth stall.** One real 8.5-second utterance took 18.2 seconds while an
identical-length clip took 4.8. Not silence, not duration, not the wall clock.
One in fifty. Undiagnosed, and written down rather than rounded away.
