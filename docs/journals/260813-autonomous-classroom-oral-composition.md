---
date: 2026-08-13
session: autonomous-classroom-oral-composition
---

# Journal: 2026-08-13 — Oral Turns and Composed Speech Boundary

## Context

The North Star remains an autonomous AI teacher for a 20–40 learner classroom. This increment converted the lesson's declared eight named-turn budget into eight compiled, individually assigned oral turns, then reviewed the physical callout-to-capture boundary before extending composition evidence.

## What Happened

- The market lesson now compiles eight distinct selected-individual speech stations. Each has a bounded whole-class recovery path, and lint rejects a mismatch between authored stations and `namedTurnBudget`.
- Core now speaks a fixed, sanitized learner callout and keeps the microphone closed until Stage completes that exact speech turn. Stale, failed, cancelled, or missing playback ACKs cannot arm capture and instead fail closed.
- Review found three seam defects and closed them: TTS queue time consumed the pre-callout capability TTL; failed callout/resume could spend or change the fair target; and the refreshed server expiry was not republished to Control before capture began.
- The eight-turn integration traverses all compiled stations, produces eight unique fair targets, completes correlated capture, and exhausts the named-turn budget.
- A separate composed probe now exercises a Chromium fake microphone through real local ASR and real Piper output through browser audio. It deliberately excludes physical-room acoustics, child recognition/grading, AIRI lifecycle ACKs, and full Hermes teaching composition.

## Verification

| Evidence | Result | Meaning |
|---|---:|---|
| Classroom Core | 232 passed | Full deterministic Core suite at review checkpoint |
| Eight-turn compiled integration | 1 passed in isolation | All eight callout/ACK/capture turns complete with unique fair targets |
| Bright agent | 82 passed, 4 live-provider deselected | Non-live Hermes adapter/eval behavior |
| AIRI bridge | 165 passed | Unit suite; typecheck/build also green |
| Content contract | 8 passed | Compiler, budget and recovery contracts |
| Smoke harness contracts | 10 passed | Product/composed harness boundaries |
| Product wire smoke | PASS, Protocol v3 `DONE`, 5110.6 ms | Virtual Stage/Core wire path; artifact `20260813T060208-159581Z` |
| Composed speech probe | SKIP, exit 2 | Speech endpoint `127.0.0.1:8001` refused; artifact `20260813T060202-456301Z` |
| Documentation links | 22 valid | Internal docs link check |

## Reflection

The authored budget now corresponds to actual opportunities for children to speak, and capture begins only after the selected learner can hear their name. The review fixes matter because each defect could pass unit-level reasoning while shortening a child's response window, corrupting fairness, or making the browser reject a server-valid assignment. The composed harness is useful infrastructure, but its skipped run is not product evidence.

## Decisions Made

| Decision | Rationale | Impact |
|---|---|---|
| Gate capture on the exact Core callout ACK. | Selection is not physically real until the learner hears it. | No silent or stale callout can open the microphone. |
| Start response TTL and Ready deadline after callout completion. | TTS latency must not consume learner response time. | Slow speech queues cannot unfairly expire a turn. |
| Preserve the same fair target across failed callout/resume. | A failed output is not a completed learner opportunity. | Fairness counters reflect heard turns, not attempted playback. |
| Keep composed-browser evidence separate from room evidence. | A fake browser microphone and synthetic speech do not represent children or classroom acoustics. | Release claims remain evidence-based. |

## Next Steps

- Start the real local speech service and rerun the composed probe; retain its machine-readable artifact.
- Extend composition to real Stage/Control plus AIRI lifecycle ACKs and a live Hermes proposal without virtual playback ACKs.
- Run consented child/noisy-room evaluation on target hardware and require zero false acceptance before competition-ready claims.
