---
title: "Full-lesson ideal product proof"
status: in_progress
created: 2026-08-13
scope: project
---

# Full-lesson ideal product proof

## North Star and decision

Bright is an autonomous AI English teacher for a shared class of 20–40 learners,
not a chatbot demo. The immediate product question is narrower and testable:

> Can a fresh, uninterrupted Bright lesson run through its real browser, speech,
> Core and hosted-Hermes boundaries without fabricated protocol events?

The one-turn proof at commit `39c1104` answers that once. This plan turns it into
repeatable multi-turn evidence and corrects a pacing contradiction that would otherwise
silently cut a Market Food lesson short. It does **not** claim physical classroom,
child-ASR, 20–40 learner, local-Gemma, restart or governance readiness.

## Scout evidence

- The canonical Market Food correct route is 2,460 seconds (41 minutes), but Core
  currently reserves the final 240 seconds from a 40-minute duration and forces
  closure at minute 36. That can skip authored teaching and exit checks.
- Market has eight canonical selected-individual oral stations and an authored
  named-turn budget of eight. A full manual route is the only honest sequential
  proof today.
- Chromium's fake capture file restarts after each capture: one WAV cannot reliably
  provide eight different answers. A concatenated WAV is not valid evidence.
- Current ideal acceptance proves one real composed turn using two persistent browser
  profiles, real MediaRecorder/Whisper/Core/Hermes/MCP/Piper/AIRI and causal Stage ACK.

## Scope and non-goals

In scope:

1. Make session-clock/closure behavior deterministic, authored and observable.
2. Add a repeatable three-turn composed fixture with the same canonical answer, using
   visible Stage/Control interaction and no fabricated frames.
3. Add a separately-labelled manual full-Market protocol/runbook for eight spoken
   answers and an eight-person roster.
4. Record scrubbed per-attempt ordering and latency evidence.

Out of scope:

- Core restart/restore, local Gemma/OpenVINO, appliance packaging, room acoustics,
  child recordings, classroom identity/perception, new curriculum, or a hidden
  test-only jump into a production Market activity.

## Acceptance contract

### Product pacing

- `durationMin` means the inclusive teaching window; `closureReserveS` is protected
  time for authored exit and closure, not permission to silently abandon arbitrary
  activities.
- Any catch-up transition must follow an explicit authored safe/default route and
  emit a visible pace reason. Hermes cannot select the skip.
- Entering closure cancels stale speech from the superseded activity.
- A deterministic canonical-path test proves Market reaches `exit_check` before its
  reserve or explicitly reports an authored catch-up route.

### Automated ideal composition

- Two persistent Chromium profiles use only visible UI; no `/dev`, direct WebSocket,
  browser state injection or fabricated ACK/input.
- For each of three attempts: exact callout completion -> capture request -> Ready ->
  capture start -> real ASR HTTP 200 -> `correct` -> one hosted-Hermes proposal ->
  causal Stage audio start + completion -> following Core commit.
- The result artifact has opaque slots and durations only; no text, IDs, credentials,
  cookies or transcript. Hermes durable `messages` remains zero.
- Separate `compositionPass` from `productLatencyPass`; acceptance-only timeout and
  confidence allowances may never be reported as product values.

### Manual Market acceptance

- Starts the real Market Food lesson from activity zero, uses an eight-person roster,
  and takes eight adult answers through the visible product UI.
- It records 8 assigned turns, 8 completed capture lifecycles, canonical station order,
  no pause/error, closure/DONE, and no durable Hermes messages. A separate optional
  accuracy result reports how many adult attempts were correct; it is not required for
  flow-completion proof and cannot be promoted to child-ASR safety evidence.
- This is an operator-run ideal-condition gate, not child/room safety evidence.

## Phases

| Phase | Deliverable | Depends on |
|---|---|---|
| 1 | Pace-contract tests and deterministic authored closure policy | — |
| 2 | Three-turn composed fixture, generalized Chromium ledger and artifact schema | 1 |
| 3 | Manual full-Market runbook and evidence validation | 1 |
| 4 | Independent review, deterministic suites, composed reruns and truthful docs | 1–3 |

## Current checkpoint — 2026-08-14

- Phase 1 is mechanically complete: Core follows only authored pacing routes,
  rearms overdue pacing steps until closure, and cancels live superseded narration.
- The one-turn composition lane passed with the locally configured hosted provider:
  two persistent Chromium profiles exercised real Stage AIRI/Piper causal ACK, ASR,
  Core grading, a Hermes MCP proposal, and a following commit. Its scrubbed local
  artifact is `tests/.artifacts/ideal-composed/result.json`; the ephemeral Hermes home
  had zero stored messages.
- Phase 2's three-turn live run remains pending. One synthetic adult turn is not a
  substitute for the full Market/manual, room, child-ASR or 20–40 learner gates.
- Phase 3's runbook is ready; the manual eight-station Market run has not yet been
  performed.
- Phase 4's deterministic suite is green and its one-turn live composition gate now
  has evidence. It remains incomplete until the repeated, three-turn and manual-Market
  gates are run.

## Risks deliberately controlled

- Fake mic cannot prove sequential Market phrases: use it only for repeated-answer
  topology/cycle proof; retain manual Market for curriculum sequence.
- Hosted provider cold latency cannot be hidden: report it separately and keep product
  default budgets unchanged.
- Closure must not speak stale narration: cancel exact old speech turns before the
  authored transition.
- No claim promotes synthetic adult audio into room/child validity.
