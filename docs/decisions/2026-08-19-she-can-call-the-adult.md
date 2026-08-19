# She can call the adult

**2026-08-19.** The eleventh tool. NS-3 says adding one requires a decision doc;
this is it.

## The gap

NORTH-STAR §1 has listed five situations since the first draft where she must
stop teaching and hand the room to the adult:

> physical danger · a child in visible distress · **any disclosure suggesting
> abuse, neglect, or a serious wellbeing concern** · equipment failure beyond
> one retry · class-wide disengagement that pacing changes have not fixed

`content/library/skills/escalate-to-the-adult/SKILL.md` tells her exactly how to
do it, and opens with *"read this now, before you ever need it"*.

**She could not do it.** `say` reaches the loudspeaker. The board reaches the
projector. Neither reaches a person. There was no tool, no field, and no path.
For two days the safety policy of a system built for children has been a
document instructing the teacher to perform an action she physically could not
perform.

Doctrine with no mechanism is not a policy. It is a wish.

## The tool

```
call_the_adult(reason, detail?)
  reason: danger | distress | disclosure | equipment | cannot_reach_the_class
  detail: one short line for the adult, in the school language
```

**A separate tool, not a flag on `say`.** The tripwire in NS-3 is explicit: a
field on `say` may be the line, a boolean about the line, or the chalk. An
escalation is none of those — it is a different act, aimed at a different
person, and it must be refusable on its own without silencing her. She still
needs to say one calm line to the class while she waits, and that `say` must
work.

**The enum is short on purpose**, and it is the same five. A teacher who
escalates constantly is not autonomous either, and a list that grows becomes a
way to avoid teaching.

**`detail` goes through the same free-text check as everything else she
writes** — no URLs, no markup, no grade words, no child's words, no name. It is
read by a person on a laptop, not by a machine.

## What it does, and what it deliberately does not

Core stores the escalation and shows it on `/teacher/status`, where the adult's
watcher already looks, and `scripts/watch-teacher.sh` prints it in the school
language above everything else.

**It does not close the period.** Closing writes an ended session, and
`count_periods_held` counts those — a lesson abandoned to an adult is not a
period this class has had, and counting it would push the next real class onto
Period 2 having never held Period 1. The room stays exactly as it was: the same
board, the same picture, the same open session. The adult walks into what the
children were looking at, and the period can be picked up.

**It does not stop her speaking.** The class is still in front of her and still
needs one calm line while they wait. Silencing a teacher at the moment something
has gone wrong is the worst available behaviour.

**Only a person ends it.** Core sets nothing that clears the escalation by
itself. That is the point: the situations on the list are the adult's, and a
machine deciding it has been long enough is the machine taking the role back.

## What this replaces

Nothing — but it is the honest answer to a failure we were about to
mis-diagnose. In an empty room she loops: with nobody answering, she re-models
the same phrase, invents assets, and eventually reaches for `close-a-period`
because she has run out of ideas. The instinct to fix that with more
self-prompting is wrong, and the north star already said so:
**"class-wide disengagement that pacing changes have not fixed"** is on the
hand-over list. The right behaviour for a room she cannot reach is not to teach
harder at it. It is to call someone.

`NO_REPLY=<moves>, <minutes>` — a fact Core witnessed, added the same day — is
what makes that condition expressible to her at all, and it is the selector that
names `elicit-chorally` and `recover-a-wobble` in `READ_NOW` before she gets
there. The escalation is the floor under those, not a substitute for them.
