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
- [ ] Chromium acceptance reruns pass when local credentials/services are available.
- [ ] Docs distinguish fixture composition, manual ideal proof, and room validation.
- [ ] The checked-in environment template names every ideal-hosted preflight
  variable without providing a credential or silently opting a developer into
  raw-transcript mode.

## Current operational blocker

The local runtime dependencies are present, but the live proof is deliberately
blocked until a developer supplies the hosted-Hermes credential and explicit
`hosted_ephemeral_transcript` acknowledgement. The template is part of this
phase so the next operator can configure that profile intentionally; it is not
evidence that the live gate passed.
