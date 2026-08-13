---
date: 2026-08-14
session: ideal-composed-hosted-evidence
---

# Journal: 2026-08-13 — One-Turn Ideal Composed Evidence

## Context

Bright's North Star is an autonomous AI teacher for 20–40 children, not a
convincing isolated demo. The missing product boundary was whether a hosted Hermes
proposal could participate in a real browser speech turn without a fabricated
playback acknowledgement.

## What happened

- The operator acceptance lane started two persistent Chromium contexts through the
  visible Stage and Control UI.
- A generated adult Piper WAV was used only as Chromium's fake microphone device. It
  passed through real browser `MediaRecorder`, Whisper, Core grading, hosted Hermes and
  its narrow MCP tool, Piper, AIRI browser playback, and Stage's causal WebAudio ACK.
- The scrubbed result artifact at
  `tests/.artifacts/ideal-composed/result.json` reported `ok: true`; it saw real ASR
  and Piper HTTP 200 responses, a correct Core outcome, one Hermes MCP proposal and
  agent speech turn, Stage playback completion at event 116, and the following Core
  commit at event 117.
- Correcting live policy placement to `gateway.api_server.extra.bright_live` left the
  inspected ephemeral Hermes runtime database with zero stored messages.

## What this proves

One ideal-condition composed turn has a real causal chain. In particular, Core did not
commit the model-proposed move until after the Stage browser reported that the agent
audio had actually begun and then completed. It also demonstrates the intended Hermes
boundary: a short terminal MCP proposal, not agent control of the DOM or Core state.
The artifact is Git-ignored and scrubbed: it contains only opaque slots, event ordering
and outcome categories—never raw audio, transcript, identifiers, cookies or secrets.

## What it does not prove

The input was synthetic adult Piper speech, not a child or a real room. The run does
not establish microphone/speaker acoustics, child ASR accuracy, no-false-accept,
physical-device reliability, a full Market lesson, fair participation for 20–40
learners, or autonomous classroom teaching. Zero stored messages in this ephemeral
runtime is evidence for that run/profile, not a complete data-retention audit.

The acceptance launcher used a 90-second cold-provider budget and a 0.65 confidence
threshold only for its generated fixture. The product remains fail-closed at the
6-second agent budget and 0.75 correct threshold. The fixture must not lower either
production bar.

## Next

1. Repeat with `manual-physical-mic` and record only scrubbed evidence.
2. Cover every Market oral path, recovery path and cancellation/degrade path.
3. Run full-session and consented room-corpus gates; require zero false praise for
   wrong or silent answers before any competition-ready claim.
