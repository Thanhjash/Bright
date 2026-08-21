# Bright

An autonomous AI English teacher for classrooms with no teacher, no internet and
no textbook. It is meant to be **given away**.

Switch the appliance on and it teaches. Nobody presses start: the room notices a
class is there and the teacher opens her own lesson, works from a curriculum
library on disk, puts pictures and recordings and exercises on a projected
chalkboard, listens to the children through a microphone, marks honestly, and
closes the period herself.

**There is no lesson tape.** An earlier version of this repository shipped a
scripted player as a fallback; it was deleted on 2026-08-18. The AI is the
teacher, or there is no lesson — see
[NORTH-STAR.md](docs/NORTH-STAR.md) NS-1.

---

## Run it

```bash
cp .env.example .env          # set LLM_BASE_URL / LLM_API_KEY / LLM_MODEL
./scripts/fetch-models.sh     # Piper voices + faster-whisper
./tools/fetch-vieneu.sh       # bilingual VI-EN TTS (optional, ~165MB)
./tools/fetch-face-models.py  # YuNet + SFace for student recognition (optional)

./scripts/teacher-up.sh
```

Then open **http://127.0.0.1:3000/classroom** and allow the microphone. She
opens the class herself; there is no button.

The adult console is a separate tab at **/control** — pause, resume, and the
escalation banner. It never appears on the projector and never makes a teaching
move.

| service | port | what it is |
|---|---|---|
| speech | 8001 | Piper + VieNeu TTS, faster-whisper ASR |
| vision | 8002 | which enrolled student is this, and how sure |
| classroom-core | 8004 | the room's OS: I/O, clock, database, refusals, restart |
| Hermes sidecar | 8642 | the teacher |
| classroom-ui | 3000 | `/classroom` (the room) and `/control` (the adult) |

Vision and VieNeu are optional. Missing models mean those features are skipped,
never that the room fails to come up.

---

## How it is put together

**Classroom Core is a witness, not a teacher.** It owns I/O, the clock, the
database, safety and restart. It never decides what to teach, and it may refuse
a move it saw was wrong — but it never rules on the *meaning* of what a child
did. That is hers.

**The teacher is a coding-agent-shaped harness with a curriculum instead of a
repo.** She reads markdown, calls twelve typed tools over MCP, and gets fresh
authoritative state from Core on every turn. She holds no state of her own
(`store: false`), so a crash costs a turn and not a lesson.

```
LOOK UP    read_library  search_library  read_board  recall_student
CHANGE     write_board   show_image      show_exercise  play_clip
INTEND     plan                                    ← hers; Core never reads it
REMEMBER   record_evidence
HAND OVER  call_the_adult                          ← stops teaching; a person resumes her
SPEAK      say                                     ← ends the turn
```

**The profession is data, not code** (NS-6). How to open a period, elicit from a
quiet class, scaffold down, judge a response, close — all of it is authored
markdown in `content/library/skills/`, discovered by name. None of it is in
Python and none of it is in a prompt constant.

**The deployment declares itself** (NS-7). Languages, timetable and unit live in
`content/library/index.md`. No source file names a language or a subject; tests
enforce it.

| directory | what lives there |
|---|---|
| `content/library/` | the curriculum: conduct, skills, unit maps, keys, exercises |
| `content/media/` | `asset://…` pictures and recordings |
| `services/classroom-core/` | the OS, the tool surface, the database |
| `services/agent/` | the Hermes adapter and the turn renderer |
| `services/speech/` | TTS and ASR behind provider seams |
| `services/vision/` | face templates, never photographs |
| `apps/classroom-ui/` | the projected room and the adult console |
| `docs/` | why it is like this — start with NORTH-STAR |

---

## Where the truth is written

Two documents are living and everything else is history:

- **[docs/NORTH-STAR.md](docs/NORTH-STAR.md)** — why this exists, who it is for,
  and NS-1…NS-7. If anything contradicts it, the other thing is wrong.
- **[docs/STATE.md](docs/STATE.md)** — what is actually wired, measured, and
  still broken. Paste it into a new agent chat and nothing else is required
  reading.

[`docs/decisions/`](docs/decisions/) holds the calls that were hard to make and
why, [`docs/research/external/`](docs/research/external/) holds commissioned
research kept as evidence rather than doctrine, and [`docs/archive/`](docs/archive/)
is provenance only — never cook from it.

---

## Testing

```bash
cd services/classroom-core && python -m pytest -q
cd services/agent          && python -m pytest -q
cd services/speech         && .venv/bin/python -m pytest tests/ -q
cd services/vision         && .venv/bin/python -m pytest tests/ -q
cd apps/classroom-ui       && pnpm exec tsc --noEmit
```

Green tests are the floor, not the evidence. Six defects found on 2026-08-20 —
including one that made the teacher **completely mute while the logs reported
success** — were invisible to every test and only appeared on a real boot. The
things that catch those live in `tests/node/`:

```bash
./scripts/teacher-up.sh
python3 tools/build_pupil_conversation.py --script scripts/pupils/spoken.txt -o /tmp/pupil.wav
PUPIL_WAV=/tmp/pupil.wav node tests/node/a_child_talks_to_her.mjs   # a spoken lesson
node tests/node/projector_reads_as_a_classroom.mjs                  # what a child sees
./tools/speech_roundtrip.py                                         # TTS -> ASR, no model credit
```

`speech_roundtrip.py` matters more than it looks: the speech stack is local and
free, the teacher is not, so voice and hearing questions get answered there
rather than by paying for a live lesson to discover the microphone was wrong.

---

## Privacy, and it is not optional

- **No raw child speech is stored.** Evidence is categorical — an objective, an
  outcome, and how it was elicited. What a child actually said exists for the
  length of one turn.
- **No photographs.** `services/vision` keeps normalized face embeddings and
  nothing else, in their own database, and deleting a child cascades to their
  templates. An embedding is not anonymisation.
- **Enrolment is consented and deliberate.** `consent_confirmed: true` and a
  reference to the signed paper are in the request *type*, so a caller cannot
  omit them. The camera only ever matches; it never enrols silently.
- **Uncertain identity means no student-memory write.** Losing a data point is
  cheap. Attributing one child's failure to another is not.
- The teacher never receives a face, an image, an embedding, or a name to match
  to a person. She receives an id, and through it that learner's record.

---

## Status, honestly

She teaches a full period through a real microphone, in two languages, with
material on the board and honest marking. Measured, not asserted — the numbers
and the failures are in [STATE.md](docs/STATE.md).

What is not done: a class of 20–40 children (a session holds one learner), the
~19 s a child waits for an answer (the hosted model is ~95% of it; local Gemma
is the way out), and a Vietnamese ASR score that is well short of the English
one. None of that is hidden anywhere in this repository.
