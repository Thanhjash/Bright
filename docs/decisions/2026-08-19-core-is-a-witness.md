# Core is a witness, not a marker

**2026-08-19.** Written after a live lesson in which every observation the
teacher had ever recorded was identical.

## What happened

I played a Grade-3 pupil. Ten rows in the database, ten of ten `correct` +
`mode=name`. Two of them are flatly wrong:

- The pupil said **"Hello"** — no name — and `greet-and-name` was recorded
  `correct`, `mode=name`. `keys.md` says that objective is `wrong` for *"only a
  greeting"*, and that `mode: name` applies **only if they said it**. Its
  "Things that are not evidence" list even opens with *"Greetings to you at the
  start of class"*.
- The pupil said **"em chưa hiểu"** (*I don't understand*) and `take-leave` was
  recorded `correct`. The child took leave once and failed to understand once;
  both were filed as success.

That memory feeds `SKILL_CARD`, which is injected every turn, which is how she
decides what to teach next. Three turns later her own written plan said
*"Review greeting & wellbeing **(mastered)**"* and she taught a three-lesson
unit in six turns. **False evidence → false mastery → she skips the teaching.**
Personalisation is why this product exists, so the defect voids the product.

## The line

> **Core may refuse a claim about the room it witnessed. Core may never rule on
> the meaning of what a child did.**

The test, which is the generality test NS-6 already gives us: *could this check
be written identically for a maths unit, without Core reading any unit file's
content?*

- *"This unit has no objective called `take-leave`"* — passes. A catalog lookup.
- *"The utterance `Hello` does not satisfy `greet-and-name`"* — fails.
  Falsifying it needs to know the objective demands a name, which lives in
  `keys.md`, which is curriculum, which `tests/test_no_unit_pedagogy.py` exists
  to keep out of Python.

Sharper: **Core is a witness, not a marker.** A witness can testify *no act
occurred*, *this is already recorded*, *the claim names a channel that carried
nothing*. A witness cannot testify *the act was insufficient*.

## What Core now refuses

| Refusal | The fact Core witnessed |
|---|---|
| no evidence on a turn with no student utterance | she is stateless per turn, so a row written where nobody spoke is about an utterance that did not happen |
| no evidence on any system event (`heartbeat`, `class_start`, `prepare`) | a system event is not a child speaking. Only `heartbeat` was refused before |
| one row per `(objective, turn)` | Core's own ledger. **Not** `(objective, session)`: wrong at minute 10 and right at minute 30 after scaffolding *is* the learning, and a session key destroys it |
| `mode` is required | it was optional, and `ATTEMPT_MODES = {name, point}` silently dropped modeless rows out of `SKILL_CARD` — evidence she recorded evaporating from the one thing that reads it |
| the row carries the **real** turn id | `response_turn_id` was `f"ev-{uuid4().hex[:12]}"` — a fresh random value on every call. The unique index on `(session_id, response_turn_id, skill)` could therefore never fire once, and no row could be traced back to the utterance it claims to be about |

## The refusal we decided NOT to add

**Core must not refuse `greet-and-name`/`correct`/`mode=name` on "Hello",** even
though the claim is a rubber stamp and Core is holding the transcript.

The average engineer loads `keys.md` into Core and string-matches
`STUDENT_SAID`. It fixes the observed bug in an afternoon and is the most
destructive change available in this repository:

- Core becomes the second teacher NS-1 forbids, and curriculum truth enters
  Python.
- NS-7 dies: software now contains language knowledge, and every new unit,
  subject and language pair extends a matcher. That is the 40-million
  logistics failure, not a philosophical one.
- It builds the NS-5 decoder bias into the **arbiter** — a curriculum-primed
  matcher grading fumbled ASR by string distance, with *"communication over
  correctness"*, the first rule in `keys.md`, as its first casualty. A `near`
  child fails a regex forever.
- It caps evidence quality at regex quality permanently, and removes the
  pressure to make her judgement good — which is the product.

> **Make false evidence impossible where Core is the witness, auditable
> everywhere else, and never adjudicated by the room.**

## What carries the rest

Not a refusal — a workflow precondition and better authoring:

- **She reads the key before she judges.** `READ_NOW` names
  `units/<unit>/keys.md` and `skills/judge-a-response/SKILL.md` on the first
  student turn. Core reads neither; it names paths, the way this repo's own
  tooling refuses an Edit to a file that was never Read.
- **`keys.md` closed the echo hole**: a child repeating the phrase you said in
  your own last line is your model working, not the child producing. Elicit it
  again later, cold. And: *one row is one attempt, not coverage.*

## Still open

`format_skill_memory` reports coverage — `supported=N` — and coverage reads as
mastery. NORTH-STAR §2 tier 2 blesses `days=N` / `last=<date>` as legitimate
derived state (*"a calculation, written by nobody"*), and that is the honest
middle: Core supplies the arithmetic, the profession supplies the meaning in
`judge-a-response`. Not built yet. The moment a number acquires a cutoff it
becomes the knowledge tracing that `2026-08-18-three-stores.md` killed.
