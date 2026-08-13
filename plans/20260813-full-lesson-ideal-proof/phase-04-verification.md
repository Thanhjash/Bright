---
phase: 4
title: "Independent verification and evidence"
status: in_progress
priority: P1
dependencies: [1, 2, 3]
---

# Phase 4: Independent verification and evidence

## Overview

Run Core, agent, AIRI/UI, browser and acceptance gates; update only claims directly
supported by the resulting artifacts.

## Success criteria

- [ ] Targeted and shared-module deterministic tests pass.
- [x] One Chromium one-turn acceptance passes with the locally configured hosted
  provider; the scrubbed artifact is
  `tests/.artifacts/ideal-composed/result.json` (Git-ignored).
- [ ] Rerun the three-turn lane deterministically and retain its own scrubbed PASS
  artifact. One observed three-turn pass was followed by a timeout rerun that overwrote
  the single result artifact with `ok: false`; it is not repeatability evidence.
- [ ] Run the separate manual-Market gate.
- [ ] Docs distinguish fixture composition, manual ideal proof, and room validation.
- [ ] The checked-in environment template names every ideal-hosted preflight
  variable without providing a credential or silently opting a developer into
  raw-transcript mode.

## Current evidence boundary

The one-turn gate was run with the locally configured hosted provider and explicit
`hosted_ephemeral_transcript` acknowledgement. It is evidence only for a synthetic
adult fake-microphone turn across the real browser, speech, Core and Hermes boundaries;
it is not evidence for a physical room, children, the full Market lesson or a 20–40
learner autonomous class. The environment template remains a preflight aid, not an
opt-in to raw transcript handling.
