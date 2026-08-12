# Option B implementation status

**Updated:** 2026-08-12
**Status:** implemented, integration verification in progress

The locked architecture is in
[Option B classroom runtime](../2-decisions/option-b-classroom-runtime.md). This
file is the current handoff, not a forecast.

## Implemented

- Protocol v2 in the Markdown, TypeScript, and Python contracts: production
  lesson start, activity epoch, utterance correlation, streamed speech turns,
  playback ACKs, and correlated student-response terminal events.
- Core-owned lesson start and conversation correlation with role-gated control
  and Stage playback events.
- Audio-aware activity arming: listening and silence/duration timers begin after
  matching playback completion; a bounded watchdog preserves offline liveness.
- Conservative speech grading: normalized exact answer plus confidence threshold;
  low-confidence exact speech is uncertain/near, and extra clauses do not become
  correct by containment.
- Learner-memory isolation and hosted-minimal context: no cross-student widening,
  no model-selected learner writes, no raw transcript in scene/durable evidence,
  and no recalled learner notes sent to the hosted classroom model.
- Hermes Responses adapter with strict SSE parsing, `store:false`, Core-issued
  turn capability, cancellation, failure mapping, and a local-Gemma provider seam.
- Bearer-authenticated four-tool Bright MCP with TTL, learner/state/activity scope,
  stale-call rejection, and mutation deduplication. The live profile excludes
  `classroom_say` and all broad Hermes tools.
- Stage-only keyed speech output through AIRI, exact cancellation, AbortSignal,
  ACT timing, audio assets, playback ACKs, and reconnect-safe terminal handling.
- Control-only mic with activity snapshot, correlated response completion,
  queued-output suppression, 800 ms echo tail, stale-capture discard, and an
  authorized exact-turn PTT barge-in handshake.
- WebSocket roles are immutable after handshake and browser origins are checked
  against the configured allowlist.
- Production Start/Restart Lesson control; Hermes/systemd/profile/install/doctor
  integration remains optional so Core can teach authored lessons without it.
- Room harness now fails on any false accept rather than tolerating one-offs.

## Verification evidence

- Core Option-B + Hermes focused tests: 18 passed.
- Core runner tests: 41 passed after protocol-version and playback-watchdog hardening.
- Core learner-memory suite: 41 passed.
- Hermes full non-live suite reported by its implementation owner: 77 passed,
  4 live-provider tests deselected.
- AIRI bridge: typecheck passed; 13 files / 165 tests passed; build passed.
- Classroom UI: typecheck and production build passed.
- Python compilation, Hermes YAML parse, and modified shell syntax passed.

## Open release blockers

- Core suites that enter Starlette `TestClient` (including `test_app.py` and
  heartbeat WebSocket tests) still hang in this environment. The separate
  learner-memory suite is now 41/41 green; the remaining lifecycle blocker
  occurs inside AnyIO's blocking portal before the first HTTP assertion. A
  one-route FastAPI application with no Bright imports reproduces the same
  `TestClient.__enter__` timeout here, so this is an environment/toolchain gate;
  it still must pass on CI or the appliance image before release.
- A real pinned Hermes + hosted-provider + MCP smoke has not run in this workspace;
  it requires credentials and the pinned Hermes wheel/runtime.
- Real child/classroom recordings have not passed the zero-false-accept release
  corpus. Synthetic/Piper evidence is not ecological validation.
- The local process/socket smoke currently proves the production Core wire path,
  role authorization, production lesson start, and playback correlation. It does
  not execute browser audio, AIRI, Piper, ASR, or Hermes and is not release proof.
- Authorized PTT barge-in is implemented, but real-room echo/AEC and child-speech
  behavior remain unvalidated on target hardware.
- Local Gemma/OVMS tool-call, latency, memory, thermal, cancellation, and audio
  provider conformance remains a future measured migration gate.
- Git metadata is unavailable in this workspace (`.git` is an empty read-only
  directory), so this implementation cannot yet be committed or pushed.

## Next gate

Run the TestClient suite on CI/appliance, then conduct a real-browser composed
Stage + Control + Core + AIRI + speech + pinned-Hermes smoke. Only after that
should the three-run demo rehearsal and consented real-room safety corpus be
treated as release evidence.
