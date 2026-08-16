# 03 — DECISION: Option B classroom runtime

**Date:** 2026-08-12
**Status:** LOCKED; v3 vertical slice implemented, release evidence open
**Scope:** live classroom path

## Decision

Bright uses Hermes as a separately managed sidecar and talks to it through its
programmatic API. Classroom Core remains the only authority for lesson state,
grading, learner memory, and legal actions. Hermes reaches that authority only
through a narrow Bright-owned MCP surface. AIRI renders the resulting speech and
behaviour; it is not a second agent runtime.

```text
Control mic -> Bright ASR -> Classroom Core -> Hermes adapter -> Hermes sidecar
                              ^                    |
                              |---- Bright MCP ----|
                              |
                              +-> protocol v3 -> Stage -> AIRI/TTS/projector
```

This is “Option B”. It deliberately avoids copying Hermes into Bright's process.
The extra loopback hop buys process isolation, upstream upgradeability, independent
health/degradation, and a clean model-provider seam. The latency budget is enforced
at the conversation boundary rather than assumed from topology.

## Authority and ownership

| Concern | Sole owner |
|---|---|
| lesson state, legal actions, grading | Classroom Core |
| learner mastery and observations | Bright database |
| cognitive response and tool proposals | Hermes |
| ASR transcript production | Bright speech service |
| physical classroom audio | Stage |
| avatar, lipsync, timed emotion | AIRI bridge |

There are no dual writers. In the live profile Hermes must call exactly one terminal
tool, `classroom_propose_move(turn_id, move_id, teacher_line)`. Core issued the opaque
turn and legal move IDs, revalidates them at commit time, bounds the teacher line, and
applies the move only after matching physical playback completes. An expired,
duplicated, unscoped, or stale proposal fails closed. This deliberately avoids asking
stock Hermes to discover a changing multi-tool surface.

## Live speech contract

Plain assistant text deltas from Hermes are the one adaptive human-facing speech
source. `classroom_say` is not exposed on the live Hermes profile because it would
create a second voice path. Core correlates the response to a conversation turn and
publishes an ordered speech turn. Stage is the only browser role permitted to play
it and reports playback started/finished. Control is the only mic owner.

The autonomous-classroom slice is half-duplex. Core issues an exact response assignment
and capture request; the child-operated answer station reports Ready and opens only
after the matching playback-finished acknowledgement and an echo-tail cooldown. A
legacy/manual PTT path remains for recovery. If PTT is pressed during output, Control
requests an authorized exact-turn barge-in; Core
validates the activity epoch, cancels that turn, and the mic remains closed until
Stage reports termination plus the echo tail. Full-duplex/VAD barge-in remains a
later measured capability, not a demo assumption.

## Hosted model policy now

The hosted classroom request contains pseudonymous session/learner references and
the minimum current pedagogical context. It contains no real child name, raw audio,
prior raw transcript, or cross-learner recall. Classroom Hermes requests use
`store: false`; no hosted conversation chain or long-term child memory is relied on.
The current-turn transcript is an ephemeral input to deterministic grading. Under the
implemented `hosted_semantic` policy Hermes receives only the graded semantic outcome,
not raw transcript. Raw synthetic transcript may reach Hermes only under the explicit
`synthetic_dev` policy with acknowledgement and fixture provenance; it must not be
serialized into observations, SQLite/FTS evidence, logs or hosted summaries, and it is
not production proof.

Hermes' live profile has an explicit allowlist containing only the Bright classroom
MCP server and its one terminal proposal tool. Terminal, filesystem, browser, cron,
delegation, general memory, and other default tools are absent. The pinned runtime is
`hermes-agent 0.20.0+bright.2`, upstream commit
`03fa32c92dd445eb64c7f67434dd91b32c40701d`; its patch disables live persistence,
conversation chaining, background work and a second inference after the terminal
tool. A future planner profile must be a separate trust domain and may not silently
broaden the live profile.

## Failure and cancellation

Core owns the wall-clock deadline and generation fence. Closing the Hermes response
stream is best-effort physical cancellation; Core immediately guarantees logical
cancellation by rejecting all late deltas and tool results for that turn. A new
activity cancels output from the old generation. Operational Hermes failures degrade
the mode immediately; the class continues through the authored deterministic path.

The production appliance must have a non-dev path to select/start a lesson. Booting
healthy services without a way to begin class is not considered available.

## Local Gemma migration

Bright's adapter calls Hermes, never a provider-specific endpoint. Replacing the
hosted model with locally served Gemma changes the pinned Hermes classroom profile
(`provider`, `model`, and `base_url`) and deployment resources, not Core, MCP,
protocol, UI, or curriculum code.

The switch is gated by the same provider conformance suite and real-room corpus:

- correct tool-call/event behaviour through Hermes;
- zero false accepts on the release safety corpus;
- conversation latency, RAM, thermal, and sustained-load budgets;
- reliable cancellation and no starvation between agent inference and audio work.

Gemma native audio may later implement the ASR provider interface, but dedicated ASR
remains canonical until that independent benchmark passes. Model support for audio
alone is not proof that the serving and Hermes transports support the required path.

## Release gates

- reflex paint remains under 100 ms;
- stale generations never grade, speak, or mutate learner state;
- one physical voice and one terminal playback event per speech turn;
- cancelled output becomes locally silent within 100 ms;
- no wrong answer is accepted on the release room corpus;
- Hermes loss produces authored fallback without repeated silent waits;
- no raw transcript is recoverable from Bright or live Hermes persistent stores;
- the lesson starts and completes under production settings with Hermes/network absent.

## Rejected alternatives

- **Embed/copy Hermes in-process:** tighter coupling to a large mutable Python runtime,
  shared failure/global state, and expensive upstream merges for negligible expected
  loopback savings.
- **Browser talks directly to Hermes:** bypasses Core authority and exposes credentials,
  tools, cancellation, and provider details to the UI.
- **Hermes voice/STT as the primary path:** the Responses API is text/image oriented and
  Bright needs correlated grading confidence and independent speech degradation.
- **Hermes memory as learner truth:** personal-agent memory is not the pedagogical data
  model and would create an unscoped dual writer.
