---
phase: 2
title: "Three-turn composed acceptance"
status: in_progress
priority: P1
dependencies: [1]
---

# Phase 2: Three-turn composed acceptance

## Overview

Prove three complete browser/speech/agent cycles with one repeatable known answer;
do not misrepresent the fixture as the Market curriculum.

## Related code files

- Create: a v3 multi-turn fixture under `tests/fixtures/`
- Modify: `tests/node/ideal_composed_acceptance.mjs`
- Modify: `scripts/ideal-composed-acceptance.sh`
- Modify: `scripts/ideal-hosted.sh`
- Modify: `tests/test_ideal_composed_acceptance_harness.py`

## Success criteria

- [ ] Per-attempt ordered evidence, real ASR/TTS, causal ACK and post-playback commit.
- [ ] Exactly three agent proposal cycles; no fake frames or raw text artifacts.
- [ ] Existing one-turn gate remains supported.
