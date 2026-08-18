---
date: 2026-08-16
topic: teacher-agent-not-cassette
status: locked
---

# Owner correction: teacher is an agent

## Context

Layer 1 was sold as “10/10 Hermes called `classroom_propose_move`.”
Layer 2 started gluing that to a Market Food `lesson_run.json` graph and
calling “banana → goto:scaffold” a teacher. The owner rejected both as
the product: that is a cassette with garnish. Hermes exists because it
is an agent harness.

Gemini 3.1 Pro (`agy --model gemini-3.1-pro-high`) council agreed:
NS-1-as-tape inverted the architecture; Core must be OS; library is a
codebase; fail policy is notify + restart.

## Decision

- Hermes teaches. Core does not.
- Curriculum = md maps + deeper files + `asset://`. Not a live graph.
- AI fail → tell the adult, keep the room, restart AI. No authored tape.
- New Layer 1 = library tools + one learner text + restart gate.
- Old 10/10 probe = harness smoke only.

## Docs touched

- `docs/NORTH-STAR.md` (NS-1, NS-3, success #4, Core role)
- `docs/decisions/teacher-agent-not-cassette.md` (new lock)
- `docs/decisions/option-b-classroom-runtime.md` (topology kept, cassette dropped)
- `docs/STATE.md` (rewritten)
- `docs/archive/teacher-agent-plan.md` (cook plan)
- `docs/research/notes/2026-08-16-teacher-loop-roadmap.md` (superseded banner)
- `docs/README.md`

## Not done today

No runtime cook. `layer2-text-station` still has graph WIP; do not merge.
