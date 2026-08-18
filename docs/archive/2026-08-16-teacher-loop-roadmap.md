# Research: teacher-loop-first roadmap

**Date:** 2026-08-16  
**Status:** SUPERSEDED the same day as a *sequencing* doc.  
**Replacement:** [autonomous-classroom-roadmap.md](../STATE.md) and [teacher-agent-not-cassette.md](../decisions/teacher-agent-not-cassette.md).

Keep the research findings (small-model tool risk, TBLT vs chatbot, child-data
law, Gemma/OpenVINO). **Do not keep** the implied product: one
`classroom_propose_move` + `lesson_run.json` as the teacher. That was a
wire-wedge that got mistaken for Layer 1.

**Date:** 2026-08-16  
**Scope:** sequencing Bright from a working text teacher to the North Star classroom  
**Not in scope:** implementing the probe, picking a production SKU, drafting consent forms

Sources: North Star and Option B in this repo; teammate TBLT / Global Success package;
NĐ 13/2023 and successor notice; TBLT+GenAI review (Li 2026); local tool-call
benchmarks (2026); Intel/OpenVINO Gemma 4 notes.

---

## Executive summary

The North Star is still a 20–40 learner offline classroom teacher. The shortest
honest path is: prove Hermes can teach **one** learner in text, then attach board
media, voice, AIRI, class scale, and local Gemma — in that order.

Three findings lock the design:

1. **Small models do not reliably drive a wide tool surface.** Bright’s own
   Gemma 4 E4B Tau2 number is 42.2%. Independent 2026 local-agent writeups treat
   tool-call reliability as the thing that makes or breaks a loop, and the
   “reliable” Gemma 4 mention is the **27B** class, not E4B. Live Bright must
   stay at one terminal proposal. Image / audio / board writes are Core
   primitives, not three extra Hermes MCP tools.
2. **Chat-shaped GenAI is a weak classroom teacher.** A 2026 TBLT+GenAI
   meta-analysis found most studies used ChatGPT one-student-at-a-time and still
   needed a human assessor. Bright’s job is a language-specific TBLT runtime
   (choral → pair → light focus), not “Ask Gemma about an animal.”
3. **Child face and voice are sensitive personal data in Vietnam.** NĐ 13/2023
   (effective 2023-07-01) requires guardian consent and additional consent from
   a child aged 7+. A later decree 356/2025 is cited as replacing/detailing the
   personal-data law. Detector and durable ASR stores wait for Layer 7 plus a
   human legal read. Silence is not consent. Face boxes must never hit the
   projector.

Hosted API now is correct. OpenVINO has a Gemma 4 functional preview (E2B/E4B
family) on Intel CPUs; GPU/NPU paths are still preview-ish and OVMS has had
`gemma4` load failures. Local Gemma is Layer 6, with a parallel probe only
after Layer 1 is green.

---

## What we took from the teammate package

Keep as curriculum:

- TBLT Pre-task → Task Cycle → Post-task
- Locked Unit 1 vocabulary; no Unit 2 language
- Local asset manifest (Drive is ingest only)
- No public scores or ranking
- Facilitator owns safety / distress / abuse escalation
- Semantic class/student memory only

Reject as runtime:

- 10 Hermes tools including `display_image(path)` and `write_class_memory`
- Long live system prompt as the lesson authority (that is `lesson_run.json`)
- Chatbot chrome from the ClassroomAI screenshot
- Identity overlay on the shared board

---

## Implications for Bright

| Temptation | Why it fails here |
|---|---|
| Give Hermes show-image / play-audio / write-board tools | E4B-class models miss tools; Core would stop when the agent does |
| AIRI before TTS | Silent avatar. AIRI is a body, and `references/airi` is renderer-only |
| Detector now to “link memory” | Illegal without consent; identity fusion is Core, Layer 5 |
| Gemma local before text teacher works | Showcase without a product. Same Hermes profile can wait |
| Keep building on the 1:1 WIP tree | Mixed wire + UI + false “reliability completed” claims |

---

## Unresolved (need a human, not more code)

- Confirm current binding text: NĐ 13 vs NĐ 356/2025, with counsel, before any
  real-child face/voice store.
- Global Success page/track licence for anything beyond a private prototype.
- Distributable avatar (Hiyori sample is not donation-safe).
- Whether Gemma 4 E4B on the actual demo laptop meets the 6s classroom budget
  with the one-tool profile. Measure after Layer 1.

---

## Next step

Layer 1 on clean `main`: Hermes-only provider probe. Details and gates live in
[autonomous-classroom-roadmap.md](../STATE.md).
