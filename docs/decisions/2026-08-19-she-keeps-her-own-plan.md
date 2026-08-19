# She keeps her own plan, and `BEATS` is gone

**2026-08-19.** Replaces the in-RAM `BEATS` log.

## The problem

Every turn she was handed `BEATS` — the last eight moves, written **by Core,
about her** — plus `SKILL_CARD` and `PERIOD_MINUTES`, and had to re-infer from
that where she was in the period. That is why teaching wandered: an agent
reconstructing its own intention from a log of its own past actions has no
intention, only a history.

A coding agent does not run on a state machine either. It keeps a todo list: it
writes one, revises it, and it survives across turns. That is the analogy this
project chose, and it was the missing piece.

## Why not Hermes' `todo`

Checked upstream: the `todo` toolset has **no table of its own**. It lives in
process memory and is reconstructed each turn by reading backwards through the
conversation for the last `todo` tool result. So it sits in *the context window*
and in *the harness's private store*, which are exactly the two places NS-5
forbids.

A lesson plan is a child's data. It must survive a power cut, and it must
outlive a harness NS-4 says is replaceable.

## What we built

`plan(plan: string)` — one tool, one required string, max 1200 characters,
stored in `lesson_plans` in `bright.db`, keyed by session, revision-counted.

**Core stores it and hands it back. Core never reads it.** It arrives as `PLAN=`
in the turn input and appears on `/teacher/status` for the adult. Nothing
branches on a word of it.

That is the line between an agent and the cassette this repo deleted, so it is
a test and not a comment: two wildly different plans — one of them naming tools,
phases and a time limit — must leave the room in identical state. The moment
anything grows an `if "exercise" in plan`, that test fails.

`resume_teacher_session` reloads it. "Restart the teacher, never the lesson" now
includes what she meant to do next; previously a restart destroyed exactly that.

A `plan` written with no session to store it in is **refused**, not accepted and
dropped. Failing closed: a plan that returns `ok` and vanishes at the next
restart is worse than no plan tool.

## What was removed

`BEATS`, `note_beat`, and the `beats` list. Replacing a log Core writes *about*
her with an intention *she* writes is the whole point; keeping both would be the
clinging we agreed to stop. `prior_evidence` went with it — it had no other
reader.

The privacy property `BEATS` was carrying is kept by its test, renamed: no raw
child words leave the turn.

## Live, first period after the change

```
census  event=class_start  tools=7  read_library ×4, plan, show_image, say
census  event=student      tools=3  record_evidence, plan, say
status  plan = "1. Review greeting & wellbeing (done). 2. Introduce
                leave-taking ('Goodbye' / 'Bye'). 3. Roleplay farewells
                with characters. 4. Wrap up."
```

She wrote a plan unprompted on the opening turn, and revised it two turns later
after the class answered — batched into the same message as `say`, so it cost no
extra round-trip.
