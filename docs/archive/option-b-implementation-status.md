# Option B implementation status

**Updated:** 2026-08-13
**Status:** one ideal-condition composed hosted turn is evidenced; not release-ready

The locked boundary remains [Option B classroom runtime](../decisions/option-b-classroom-runtime.md):
Core is the only authority, Hermes is a replaceable reasoning sidecar, Stage owns
physical output, and Control owns answer-station input. This page separates code and
mechanical evidence from classroom, provider and governance proof.

## Implemented

- Protocol v3 across Markdown, TypeScript and Python: class/session state, roster and
  attendance, decision revision, exact turn assignment, capture lifecycle, capability
  leases, playback correlation and lesson-schema versioning independent of wire version.
- Core-owned `ClassSessionController` with explicit session/activity/response/agent
  states, atomic transitions, roster, attendance, deterministic fair selection,
  cooldown, participation ledger, exactly-once response claims and checkpoint writes.
- One narrow live Hermes terminal tool:
  `classroom_propose_move(turn_id, move_id, teacher_line)`. Core binds opaque legal
  moves, rejects stale/duplicate proposals, validates the teacher line, speaks it, and
  commits the semantic move only after matching physical playback completes.
- Pinned patched Hermes runtime `0.20.0+bright.1`, upstream
  `03fa32c92dd445eb64c7f67434dd91b32c40701d`, with live session persistence,
  chaining, background work, broad tools and post-terminal second inference disabled.
- Hosted-model data boundary: `hosted_semantic` sends only the graded outcome, never
  raw transcript. Synthetic raw transcript may reach Hermes only with `synthetic_dev`,
  explicit acknowledgement and a fixture ID, and is excluded from durable evidence.
- Stage output and Control answer-station input are separate expiring leases. Core
  issues exact assignments/capture requests; group/choral input cannot become named
  evidence. Loss of required capability enters recovery rather than silent advance.
- A Market Food candidate compiles to Protocol v3 with eight authored
  selected-individual oral turns. Each target has an explicit recovery path before the
  next callout, so the named-turn budget is real rather than a single sampled path.
  Core speaks the selected learner's deterministic bounded roster-name callout and keeps the
  response capability closed until Stage ACKs that exact completed speech turn; failed,
  stale or timed-out ACKs safe-pause rather than open the microphone.
- The candidate covers a 41.0-minute correct path and up to 44.7-minute recovery path. Every
  autonomous activity declares stage,
  budget, response/participation scope, skill IDs, evidence policy and recovery targets.
- A manual full-Market ideal-condition operator protocol now specifies the normal
  `ideal-hosted start` profile, activity-0 entry, an eight-person pseudonymous roster,
  the eight authored spoken stations, scrubbed evidence, and strict non-claims. It is a
  runbook, not evidence that such a full session has yet passed.
- Control has roster/attendance setup, room-readiness gating, teaching/recovery status
  and prominent emergency controls. Stage has learner turn and recovery cues.
- `composed-smoke` probes a real local Piper/faster-whisper endpoint from Chromium:
  a synthetic browser microphone recording reaches ASR, and returned Piper WAV enters
  browser playback. Optional authenticated Hermes health and a Hermes → Core MCP
  rehearsal are available; the latter deliberately delegates to the virtual-ACK wire
  smoke and is not physical-playback evidence.
- The stricter `ideal-composed-acceptance` lane completed one hosted-Hermes turn through
  two persistent Chromium contexts. It starts through visible UI controls; a generated
  adult Piper WAV supplies only Chromium's fake microphone file, then flows through real
  browser `MediaRecorder`, Whisper, Core grading, hosted Hermes/MCP, Piper, AIRI browser
  playback and a causal WebAudio acknowledgement. Its scrubbed artifact records `ok:
  true`: the unique agent turn's Stage-originated playback completion was event **368**,
  followed by Core commit **370**. This is composed-runtime evidence, not a classroom or
  child-speech result.
- The pinned `bright_live` gateway profile is active through
  `gateway.api_server.extra.bright_live`; after that correction the inspected ephemeral
  Hermes runtime database contained zero stored messages. That observation concerns this
  profile/run, not a blanket retention certification.

## Mechanical evidence

| Surface | Result | What it proves |
|---|---:|---|
| Classroom Core | **242 passed** | deterministic state, runner, app, MCP, session and policy behavior |
| Bright agent | **83 passed, 4 live-provider deselected** | non-live adapter/eval behavior only |
| AIRI bridge | **169 passed** | bridge unit behavior; typecheck/build also green |
| Chromium v3 flow | **2 passed** | mocked Stage/Control v3 browser contract at tested viewports |
| Content contract | **8 passed + lesson self-test green** | compiler/linter/simulated paths and draft release rejection |
| Smoke harness contracts | **10 passed** | product-wire/composed harness argument and coverage boundaries |
| Pinned Hermes artifact | manifest + patch/wheel hashes verified | reproducible Bright patch identity, not hosted-provider behavior |
| Ideal composed acceptance | **PASS, one synthetic adult turn** | real Stage/Control browser contexts, ASR → Core → hosted Hermes/MCP → Piper/AIRI, causal playback ACK and post-playback commit |

These counts are a snapshot of the implementation handoff. The Chromium test uses
mocked speech and does not establish real audio timing, echo behavior or Hermes
transport. The four agent deselections require live provider credentials/runtime.

## Honest capability boundary

The compiled lesson mechanically traverses eight distinct fair assignments through
callout, playback-ACK and capture contracts. It does **not** yet demonstrate a room-safe oral
classroom loop.

- Curriculum status is `draft`; approver is explicitly unassigned. Release lint and
  compile correctly fail until an educator approves the lesson and rubric.
- Roster/fairness/participation exist, but longitudinal class-aware learner memory is
  incomplete.
- Checkpoints are written, but Core startup does not restore and resume one.
- Stage budgets, checkpoints and recovery targets exist in content; the controller does
  not yet execute the complete pacing/recovery policy across a 35–45 minute session.
- The ideal acceptance uses a generated adult Piper WAV supplied through Chromium's
  fake-audio-file device, not child or room speech. It proves the real
  MediaRecorder/Whisper/Core/hosted-Hermes/MCP/Piper/AIRI causal-playback chain for one
  turn, but not physical speaker-to-mic echo, target hardware, child grading,
  no-false-accept, a full Market lesson, or a 20–40 learner classroom.
- Its 90-second hosted-provider budget and `0.65` speech-confidence threshold are
  fixture-only allowances for this synthetic diagnostic. Product defaults remain a
  6-second agent-turn budget and `0.75` speech-correct threshold; neither may be relaxed
  on the strength of this run.
- Local Gemma/OpenVINO remains a later provider migration behind the same Hermes seam;
  it is not a blocker for hosted-product implementation, but it is a competition gate.
- Consent, deletion/export, licences, SBOM, signed updates and cleared avatar remain
  release work.

## Next release-critical slice

Keep the one-turn lane green while completing the authored pacing/recovery metadata,
checkpoint restore and class-aware memory attribution. Then exercise all eight
callout/capture/recovery paths with physical audio and a pinned hosted Hermes session,
followed by repeated full 41.0–44.7 minute sessions and the consented room corpus. Until
those gates pass, describe Bright as an implemented autonomous-classroom vertical
slice—not a competition-ready autonomous teacher.
