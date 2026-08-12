---
date: 2026-08-12
session: option-b-product-hardening
---

# Journal: 2026-08-12 — Option B Product Hardening

## Context

Option B is now an implemented classroom-runtime boundary, not merely an architecture proposal: Hermes remains a replaceable sidecar, Core owns authority and durable learner state, Stage owns physical speech, and Control owns the microphone. This session focused on making those boundaries enforceable while separating mechanical evidence from evidence that is valid in a real classroom.

## What Happened

- Protocol v2 added activity-generation, utterance, speech-turn, and playback correlation across Core, Stage, and Control. Listening and timers now arm from the matching terminal playback event, stale input is rejected, and exact-turn cancellation supports bounded PTT barge-in.
- Voice ownership was narrowed to one adaptive source and one physical renderer. Stage emits keyed playback acknowledgements; Control suppresses capture during output and through an echo tail.
- Privacy moved into runtime constraints: hosted requests use minimum pseudonymous context with `store: false`; raw audio/transcripts remain ephemeral and are excluded from durable evidence, recalled context, and hosted summaries; learner memory cannot widen across students.
- Focused evidence is green: Option B/Hermes tests reported 18 passes, Core runner and learner-memory suites 41 each, Hermes non-live 77, and AIRI 165 plus typecheck/build. The production smoke harness and zero-false-accept room gate now exist.
- The available product-smoke artifacts are explicitly `environment-blocked` by forbidden loopback binding. The stored room result covers clean synthetic Piper speech, not children or a noisy classroom. Neither artifact closes its release gate.

## Reflection

The strongest progress is structural: correlation, authority, privacy, and failure behavior are now explicit contracts with focused verification. The largest risk is evidentiary, not another missing code slice. Passing component suites cannot establish one physical voice, cancellation-to-silence, echo safety, child-speech grading, or classroom latency. Synthetic speech is useful regression evidence, but calling it classroom validation would repeat the project’s recurring seam mistake: measuring something plausible that answers a different question.

## Decisions

| Decision | Rationale | Impact |
|---|---|---|
| Keep Option B and Core as the sole authority. | The narrow sidecar/MCP boundary preserves deterministic teaching and fail-closed state changes. | Provider and Hermes failure cannot own or halt the lesson. |
| Keep adaptive speech single-owner and fully correlated. | Dual voice paths and unkeyed completion create interruption, stale grading, and echo hazards. | Every turn has one Stage playback lifecycle and one terminal outcome. |
| Treat privacy as an executable data boundary. | Children’s audio and transcripts are high-risk data, not ordinary telemetry or memory. | Hosted context stays minimal; raw transcript persistence remains prohibited. |
| Do not promote mechanical checks to ecological evidence. | Fake services, clean synthetic speech, and virtual clients cannot reproduce children, rooms, microphones, speakers, or target hardware. | Release remains blocked despite focused green suites. |

## Next

1. Run the hanging TestClient lifecycle suites on CI or the appliance image.
2. Execute a real-browser composed smoke across Stage, Control, Core, AIRI, Piper/ASR, and pinned Hermes, including playback correlation, barge-in, cancellation-to-silence, and agent-loss fallback.
3. Collect consented child/noisy-room recordings and require zero false accepts; verify that no raw transcript is recoverable afterward.
4. Run three target-hardware rehearsals and measure end-to-end voice latency, echo/AEC behavior, memory, thermals, and sustained load before making release or local-Gemma claims.
