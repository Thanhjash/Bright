# 10 — STATE OF THE PROJECT

**Date:** 2026-08-11
**Purpose:** a step back. What is actually true now, what changed, and what is still unproven.

Written after building the Phase 1 skeleton. Read this before deciding what to do next.

---

## 1. The one-paragraph truth

We have built and verified a **lesson player**: a system that runs an authored English lesson end to end, on screen, with grading and branching, and **no AI whatsoever**. That was the deliberate first target (NS-1) and it works. But the entire value proposition of this product — an agent that *adapts* — remains **completely unproven end to end**. The agent exists, is tested, and has never once driven a real lesson.

We proved the floor. We have not touched the ceiling.

---

## 2. What is now known to be true

Each of these was uncertain a day ago and is now settled by measurement, not argument.

| Claim | Evidence |
|---|---|
| A lesson runs with the LLM absent | I1: hook → vocabulary → choice → graded → branched, live WS, zero LLM calls |
| Reflex tier is genuinely fast | real mouse click → graded reveal, sub-second end to end; core's own bench 1.4 ms |
| Contract-first parallel building works | 4 services built independently by 4 agents, integrated with only boundary bugs |
| Live TTS is not a bottleneck | Piper warm: 100–190 ms EN, 96–132 ms VI. The published 1,510 ms figure is cold start |
| Whisper cost is per *call*, not per second | always a 30 s window. `large-v3-turbo` 11.5 s vs `tiny.en` 0.66 s, same accuracy on clean audio |
| The hosted model does what we need | tool calling picks a valid `action_id`; `thinking:{"type":"disabled"}` top-level suppresses reasoning |
| AIRI's audio pipeline is reusable without Vue | ~2,200 lines vendored verbatim; AIRI's own motion-manager test passes against our port with 2 lines changed |
| Emotions on a real model need config, not constants | Haru has no per-emotion motion groups. Verified against the actual `.moc3` in a Node VM |

---

## 3. What is still entirely unproven

This list matters more than the one above.

> **Updated the same day.** The first two rows below were resolved within hours
> of writing this section — see §10. They are kept here because the reasoning
> that produced them is what made resolving them the obvious next move.

| Unproven | Why it matters |
|---|---|
| ~~**The agent teaching anything**~~ | ✅ **RESOLVED** — see §10 |
| ~~**`available_actions` in a real loop**~~ | ✅ **RESOLVED** — see §10 |
| **Memory and recall** | Schema exists, `classroom_recall` exists, nothing has ever written or read a real observation |
| **Background work** | Scheduler runs; the jobs are wired to a no-op seam |
| ~~**Speech in the loop**~~ | ✅ **RESOLVED** — Piper drives the lesson's narration in the browser |
| ~~**The avatar moving**~~ | ✅ **RESOLVED** — Hiyori Pro renders and lip-syncs from the audio |
| **The agent and the voice together** | ⚠️ **New gap, and it is real.** The agent was proven through a silent dev endpoint; speech was proven with no agent. They have never run in the same session |
| **Anything pedagogical** | Not a single claim about whether this teaches English |
| **Lesson-authoring cost (SP-0)** | Still the #1 project risk. Still untouched |

---

## 4. The most useful thing we learned

**293 unit tests passed while four real bugs sat in the seams between components.**

Every single bug was at a boundary, and not one was inside a component:

| Bug | Boundary | How it hid |
|---|---|---|
| Two WS connections, stage frozen | React lifecycle ↔ socket lifecycle | fake-socket tests never opened two real sockets |
| Console showed FULL while agent was dead | connect handshake ↔ event semantics | `mode.changed` fires on *change*; nobody tested *connect while already degraded* |
| Emotion map off by one | my config ↔ the model's own key spaces | `Name` and `File` overlap case-insensitively; wrong expression, no error |
| `speaking` flapping per segment | playback queue ↔ lip-sync release tail | each clause looked correct in isolation |

Three of the four were **silent** — no exception, no error log, output that looked plausible. The emotion one would have shipped: every emotion one off, nothing to notice unless you know what `happy` should look like.

**Implication for how to spend effort next:** more unit tests on the existing components have low expected value. Integration tests across seams have very high expected value. The remaining work is almost entirely seams.

---

## 5. Is the architecture holding up?

Honest scoring of the decisions in docs 00–08.

| Decision | Verdict |
|---|---|
| **NS-1** lesson runs without LLM | ✅ **Validated.** Not just true — it is what let us build and demo before the agent existed |
| **NS-2** two control tiers | ✅ **Validated.** The reflex path never touches the agent and is sub-second |
| **NS-3** semantics not DOM | ✅ **Validated.** The UI was built from `PROTOCOL.md` alone, against no running backend |
| **NS-4** runtime replaceable, contract is not | ✅ **Validated in a way I did not expect.** The contract survived four independent implementations; the *runtime* choice (Hermes) was deferred entirely without cost |
| **NS-5** state in core, not chat history | ✅ **Validated.** Restarting the agent, the UI, or core loses nothing |
| Contract-first with a frozen PROTOCOL | ✅ **The single highest-leverage decision made.** Four parallel builds, integration bugs only at seams the protocol did not specify — which is exactly where PROTOCOL §9 now exists |
| 4-tool `available_actions` surface | ⏳ **Unproven.** One synthetic turn is not evidence |
| Deferring Hermes for `DirectAgent` | ✅ **Correct so far.** Zero framework friction; the agent was the fastest component to build |
| Deferring local model to hosted MiMo | ✅ **Correct.** Removed three Tier-0 spikes from the critical path for one config line |
| Live2D before VRM | 🟡 **Cheap so far, but the character question is unanswered** and it is a product question, not a technical one |

**Nothing in the architecture has had to change.** The corrections have all been to *facts I got wrong* (TTS latency, STT model, emotion mapping), not to structure.

---

## 6. The risk register, honestly re-ranked

| # | Risk | Movement | Where it stands |
|---|---|---|---|
| 1 | **Lesson-authoring economics (SP-0)** | ⬆️ unchanged, now more urgent | Every day the skeleton improves without this being answered increases the sunk cost of a wrong answer. **The single most valuable thing anyone could do this week** |
| 2 | **The agent has never taught** | ⬆️ **new #2** | We built the stage and never brought the actor on. This is now the biggest *unknown*, and it is cheap to test |
| 3 | Teacher control (SP-10) | ↔️ | The console is built and looks good. Never put in front of a real teacher |
| 4 | Character is wrong for the audience | ↔️ | Licensing is settled and small. Design is unanswered and is not engineering's call |
| 5 | Building against a strong model, deploying a weak one | ⬆️ | Now real: MiMo is far above Gemma 4 E4B. Every day of agent work on MiMo is a day of unvalidated assumptions about E4B |
| 6 | Offline promise quietly dies | ↔️ | One outbound host. The `TeacherAgent` seam holds. Watch it |
| — | ~~Model plumbing (SP-1/SP-2/SP-4)~~ | ⬇️⬇️ | **Off the critical path entirely** thanks to the hosted model |
| — | ~~TTS latency~~ | ⬇️⬇️ | **Resolved by measurement.** Was never real |

---

## 7. What to do next, in order

The ordering follows from §3 and §6: prove the unproven, cheapest and most informative first.

```
N1  Wire the agent to core                     ← the whole thesis, and it is a day
      DirectAgent + ToolExecutor -> classroom-core
      Prove: it picks activities, grades adapt, mode goes FULL
      Prove: kill the agent mid-lesson -> DEGRADED -> class continues (I2)

N2  Wire speech                                ← the service exists and is measured
      speech.say -> /audio/speech -> AudioBuffer -> playback queue
      Now the lesson talks

N3  Wire the avatar                            ← 164 tests, never mounted
      Live2DAvatar into AvatarLayer, ACT tokens -> emotion, lipsync from audio
      ★ Phase 1 demo complete ★

N4  Memory loop                                ← proves "it remembers"
      record_observation -> DB -> recall -> next session greets by name

N5  Integration suite I2-I10 as real tests     ← the seams are where bugs live
```

**In parallel, by a human, not by engineering:**
- **SP-0** — author one complete lesson, measure the hours. Nothing engineering does substitutes for this number.
- **Character direction** — `docs/5-research/PROMPT-avatar-decision.md` is written and ready to run.

---

## 8. A caution I want on the record

The skeleton is good and it demos well. That creates a specific danger: **it is easy to keep polishing the part that works.**

The lesson player is the *floor*, not the product. A school watching it sees courseware — good courseware, but courseware. What makes this worth building is the agent noticing that Minh hesitated and dropping a scaffolding rung, and none of that exists yet.

If in two weeks the player is beautiful and the agent still has not taught a lesson, the project has drifted.

---

## 9. Numbers, for reference

```
source files      141   (excluding vendored/node_modules/.venv)
tests             293   88 core · 41 agent · 164 airi-bridge
services running    3   speech :8001 · core :8004 · ui :3000
models            1.7 GB   Piper 126 MB · Whisper 1.6 GB · Live2D 3.3 MB
outbound hosts      1   the model API. Everything else is localhost
docs               11   00-10 + PROTOCOL + research
```

Measured latencies that matter:

```
click -> graded reveal        sub-second (core bench: 1.4 ms)
TTS warm, English             100-190 ms
TTS warm, Vietnamese          96-132 ms
STT per call (small.en)       3.35 s     ← the slowest thing in the loop
agent turn (MiMo)             2.7-5.8 s  ← the second slowest
```

Those last two are the whole reason the reflex tier exists.

---

## 10. N1 done — the agent teaches

Written after §1–§9, on the same day. `services/classroom-core/agent_bridge.py`.

Core now computes `available_actions` from the lesson run (it never had them —
the 4-tool design and the runner had been built to two different pictures), the
agent picks one, core validates and executes. Verified live against MiMo across
every outcome the runner can produce:

| Outcome | Chose | Said |
|---|---|---|
| `correct` | `goto:q_legs` — advance | `<\|ACT {"emotion":"happy"}\|> Yes! A cat says "meow"! Great job, everyone!` |
| `wrong` | `goto:help_meow` — scaffold | `Almost! <\|ACT {"emotion":"think"}\|> Listen — a cat says "meow meow."` |
| `silence` | `goto:help_meow` | `It's okay! <\|ACT {"emotion":"think"}\|> Listen — *meow meow* 🐱` |
| `timeout` | `goto:help_meow` | `It's okay! Let me help you. <\|ACT {"emotion":"curious"}\|>` |
| `near` | `goto:help_meow` | `It's okay! <\|ACT {"emotion":"think"}\|> "meow, meow!"` |

~4 s per turn, ~1,510 prompt tokens, 512–1,024 cached, one round.

**What this actually demonstrates**, beyond "it works":

1. **The constrained-choice design holds.** The model never invented an action;
   it picked from the list core offered, every time.
2. **The scaffolding policy survives into behaviour.** It withholds the answer,
   drops a rung, stays in English, and distinguishes *silent* from *wrong* —
   "It's okay!" for silence, "Almost!" for a wrong answer. That is doc 00 §5
   showing up in output, not in a prompt.
3. **The agent emits `<|ACT|>` tokens unprompted**, exactly as PROTOCOL §5
   specifies. The embodiment bridge has a live producer before it has a
   consumer.

### Two bugs this found, both mine, both in the contract

**`classroom_say` bumped `state_version`, so the agent could never speak *and*
act in one turn.** Its own subtitle write invalidated its own decision. The very
first live turn produced a genuinely good hint and then threw the action away.
The `state_version` gate exists to reject decisions made against state that moved
*underneath* the agent — not against the agent's own side effects. `say` no
longer touches the store, which PROTOCOL §9.6 already made redundant anyway.

**`LastInteraction.outcome` could not express `silence` or `timeout`.** `BranchOn`
allows them, the runner produces them, and the type the agent sees rejected them
with a 500. So there was no way to tell the agent a child had gone quiet — the
single most pedagogically loaded signal in a classroom. Fixed in all three
mirrors as a shared `Outcome` type.

Both were **contract inconsistencies that only a live end-to-end turn could
surface** — 293 unit tests and four independent implementations passed straight
over them. That is the same lesson as §4, now with a third data point.

### What is still unproven

Everything else in §3 stands: speech in the loop, the avatar mounted, memory
actually remembering, background work, and any pedagogical claim at all.
And **SP-0 remains untouched and remains risk #1.**
