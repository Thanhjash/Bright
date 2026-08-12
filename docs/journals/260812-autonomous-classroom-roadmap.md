---
date: 2026-08-12
session: autonomous-classroom-vertical-slice
type: implementation-reflection
status: complete
---

# Autonomous Classroom Vertical Slice — Implementation Reflection

## Context

Bright's North Star remains one autonomous AI teacher running a 35–45 minute lesson for 20–40 children around a shared board. Option B is now being implemented as the stable product seam: Core owns classroom authority, Hermes proposes one bounded teaching move, Stage owns speech playback, and dedicated ASR turns assigned speech into correlated text. Local Gemma remains a provider change behind Hermes, not a reason to delay the product spine.

The persistent execution roadmap is [`docs/4-build/autonomous-classroom-roadmap.md`](../4-build/autonomous-classroom-roadmap.md). This repository has no `plans/` directory; this journal records implementation learning rather than duplicating that roadmap.

## What happened

- Protocol v3 made class session, turn assignment, capture lifecycle, capability ownership, and exactly-once correlation explicit. Lesson schema versioning is independent from transport protocol versioning.
- A Core-owned class/session controller, roster and attendance model, deterministic participation ledger, stage/control leases, persisted decisions, and safe playback-gated transitions replaced the implicit single-learner flow.
- Hermes was narrowed to one terminal `classroom_propose_move` capability. Model prose is not sent directly to children: Bright validates a bounded teacher line, plays it, waits for physical playback completion, then applies the semantic move.
- A 17-activity, 37–39 minute autonomous lesson now exercises group, pair, named and recovery paths. Its curriculum approval remains deliberately `draft`, so release lint fails honestly.
- Control/Stage and the answer-station voice path now model readiness, assignment, capture and synthetic provenance. Synthetic transcripts are accepted only in an explicitly acknowledged development policy with a fixture identifier.
- The Hermes runtime patch is pinned to an upstream commit and was verified against a clean temporary checkout. It disables persistence, background work and extra tool surfaces for live classroom turns.

## Independent-review surprises

1. Constrained transcript matching improved scoring but did not reduce Whisper latency; the real near-term latency lever is the ASR model/profile and the state-driven capture window.
2. Playback success is a semantic safety boundary, not UI telemetry. Advancing a lesson before a real completion ACK can produce a silent autonomous class.
3. Stage audio ownership and Control input ownership must be separate leases. Requiring the answer station to own the Stage lease would make legitimate capture impossible.
4. A polished Control screen was still unusable until Start carried a real class roster and attendance. Autonomous teaching begins at setup, not at the first board.
5. A protocol smoke with fabricated playback ACKs is useful, but it cannot prove browser, device, audio, ASR or room behavior.

## Mechanically green at this checkpoint

| Evidence | Result |
|---|---|
| TypeScript/Python event-name parity | 35 event types on both sides; no diff |
| Contract and workspace type checking | clean at the recorded checkpoint |
| Lesson toolchain self-test | 20/20 expected rules pass |
| Autonomous lesson simulation | five behavior paths reach completion with zero stalls/unhandled branches |
| Autonomous lesson contract tests | 7 pass, including all taught food requests, fail-closed schema and draft release gate |
| Product protocol smoke harness | 6 pass |
| Protocol v3 capture endpoint | pass |
| Core class-session tests | 7 pass after synthetic provenance tightening |
| Classroom Core full suite | 224 pass |
| Agent full non-live suite | 82 pass; 4 live-provider tests intentionally deselected |
| AIRI bridge | 165 pass; typecheck and build pass |
| Chromium Protocol v3 flow | 2 pass with mocked speech/browser contract |
| Content contract | 7 pass plus lesson-lint self-test |
| Pinned Hermes artifact | `0.20.0+bright.1`; patch/wheel hashes recorded against upstream `03fa32c92dd445eb64c7f67434dd91b32c40701d` |

These results prove contracts and deterministic behavior, not classroom readiness.
The Chromium flow is mocked; it does not prove real TTS, ASR, room acoustics or hosted
Hermes transport.

The final independent review also caught and closed P0 contract faults before this
checkpoint: agent transition was held until physical playback completion; Stage output
and Control input became distinct leases; Start acquired real roster/attendance; capture
deadline units were separated into absolute Ready and relative speech-onset values; raw
synthetic transcript required an acknowledged policy plus fixture provenance; and the
live MCP surface was reduced from stale multi-tool assumptions to one terminal proposal.

## Decisions reinforced

- No direct agent-to-child channel. Core remains the policy and state authority even when Hermes or Gemma becomes more capable.
- No correctness claim from group/choral or uncertain input, and no learner-memory mutation without a correlated assigned turn.
- No silent progression: required speech retries/falls back, then visibly safe-pauses.
- Dedicated ASR is valid NOW. Under `hosted_semantic`, Hermes receives only a graded
  semantic outcome; raw synthetic transcript can reach it only in the acknowledged
  fixture-backed development mode. Local Gemma/native audio must pass the same policy
  and provider contracts later.
- Synthetic fixtures accelerate development but must remain visibly marked and impossible to confuse with ecological evidence.

## What remains product and release proof

- Curriculum approval and teacher review of the real lesson and assessment rubric.
- Hosted-provider conformance for the built, hashed patched-Hermes artifact.
- Class-aware longitudinal memory, checkpoint restore, and full execution of authored
  pacing/recovery metadata.
- A composed run with real Chromium Stage and Control, AIRI, TTS playback events, ASR and Hermes; no fabricated ACKs.
- Consented child/noisy-room testing on target microphones and speakers, with zero false acceptance for wrong or silent answers and measured latency distributions.
- Three consecutive full 35–45 minute rehearsals for a 20–40 learner roster with no routine adult teaching action.
- Cold boot, service/model failure, network loss, power-loss recovery, signed update/rollback, privacy deletion and licence/provenance evidence.

The implementation has crossed from architecture proposal into an honest vertical slice. The next milestone is not “more features”; it is converting this deterministic spine into repeatable ecological and release evidence without weakening its fail-closed boundaries.
