# A period is a thing she names, not a field Core understands

**2026-08-19.**

## The problem

Nothing in the system knew which of a unit's three periods it was in. No
`period_index`, no `lesson_index` — the unit is one `unit_id`, and the three
periods exist only as prose in `map.md`. So she could not stay in Lesson 1,
because nothing told her Lesson 1 was where she was.

The obvious fix is a `period` field on the session. That is a state machine with
one variable, and the founding decision of this project deleted the state
machine (`teacher-agent-not-cassette.md`, and the owner's own words: *"không có
statemachine, t cần pure agent"*).

## What we built

**`PERIODS_HELD`** — the count of *ended* sessions on this unit — one line in
`_session_recall`, beside `PERIOD_MINUTES`. Core opened and closed every one of
those rows; counting them is the same species of act as reading the clock.

**The map says what the number means.** `map.md` already has "The three
periods". One prompt sentence connects them: *"PERIODS_HELD is how many periods
this class has already finished on this unit; the unit map says what each period
is for."* She reads the count, reads the map, and writes the conclusion into her
own `plan` — which survives a restart and which Core already never reads.

**`THIS_PERIOD`** ships with it: per-objective attempt counts from this
session's rows. The map's own pacing law is *"Time is not the measure; attempts
are"*, and it was unexecutable because nothing counted attempts.

## The line, as a reusable test

> **Provenance** — Core may compute only facts it witnessed itself: the clock,
> counts of its own rows, what is on the board, who spoke. Meanings are authored
> in markdown, or written by her.
>
> **Consumption** — the value may appear on the right-hand side of *show her*,
> and **never inside a Core `if`**. Mechanical check: delete every read of the
> field except the line that prints it into recall. If the room's behaviour
> changes at all, it was a state machine.

`period: 1` that Core stores and shows passes. `period: 1` that filters which
objectives `record_evidence` accepts, or picks which file goes into `READ_NOW`,
or gates `say(closing)`, fails.

## Rejected: `l1.md` / `l2.md` / `l3.md` chosen by Core

The moment `render_teacher_turn` puts `units/<unit>/period-2.md` into `READ_NOW`,
Core owns the count→curriculum mapping and the map no longer does. Splitting the
period prose into files **she** opens is a fine authoring decision later; it is
not the mechanism.

## Rejected: a Core-enforced period boundary

Not merely inelegant — **wrong by the curriculum's own text.** `map.md` commands
cross-period teaching: Period 2 opens by recalling Period 1, and the exit says
*"carry the weakest objective into the next period's opening"*. A Core gate
would refuse moves the authored unit requires.

## The caveat, named with its measurement

`PERIODS_HELD` means "period 2" only while one session ≈ one timetable period.
The stand-in for a timetable today is `REOPEN_AFTER_CLOSE_S = 600`: close and
reopen three times in an afternoon of testing and the unit reads as finished.
Log ended-session durations; if the median is minutes rather than about an hour,
the count is lying, and the timetable NORTH-STAR §2 already names becomes a
prerequisite rather than a nice-to-have.

Abandoned sessions — the two-hour stale close — count as held. Deliberately: a
period that was interrupted still happened to the class.

## What this does not fix, and what did

A period is ~an hour, which is 15–25 moves of hers. Knowing *which* period she
is in does not give her a way to *fill* one. Two things did, the same day:

- **`say(wake_in_s)`** — she asks the room to hand her the next beat. Without it
  her only wakes were a child speaking, one 7s nudge, and a 45s silence floor,
  so a choral drill was three rounds of a silent classroom and she never started
  one.
- **`skills/prepare-a-period/SKILL.md`** — NS-6 has listed this skill since the
  beginning and it did not exist. It prescribes the plan shape: phases with
  minute budgets and a `NOW=` marker, which turns `PLAN` into a program counter
  she owns and Core never reads.
