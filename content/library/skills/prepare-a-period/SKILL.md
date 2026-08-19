---
name: prepare-a-period
description: Decide what this period is for, and write the plan you will actually run.
when: a period is about to start, or has just started and you have no plan yet
version: 1
---

# Prepare a period

A period is about an hour. That is fifteen to twenty-five moves of yours, not
four. If you finish everything you meant to do in six exchanges, you did not
teach a period — you read out a vocabulary list.

Before anyone arrives, or on your first turn if nobody prepared, do this.

## 1. Find out where this class is

`PERIODS_HELD` is how many periods this class has already spent on this unit.
The unit map says what each period is for. Nought means today is the first one.

Then read what they actually did: `SKILL_CARD` is coverage, not mastery.
`supported=1` is **one attempt on one day** — that is exposure, not retention.
An objective is worth calling covered when they produced it more than once, on
more than one day, and at least once without you having just said it.

## 2. Choose one period's worth, and no more

Take the objectives the map gives **this** period. Not the unit's whole list —
the map's later periods exist because a child cannot hold six new functions in
an hour.

Two new items per ten minutes is the ceiling. If you are teaching a third thing
in the first quarter of an hour, you are moving too fast for the room, however
well the last answer went.

## 3. Write the plan

Write it with the `plan` tool. Nothing in the room acts on it — it is yours, and
it comes back to you every turn, so it is where you keep your place.

Give it phases with minutes, and mark where you are:

```
P1 open+recall 0-10 | P2 model with the recording 10-20 | P3 choral x3 20-30 |
P4 practice + exercise 30-45 | P5 close 45-60   NOW=P2
```

Move `NOW` when you move. If you find yourself at `NOW=P5` after eight minutes,
that is the signal to go back, not to finish early.

## 4. Pull the material before you need it

Look at the map's material table and decide **which** picture and **which**
recording each phase uses. A period that shows one picture for an hour is a
period the class stopped looking at after ten minutes.

The recordings are not decoration. A child in a room with no English speaker
needs to hear a voice that is not yours saying the same words — that is what the
recordings are for, and it is why the map names one for nearly every activity.

## 5. Then teach it, and change it

The plan is a plan, not a rail. Revise it whenever the room tells you something:
they got it faster than you thought, they did not get it at all, one child is
lost. Re-write it with `plan` and carry on.

The one thing not to do is quietly abandon it and follow whatever the last child
said. That is how an hour becomes six turns.
