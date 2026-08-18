# archive/ — superseded documents

**Do not cook from anything in this folder.** Every file here was accurate once
and is wrong about something now. They are kept because the reasoning trail is
part of the product's evidence — a competition judge asking "how did you decide
that?" deserves an answer, and deleting the record would remove it.

Living doctrine is exactly two files, plus `decisions/`: [`../NORTH-STAR.md`](../NORTH-STAR.md) and
[`../STATE.md`](../STATE.md).

Archived 2026-08-18.

| File | What it was | Wrong about |
|---|---|---|
| `HANDOFF.md` | The paste-into-a-new-chat brief, 2026-08-18 | Absorbed into `STATE.md`. Kept because it carried the owner's no-buttons correction before it became a decision doc |
| `autonomous-classroom-roadmap.md` | The living layer order 0→7 | Absorbed into `STATE.md`. Its "do not re-bias" table is still good advice |
| `teacher-agent-status.md` | What was wired, 2026-08-17 | Absorbed into `STATE.md` |
| `teacher-agent-plan.md` | Layer 1 phases A–H, "next = voice" | Voice wiring closed 2026-08-18 |
| `cook-until-done.md` | Layer 3 voice cook brief | Already cooked. Says "do not start AIRI" — the AIRI body is on Stage now |
| `classroom-is-the-room.md` | Interaction contract, 2026-08-18 | Half-superseded the same day. `/classroom` **is** the room (still true); Start + Hold-to-talk as the teaching contract (rejected by the owner). Replaced by `decisions/2026-08-18-room-runs-itself.md` |
| `option-b-implementation-status.md` | Implementation handoff, 2026-08-13 | Cassette era |
| `state-of-the-project.md` | Snapshot, 2026-08-11 | Pre-teacher-agent |
| `tracker.md` | Living tracker, 2026-08-11 | Pre-teacher-agent. **Still worth reading for its measured latency numbers and its record of four silent seam bugs found under 293 passing unit tests** |
| `phase-1-plan.md` | Phase-1 plan, 2026-08-11 | Cassette era |
| `execution-plan.md` | Adversarial review of the build plan | Cassette era. Its "Hermes adapter over 800 lines" trigger is still a useful smell |
| `open-questions.md` | Spikes to run before building | Background, not a queue. Several are answered in `decisions/` |
| `composed-smoke-runbook.md` | Runbook for the compiled-lesson smoke test | Cassette era |
| `product-smoke-runbook.md` | Runbook for the product smoke test | Cassette era |
| `2026-08-16-teacher-loop-roadmap.md` | Research arguing teacher-loop-first | Superseded the same day by `decisions/teacher-agent-not-cassette.md` |

## The recurring failure this folder documents

Four of these files claimed to be the current status at the same time. Three
described the interaction contract, two of them written on the same day and
contradicting each other. That is not a documentation problem — it is what
happens when a project has no single living document, and it cost real hours of
agents reading the wrong file and building the wrong thing.

The rule now: **one bible, one living doc, append-only decisions, everything
else archived on the day it stops being true.**
