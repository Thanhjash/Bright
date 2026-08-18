# Decision: the teacher is an agent, not a cassette

**Date:** 2026-08-16  
**Status:** LOCKED (owner correction)  
**Supersedes:** “Core plays `lesson_run.json` when the LLM is dead”; Layer 1 = one-tool `classroom_propose_move` probe; “adaptive” = pick an authored `goto`

---

## Decision

Hermes is the teacher. Classroom Core is the classroom OS. The curriculum
library is a codebase the agent reads. A compiled activity graph is not the
lesson, and it is not a substitute teacher.

This is the same shape as a coding agent in a large repo: maps and files to
retrieve, a small tool surface that actually does work, a human to talk to,
and a runtime that is not a second programmer.

## Why Hermes exists

If Bright only needed a fixed script plus an LLM to say the next line, we
would not run an agent harness. Hermes is here so the teacher can search,
read deeper, review, remember, and adapt — across many subjects later —
without a new state machine per unit.

## Failure policy

When the AI dies or times out:

1. Tell the facilitator honestly. Do not invent a teacher.
2. Keep the room up (board, session, last visual, sockets).
3. Restart / re-setup the Hermes sidecar and resume from OS snapshot
   (active unit, last student act, board).

There is no authored-tape fallback. `lesson_run.json` must not walk the
class “so the lesson still runs.”

## What Core must never do

- Own pedagogy
- Compile teaching into a rail (`available_actions` from a graph)
- Impersonate the teacher while Hermes is down

What Core does: session, bus, board/mic/speaker I/O, typed tool
side-effects, semantic student DB, safety rejects, health + restart.

## What Hermes must never do

- Write HTML/CSS/DOM
- Touch raw filesystem / browser / cron in the live classroom
- Invent syllabus outside the active unit map
- Be a second agent inside AIRI

## Tool direction

Kill “one terminal tool `classroom_propose_move` as the teacher.”

Live tools are few, typed, and executed by Core:

| Tool (working names) | Job |
|---|---|
| `read_library` | open a map / unit / rubric / key |
| `search_library` | find a deeper doc or `asset://` id |
| `present` | semantic board change (layout + slots, never paths) |
| `say` | one teacher line (Stage speaks later; text now) |
| `record_evidence` | write mastery / tags, never raw chat |
| `open_response` | invite the current learner to answer |

Generic Hermes `file` / `browser` / `terminal` stay off in class.

## Expert council

Gemini 3.1 Pro (via `agy`, 2026-08-16) reviewed this correction and
agreed: NS-1-as-cassette inverted the product; Layer 1 as a 10/10 wire
probe is not a teacher brain. Council tool list and restart sequence are
adopted with one tightening: library access is Bright MCP, not Hermes
generic filesystem.

## See

- Bible: [north-star.md](../NORTH-STAR.md)
- Living order: [autonomous-classroom-roadmap.md](../STATE.md)
- First plan: [teacher-agent-plan.md](../archive/teacher-agent-plan.md)
