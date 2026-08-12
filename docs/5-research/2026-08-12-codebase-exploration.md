# Bright codebase exploration

> **Historical research snapshot.** Findings here explain the interrupted state that
> preceded implementation. The locked production decision and current invariants now
> live in [Option B classroom runtime](../2-decisions/option-b-classroom-runtime.md)
> and the [North Star](../1-vision/north-star.md). When this report conflicts with
> those documents or current tests, it is not authoritative.

**Researched:** 2026-08-12 (Asia/Bangkok)
**Scope:** full `docs/` corpus, current product code, tests, runtime data, and the three cloned repositories under `references/`
**Method:** read-only inspection and local verification; no product code changed

## Executive summary

Bright is already a substantial **local-first classroom runtime**, not a concept repo. Its strongest finished layer is the deterministic floor: a lesson can render, narrate, accept tap/drag/speech input, grade, branch, persist observations, and continue without an LLM. The browser UI, Piper/Whisper speech service, Live2D avatar, event protocol, lesson compiler/linter/player, SQLite memory, appliance scripts, and integration harness all exist.

The intended final story is still **Hermes + AIRI + an English-teaching product**, but those three parts are at different maturity levels:

- **AIRI:** materially integrated. Bright has a React-facing `airi-bridge`, vendored audio pipeline, ACT parser, Live2D renderer, lip-sync, model binding, and extensive tests.
- **English-teaching product:** a strong runtime frame exists, but curriculum and classroom validity are weak. There is one format/reference lesson and one built-in sample; no evidence yet that a real teacher can author cheaply or that children learn from it.
- **Hermes:** selected architecturally but not integrated. `services/hermes-adapter/` is empty. Current runtime uses `DirectAgent` against an OpenAI-compatible API. Local Gemma/OpenVINO is also not integrated.

The four Claude agents that ended with 403 did leave partial work on disk. None of their assignments should be considered complete merely because files exist.

## How to read the existing docs

The docs are a development chronology, not one synchronized specification.

1. `1-vision/north-star.md` is the governing product doctrine.
2. `2-decisions/` records choices and source-based fact checks.
3. `3-design/` describes the target architecture.
4. `4-build/` contains several snapshots from different moments on 2026-08-11.
5. `5-research/` contains later reviews and explicit corrections to earlier claims.

Therefore a statement such as “speech is not wired” in an earlier status section can coexist with later code that wires it. For current status, use this precedence:

```
north-star for intent
    -> latest correction/research for interpretation
    -> current code and tests for implementation status
    -> tracker checkboxes only as historical status
```

## Product map

| Layer | Current implementation | Assessment |
|---|---|---|
| Product shell | Local React/Vite web UI at `/classroom` and `/control`; Chromium kiosk packaging | Built |
| Source of truth | FastAPI `classroom-core`, event bus, scene/state versions, lesson runner | Built and central |
| Content | Markdown lesson format, compiler, linter, headless player, compiled run JSON | Toolchain built; real curriculum missing |
| Reflex interaction | Tap, point, multi-step drag, speech grading, reveal, branch, timers | Built |
| Voice out | Piper REST service -> AIRI audio pipeline -> browser playback | Built |
| Voice in | Browser microphone/PTT -> Whisper -> `student.speech.final` | Built; ecological validity unresolved |
| Embodiment | Live2D renderer, ACT cues, mouth movement, model bindings | Built; production character/licence unresolved |
| Agent | `TeacherAgent` seam + `DirectAgent` + constrained actions | Built against hosted API |
| Hermes | Target runtime/reference | Not integrated |
| Local Gemma | Intended future provider behind the seam | Not integrated or measured here |
| Memory | SQLite students/sessions/observations/summaries + FTS5 recall | Implemented and exercised |
| Background work | Health probe and session summary | Implemented; next-lesson preparation remains no-op |
| Appliance | systemd, kiosk, doctor, USB update/rollback, budget script | Substantial; exact deployed box not proven |
| Perception | Face/gesture/identity fusion architecture | Not implemented |
| Pronunciation engine | Board exists; dedicated forced-alignment scorer does not | Not implemented |

## What is genuinely strong

### 1. The deterministic floor is real

`classroom-core` owns the lesson state and can follow authored branches without an agent. This is the most important architectural success because it preserves NS-1: the model can disappear without taking the lesson down.

Recent code also fixes three previously documented integration defects:

- only the first completed answer to an activity is graded;
- `repeat_activity` stops being offered after a bounded number of entries;
- every graded outcome advances `state_version`, including interactions with no special reveal pixels.

The old “known failures” list in `tests/README.md` predates these fixes.

### 2. AIRI reuse is real, not branding

`packages/airi-bridge` is a serious adaptation layer rather than a thin import. It contains:

- streaming ACT/DELAY marker parsing;
- ordered TTS chunking and playback;
- WebAudio and wLipSync integration;
- Live2D stage/motion/model binding;
- a React component and hook surface;
- upstream attribution and regression tests.

The UI mounts the real `Live2DAvatar` and sends real Piper audio through this path. This is currently the closest part of the repo to the original “AIRI body” vision.

### 3. Memory is ahead of the older status docs

The repo has a complete local persistence path:

```
graded interaction
  -> observation in SQLite + FTS index
  -> session summary (model or deterministic fallback)
  -> skill estimates
  -> recall injected into a later greeting/turn
```

The current database contains 1 student, 11 sessions, 24 observations, and 4 summaries. Integration test I8 is explicitly designed to prove persistence across a core process restart and a name-based greeting in the next session.

What remains missing is not basic memory storage. It is the larger product model: a roster/class of 20–40 students, reliable attribution of classroom speech, teacher-facing correction of memory, and next-lesson generation.

### 4. Failure-oriented engineering is unusually mature

The integration harness uses real processes, sockets, a real browser, a scriptable fake LLM/TTS, and a cuttable/black-hole proxy. Appliance work includes loopback binding, service restart policy, health gates, SQLite/WAL checks, kiosk boot, and atomic USB rollback. This work serves the actual deployment environment better than adding more model features would.

## The four interrupted agent assignments

### A. ScriptedAgent demo insurance — partial, not runnable

`services/agent/bright_agent/scripted.py` is a large and thoughtful deterministic `TeacherAgent`. It validates actions through the same contract as `DirectAgent`, supports greeting, observation, speech, action preference, zero-token accounting, and a health-probe-compatible `complete()` method.

However, the product cannot select it:

- it is not exported from `bright_agent.__init__`;
- `classroom-core/app.py` always constructs `DirectAgent` when `BRIGHT_AGENT=1`;
- there is no implementation-selection config;
- the default `bright_agent/data/demo_script.json` does not exist;
- there are no product tests for this implementation.

Status: **implementation draft on disk; integration not started/completed.**

### B. Demo lesson and fast degrade — mostly implemented, policy unfinished

The runner now speaks authored branch feedback immediately while the model thinks, overlaps the reveal hold with the agent turn, cancels obsolete speech, and defers the authored branch safely after `say_only`. This directly addresses the earlier four-second silent gap.

Mode tracking now accepts live-turn failure signals and pulls the next health probe forward. But default `CORE_DEGRADE_AFTER=2` still permits two six-second failures before demotion. That is bounded, but it is not the review's strongest recommendation of demoting after the first failed live turn for a rehearsed demo.

The built-in animal sample now includes a speech expectation, so the earlier “sample has no spoken answer” finding has been partially addressed.

Status: **substantial code landed; exact demo policy and end-to-end rehearsal remain unproven.**

### C. Demo path hardening in UI — core risk still open

The five new boards are present: matching, sentence builder, pronunciation, roleplay, and explore. The compiled format example reaches all five; the built-in sample reaches matching and sentence builder.

But breadth is not equivalent to demo readiness. The important unresolved issue remains:

- every `speech.say` starts a player turn with `behavior: 'interrupt'`;
- Core can emit several narration lines synchronously;
- a new activity or agent line can supersede speech already in progress.

Core now emits `speech.cancel` intentionally when a decision overtakes narration, but the browser still has no ownership-aware queue for multiple valid `speech.say` events. The exact judged sequence must be rehearsed; otherwise the teacher can still cut herself off.

Status: **boards built; demo sequencing/voice ownership not hardened.**

### D. Speech latency and room test — useful harness, wrong evidence population

`tests/room/room_test.py` does the right conceptual thing: it feeds transcripts through the real Core grader and reports false accepts separately from transcription accuracy. The latest stored result shows `tiny.en` with no wrong-to-correct false accept on the tested set and roughly 544 ms median wall-clock transcription.

But the stored evidence is clean Piper-generated speech. The harness can add synthetic room effects, yet it has no recorded child speech and no real classroom capture. It therefore cannot settle the deployment model choice or the risk that the microphone hears the loudspeaker better than the selected child.

The harness also surfaced a model-independent grading bug: containment can mark “I don't like cats” correct for target `cat`. The hard product boundary—never tell a child they are correct when they are wrong—is not yet secured for open speech.

Status: **mechanical harness built; ecological test not run; grading policy still unsafe for some utterances.**

## Hermes, DirectAgent, and future Gemma

The current architecture already proves NS-4 better than the original target stack:

```
Classroom Core -> TeacherAgent protocol -> current DirectAgent -> hosted API
                                  future HermesAgent -> Hermes service
                                  future LocalAgent  -> Gemma server
```

Hermes remains a reasonable future harness for procedural skills, cron, subagents, and a maintained API server. It should not be described as part of the running product today. `services/hermes-adapter/` is empty, no systemd Hermes service exists, and nothing imports the cloned Hermes repo.

There is also a strategic question worth keeping open: Bright's constrained agent loop is already small and purpose-built. Hermes earns its place only when its higher-level harness capabilities are actually needed. The existing docs give a sensible exit criterion: if the adapter becomes hundreds of lines of workarounds, keep the direct loop.

For the user's current direction—hosted API now, Gemma later—the present seam is appropriate. Model work should not lead product work until the classroom path is credible.

## Current verification snapshot

Executed locally during this exploration:

- workspace TypeScript typecheck: **pass**;
- `packages/airi-bridge` tests: **pass**;
- agent offline/eval tests: **67 pass**;
- the default agent suite enters `test_live.py` and fails/hangs without provider access; live tests are mixed into the default suite rather than cleanly separated;
- focused/full Core runs exceeded the exploration timeout on the Windows-mounted filesystem after producing passing progress, so this exploration does **not** claim a fresh full Core pass count;
- the stored room result is a prior run, not rerun here.

This means old totals such as 178 or 293 are historical counts, not a trustworthy current headline.

## Product risks, re-ranked for the current state

1. **No real product lesson.** `format-example.md` explicitly says it is not curriculum. Until one complete teacher-approved lesson exists, the product is a capable engine with placeholder teaching content.
2. **No ecological classroom evidence.** One-student tests, fake LLM/TTS, and synthesized speech cannot validate a room of 20–40 children.
3. **Spoken grading can falsely accept.** The known negation/substring case violates the strictest teaching requirement.
4. **The rehearsed demo path is not insured yet.** ScriptedAgent is disconnected; hosted-model failure can still be visibly expensive.
5. **Speech ownership is ambiguous.** Multiple valid narration events can interrupt each other.
6. **The system models one active student, not a class.** Identity/perception and classroom orchestration are still architectural sketches.
7. **Hermes and local Gemma are future claims.** Neither belongs in a present-tense demo claim.
8. **Character distribution/licensing remains unresolved.** The current model is suitable for development/demo only under the documented constraints.
9. **Docs and tests are not synchronized.** Useful history is being mistaken for current status, and default Python test commands do not provide a clean offline baseline.

## Recommended product sequence — analysis only

No implementation should start from this report without choosing the demo/product milestone. The highest-information sequence is:

1. Define one exact 10–20 minute lesson and one exact room/demo script.
2. Rehearse it end to end with the model disabled; include one real spoken answer.
3. Collect real child/room audio with consent and run the existing outcome-level harness.
4. Make false accept impossible or explicitly uncertain before optimizing latency.
5. Finish deterministic demo insurance and voice ownership for that one path.
6. Put the teacher console in front of a teacher unfamiliar with the system.
7. Only then expand curriculum, multi-student identity, Hermes, and local Gemma.

This ordering follows the North Star: finish the product floor, then intelligence, then the general-purpose agent harness.

## Unresolved questions

- What is the exact competition/demo date now? The existing “five days” tracker is dated 2026-08-11.
- Is the immediate product milestone a judged demo, a school pilot, or a reusable authoring platform?
- Who owns the first real curriculum lesson and its acceptance criteria?
- Is voice input teacher-operated push-to-talk for the demo, or autonomous room listening?
- Should a single agent failure demote immediately for demo mode, even if production keeps a two-failure threshold?
- What may be claimed publicly about Hermes, local Gemma, offline intelligence, and the current Live2D character?
