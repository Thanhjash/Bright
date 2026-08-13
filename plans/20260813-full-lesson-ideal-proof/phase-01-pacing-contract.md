---
phase: 1
title: "Pacing contract and authored closure"
status: completed
priority: P1
dependencies: []
---

# Phase 1: Pacing contract and authored closure

## Overview

Make Core honor the authored lesson arc before trying to prove a full session.

## Related code files

- Modify: `services/classroom-core/class_session.py`
- Modify: `services/classroom-core/runner.py`
- Modify: `services/classroom-core/tests/test_class_session.py`
- Modify: `tools/lesson-play/lesson_play.py` and/or focused contract tests as needed

## Implementation steps

1. Write failing tests for Market's canonical route and closure transition.
2. Define and encode the inclusive teaching-window/closure-reserve semantics.
3. Route catch-up through authored deterministic choices only; emit its reason.
4. Cancel stale old-generation narration before entering closure.

## Success criteria

- [ ] No implicit minute-36 cutover drops an authored path.
- [ ] Closure cannot overlap stale narration.
- [ ] Core deterministic suite passes.
