# Option B implementation status

**Updated:** 2026-08-12
**Status:** autonomous-classroom v3 vertical slice mechanically green; not release-ready

The locked boundary remains [Option B classroom runtime](../2-decisions/option-b-classroom-runtime.md):
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
- A 17-activity Market Food candidate compiles to Protocol v3 and covers a 37-minute
  correct path and 39-minute recovery path. Every autonomous activity declares stage,
  budget, response/participation scope, skill IDs, evidence policy and recovery targets.
- Control has roster/attendance setup, room-readiness gating, teaching/recovery status
  and prominent emergency controls. Stage has learner turn and recovery cues.

## Mechanical evidence

| Surface | Result | What it proves |
|---|---:|---|
| Classroom Core | **224 passed** | deterministic state, runner, app, MCP, session and policy behavior |
| Bright agent | **82 passed, 4 live-provider deselected** | non-live adapter/eval behavior only |
| AIRI bridge | **165 passed** | bridge unit behavior; typecheck/build also green |
| Chromium v3 flow | **2 passed** | mocked Stage/Control v3 browser contract at tested viewports |
| Content contract | **7 passed + lesson self-test green** | compiler/linter/simulated paths and draft release rejection |
| Pinned Hermes artifact | manifest + patch/wheel hashes verified | reproducible Bright patch identity, not hosted-provider behavior |

These counts are a snapshot of the implementation handoff. The Chromium test uses
mocked speech and does not establish real audio timing, echo behavior or Hermes
transport. The four agent deselections require live provider credentials/runtime.

## Honest capability boundary

The slice demonstrates one sampled individual speech turn through assignment and
capture contracts. It does **not** yet demonstrate a complete oral classroom loop.

- Curriculum status is `draft`; approver is explicitly unassigned. Release lint and
  compile correctly fail until an educator approves the lesson and rubric.
- Roster/fairness/participation exist, but longitudinal class-aware learner memory is
  incomplete.
- Checkpoints are written, but Core startup does not restore and resume one.
- Stage budgets, checkpoints and recovery targets exist in content; the controller does
  not yet execute the complete pacing/recovery policy across a 35–45 minute session.
- No real Stage + Control + Core + AIRI + Piper + ASR + hosted Hermes composed run has
  passed. There is no target-hardware, child/noisy-room, echo/AEC or provider proof.
- Local Gemma/OpenVINO remains a later provider migration behind the same Hermes seam;
  it is not a blocker for hosted-product implementation, but it is a competition gate.
- Consent, deletion/export, licences, SBOM, signed updates and cleared avatar remain
  release work.

## Next release-critical slice

Execute the authored pacing/recovery metadata, restore checkpoints on Core restart,
complete class-aware memory attribution, and run the same one-turn flow through real
browser audio, ASR and pinned hosted Hermes. Then run repeated full 37–39 minute
sessions and the consented room corpus. Until those gates pass, describe Bright as an
implemented autonomous-classroom vertical slice—not a competition-ready autonomous
teacher.
