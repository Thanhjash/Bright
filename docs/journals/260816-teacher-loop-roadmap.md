---
date: 2026-08-16
topic: teacher-loop-first-roadmap
status: locked-for-execution
---

# Teacher-loop-first execution order

## Context

North Star is still a 20–40 learner autonomous classroom. The 1:1 text wedge and a
teammate TBLT/Global Success package are real inputs. A parallel ClassroomAI
screenshot (chat box + face overlay + llama.cpp) is the anti-pattern.

The 2026-08-14 1:1 WIP was parked on `wip/20260814-1to1-text-unproven`. `main` is
the Option B baseline (`0.20.0+bright.1`, one proposal tool).

## Decision

Execute in layers: text Hermes brain → thin text station → TTS then ASR → AIRI
body → 20–40 classroom → local Gemma → giveaway/legal.

Image, audio, and board writing are Core/Stage primitives driven by
`lesson_run.json` and legal `move_id`s. Hermes does not gain three media tools.
Student detectors are Layer 5 and never render on the projector.

## Docs

- Living order: `docs/4-build/autonomous-classroom-roadmap.md`
- Research: `docs/5-research/2026-08-16-teacher-loop-roadmap.md`

## Layer 1 follow-up (same day)

`tool_choice: required` on `bright.1` missed 1/10 live turns (provider
`completed`, zero tools). Wire-only `0.20.0+bright.2` pins the exact terminal
function. Second live probe: 10/10 + reconnect, timeout fail-closed, no
sentinel leak. 25-minute × 3 remains open.
