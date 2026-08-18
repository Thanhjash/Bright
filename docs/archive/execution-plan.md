# 07 — EXECUTION PLAN & ADVERSARIAL REVIEW

**Date:** 2026-08-11
**Input:** an adversarial review by Codex (GPT-5.x) against docs 00/01/03/05 and the three reference repos.
**Purpose:** name what actually kills this project, and order the work accordingly.

---

## 1. The finding that reorders everything

> **The #1 risk is not OpenVINO, not AIRI, not MCP routing. It is the economics of authoring deterministic lesson content.**

NS-1 says the lesson must run without an LLM. That requires `lesson_run.json` to be complete enough to carry a full class: narration, prompts, answer keys, recovery branches, alternate acceptable answers, timing, media. The example in [architecture](../design/architecture.md) §8 is skeletal — it would not survive ten minutes of a real class.

If authoring one lesson costs 20–40 hours of expert time, the project dies of content starvation no matter how good the agent is. And no spike in [open questions](open-questions.md) measures this. **That gap is the single most dangerous thing in the plan.**

### The unlock

**Internet exists at authoring time. It only disappears at teaching time.**

This distinction was implicit and never stated, and it changes the economics completely:

```
AT HQ (online)                          IN THE CLASSROOM (offline)
────────────────────────────            ──────────────────────────
Large frontier model                    Gemma 4 E4B
Authoring Studio                        Classroom Core
generates lesson.md drafts              plays lesson_run.json
expands to full lesson_run.json         adapts within it
generates media                         no generation at all
human expert reviews + edits            no authoring
```

The offline constraint applies to **inference in class**, not to **content production**. A frontier model at HQ can expand a 40-line `lesson.md` into a complete, branch-covered `lesson_run.json`, generate the media manifest, and propose distractors and recovery paths — with a human teacher reviewing rather than writing.

**Therefore `apps/authoring-studio/` is Tier-0 infrastructure**, and `tools/lesson-lint/` (does this lesson produce a *complete, playable* run?) is the gate that makes the pipeline trustworthy. Both are named in [runtime topology](../design/runtime-topology.md) §5.

---

## 2. Where the NS-1 line actually falls

Codex asked the right question: does "runs without an LLM" secretly make the LLM decorative?

**No — if the split is drawn correctly.**

```
CORE OWNS (deterministic, authored)      LLM OWNS (generated live)
──────────────────────────────────       ───────────────────────────
lesson structure and ordering            which branch to take
activity content and answer keys         word choice in feedback
templated narration                      recasts of student sentences
timing and pacing                        personalization ("Minh, last week…")
grading and immediate feedback           EXPLORE depth and direction
recovery defaults for every branch       unscripted roleplay dialogue
who *can* be called on                   who *is* called on, and why
```

Run the same lesson in both modes and you get:

- **OFFLINE** — a well-made, linear, generic courseware lesson. Genuinely usable. Not personalized.
- **FULL** — an adaptive tutor that knows Minh dropped final `-s` last week, notices he hesitated, and drops a scaffolding rung before he gives up.

The LLM is not decorative. It is **the difference between courseware and a teacher**. And crucially, the floor being real means a school gets value on day one, before the agent is good.

**Authoring rule that keeps this honest:** every branch point in `lesson_run.json` must carry a `default` action. If an author cannot write the default, the branch is not authorable and should be removed. `lesson-lint` enforces this.

---

## 3. What falls between the two tiers — and how to resolve it

The reflex/pedagogy split in [architecture](../design/architecture.md) §2 is clean in principle. These are the cases that sit awkwardly across the seam, with the resolution for each.

### The general pattern: pre-registration

The strongest fix is to stop treating the LLM as reactive. **Before** the student responds, the agent pre-registers what happens for each anticipated branch:

```
Core: "asking Q7 now. Expected: 'I would like an apple'.
       What should I do on: correct / near-miss / wrong / silence?"
Agent (while the student is still thinking):
       correct   → praise_and_advance
       near-miss → recast: "Try: I would like an apple, please."
       wrong     → scaffold_down to image support
       silence   → repeat with slower TTS, then offer choice of two
```

Core then executes instantly at reflex speed. The LLM's latency is spent *during* the student's thinking time, which is free. This converts latency into prefetch and is the single highest-leverage trick in the design.

### Case-by-case

| Situation | Problem | Resolution |
|---|---|---|
| **Near-miss spoken answer** ("I want water" vs "I would like water") | Reflex can't judge partial correctness; the LLM takes seconds | Two-stage response. Core emits an instant non-committal backchannel (AIRI nods, "Mm-hmm") within 100 ms, then the substantive recast lands 1–2 s later. Humans do exactly this |
| **Silence after a question** | Is the student thinking, confused, or shy? | Core owns the timer with a pre-registered ladder (wait 4 s → repeat slower → offer two choices → move on). The LLM sets the ladder, never runs the clock |
| **Interestingly wrong answer** | Reflex marks it wrong; the pedagogy is in *why* it's wrong | Core gives neutral immediate feedback and queues the event with evidence. The LLM decides later whether to revisit — possibly next lesson, not this second |
| **Off-script utterance** ("Teacher, what's that bird?") | Belongs to neither tier | Core has an explicit `unhandled_utterance` state with a holding response ("Good question — let me think"). The LLM answers, defers to EXPLORE, or parks it. **This state must exist from day one**; without it the system looks broken the first time a child is curious |
| **Two students speak at once / class noise** | Never route to the LLM | Pure Core arbitration: confidence threshold, turn ownership, drop-and-reprompt |
| **Pronunciation scoring** (~300–800 ms) | Too slow for reflex, too fast to need the LLM | A third lane: **fast-async**. Fires as an event when ready. The board renders phoneme feedback directly; the LLM only sees the summary |
| **Teacher override mid-activity** | Human input outranks both tiers | Facilitator events bypass everything and mutate Core state directly, bumping `state_version` — which invalidates any in-flight agent decision. This is why `state_version` gating exists |

---

## 4. Revised risk ranking

| # | Risk | Mitigation | Covered by |
|---|---|---|---|
| 1 | **Lesson-authoring economics** — content starvation | Authoring Studio + frontier model at HQ + `lesson-lint` | **SP-0** (new) |
| 2 | **Loss of teacher control / classroom chaos** — the agent does something odd and the teacher can't stop it, so the school stops using it | Facilitator console with one-tap Pause/Skip/Take-over; `state_version` invalidation; agent policy limits | **SP-10** (new) |
| 3 | **16 GB budget** across model + speech + vision + Chromium | measure early, merge processes, be ready to move to 32 GB | SP-4 |
| 4 | **Small-model routing errors and repair-loop latency** | 4-tool proposal surface + `available_actions`; single-attempt, no retry ([architecture](../design/architecture.md) §3) | SP-3 |
| 5 | **Appliance operations + biometric consent policy** blocking adoption | offline update path, written data policy before any pilot | Q2, Q5 |
| 6 | Gemma 4 on OpenVINO / Hermes→OVMS plumbing | plumbing spikes | SP-1, SP-2 |

Note that the original Tier-0 spikes (SP-1, SP-2) drop to **#6**. They are plumbing — if they fail, we swap the serving layer (llama.cpp and vLLM are both documented in Hermes) and lose a week. Risks 1 and 2 are existential and lose the project.

### Two new spikes

**SP-0 — Author one complete lesson, end to end. (Do this first.)**
Take one 20-minute A1 lesson. Author it fully: narration, all activities, answer keys, distractors, recovery branches for every step, media list. Use a frontier model to assist. **Measure the wall-clock hours**, and how many hours are human vs. model.
*Kill criterion:* > 8 human-hours per 20-minute lesson after tooling → the content model is wrong; reduce branch coverage or shift to a template/parameter system where one authored template yields many lessons.

**SP-10 — Teacher control usability.**
Put the facilitator console in front of an actual teacher who has never seen it. Run a scripted lesson, inject three agent failures (wrong student named, wrong activity, agent stalls). Can they recover without help, in under 10 seconds, each time?
*Kill criterion:* they freeze, or call for help → redesign the console before writing any more agent logic.

---

## 5. The minimum demoable milestone

> **One complete 20-minute lesson, running on the real box, fully offline, with the LLM switched off entirely — avatar speaking, board interactive, one student answering by voice and one by pointing.**

Deliberately with **no LLM in the demo path.** Reasons:

1. It proves the floor that NS-1 promises. A school buying this needs to see the thing that always works, not the thing that sometimes impresses.
2. It is the demo we can make *reliable*, and a demo that fails in a real classroom kills a pilot faster than a modest demo that works.
3. Everything in it is on the critical path anyway.
4. It forces SP-0 to be answered honestly — you cannot fake a complete lesson.

Then, as a second act with the same lesson: turn the agent on, and show it noticing a struggling student and adapting. The contrast *is* the pitch.

### Shortest path, in order

```
M0  ── SP-0: author one complete lesson by hand + model assist
        Deliverable: one lesson_run.json that a human could teach from.
        Everything downstream depends on knowing this is affordable.

M1  ── data/schemas/ : scene, event, lesson_run, student record
        The spec. Written before code, versioned from line one.

M2  ── classroom-core: lesson runner + event bus + grading, NO LLM
        Headless. Tested by playing M0's lesson to a log file.

M3  ── classroom-ui: Stage skeleton + WS bus + 3 activity components
        (vocabulary_grid, ask_choice, sentence_builder). Still no avatar.
        Now M0's lesson is visibly playable on a projector.

M4  ── speech: TTS out (AIRI REST path) + VAD/STT in
        The lesson now talks and listens. Still no LLM.

M5  ── AIRI vendoring (SP-6): avatar + lipsync driven by M4's audio
        ★ MINIMUM DEMO REACHED — show it to a school ★

M6  ── perception: hand tracking → point-to-answer
        (face ID deferred; it needs the consent policy first)

M7  ── SP-1 + SP-2 + SP-4: model plumbing, and MEASURE consumption
        Output is a hardware spec, not a pass/fail. This is what picks the box.

M8  ── classroom-mcp 4-tool surface + Hermes wired in; SP-3 evals
        Second act of the demo: the same lesson, now adaptive.

M9  ── SP-10 teacher control review, then pilot readiness

M10 ── port to the production box, chosen using M7's measurements
```

### The demo runs on a laptop

Decided 2026-08-11. The school demo happens on a developer laptop plugged into a projector — Chrome fullscreen, all services local. See [runtime topology](../design/runtime-topology.md) §7.

This is not a shortcut, it is better sequencing. Every published Gemma 4 throughput figure comes from premium Core Ultra silicon; the number for budget hardware does not exist ([research](../research/notes/2026-08-11-edge-stack-viability.md) §1). Picking a SKU now means guessing at a workload we have not built. Build the product, measure what it needs at M7, then buy hardware against a real number.

**The offline architecture is still built from day one.** Local-only binding, separate services, versioned schemas — see [runtime topology](../design/runtime-topology.md) §7 for the list that must hold or M10 becomes a rewrite. What we defer is the *purchase*, not the *discipline*.

**M0–M5 contains no LLM at all.** That is the point. If the model layer slips a month, the demo does not.

Run **SP-1/SP-2 opportunistically in the background** from week one — they are cheap and independent, and knowing early is free. Just do not let them block M0–M5.

---

## 6. Where the Hermes decision might still be wrong

Codex pushed back on two things in [Hermes decision](../decisions/hermes-over-openclaw.md), and both deserve to be recorded rather than defended:

**The OpenClaw microphone argument was overstated.** `docs/platforms/linux.md:32` describes a WebView limitation with a documented workaround (use a regular browser) — which is what our architecture does anyway. [Hermes decision](../decisions/hermes-over-openclaw.md) has been corrected. The Hermes decision stands on Python co-residency, the verified `/v1/responses` contract, and install weight — not on that caveat.

**A purpose-built agent loop may beat Hermes.** This is the real open question. With the tool surface collapsed to 4 proposal-style tools and `available_actions` constraining every decision, the "agent" is close to: *build a prompt from Core state, call the model, parse a constrained response, validate `state_version`, execute*. That is a few hundred lines. Hermes brings memory providers, skills, cron, subagents, and a maintained API server — real value, but also a general-purpose chat loop with a repair mechanism we have to actively disable ([architecture](../design/architecture.md) §3).

**Decision: keep Hermes, but treat it as a service behind an adapter, not a framework we build inside.** Concretely:

- Everything Hermes-specific lives in one adapter module. Nothing else in the codebase imports it.
- `classroom-mcp` and `classroom-core` never know Hermes exists.
- Track the adapter's line count. **If it grows past ~800 lines of glue and workarounds, that is the signal to write the loop ourselves** — Hermes would then be costing more than it provides.

This is NS-4 with a concrete trigger instead of a vibe.

---

## 7. What this changes in the other docs

| Doc | Change |
|---|---|
| [Hermes decision](../decisions/hermes-over-openclaw.md) | OpenClaw mic argument corrected; decision unchanged |
| [architecture](../design/architecture.md) §3 | Tool surface cut from 26 ops to 4 proposal tools + `available_actions`; retry loop disabled; fallback ladder added |
| [open questions](open-questions.md) | SP-0 and SP-10 added; priority re-tiered |
| [runtime topology](../design/runtime-topology.md) | `authoring-studio` and `lesson-lint` promoted to Tier-0 deliverables |
| [north star](../NORTH-STAR.md) | NS-1 unchanged — but the line between Core and LLM is now defined in §2 above |
