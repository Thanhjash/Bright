# BUILD TRACKER

## ⏱ Deadline: 5 days to a finished product, 7 days buffer, then present

Intel × UN competition. That reorders everything below, and the reordering rule is simple:

> **Ship what a judge will see working. Cut what only an engineer would notice.**

What that means concretely:

| | |
|---|---|
| **Must ship** | A demo that cannot fail in the room. The five placeholder activity types. Voice latency low enough that a child does not look confused waiting |
| **Deliberately NOT in these 5 days** | Local Gemma on OpenVINO · Hermes harness · pronunciation scoring · multi-language config |
| **Why deferring is safe** | `TeacherAgent` is an interface. Gemma is one class plus a `base_url`; Hermes is the same seam. Neither is a rewrite, so neither is a reason to spend days now |
| **The one thing that must not slip** | NS-1. A demo that stalls in front of judges because a network call hung is the single worst outcome available, and the LLM-free path is the insurance that already exists |

**The worst measured number is voice: 3.2–4.4 s from a child speaking to a transcript on screen.** That is the latency a judge feels. Three independent reviews are running on it.

---

**Living document.** Update on every merge. If this file and reality disagree, fix this file first.

Last updated: 2026-08-11

---

## Status board

| ID | Component | Owner | State | Blocks |
|---|---|---|---|---|
| B0 | `packages/contracts` | lead | ✅ **done** | — |
| B1 | `services/classroom-core` | agent A | ✅ **done** — 88 tests, I1 verified live | B3 exec, integration |
| B2 | `apps/classroom-ui` | agent B | ✅ **done** — browser-verified E2E against live core | B4, B5 mount |
| B3 | `services/agent` | agent D | ✅ **done** — 41 tests pass, live-verified | — |
| B5a | `packages/airi-bridge` | agent C | 🔨 building | B5 |
| — | `services/speech` (Piper + Whisper) | lead | ✅ **done** — running, measured | B4 |
| — | model assets in `models/` | lead | ✅ **done** — TTS, STT, Live2D all fetched | B4, B5 |
| — | `scripts/fetch-models.sh` | lead | ✅ **done** — idempotent, documented | — |
| — | root workspace + run scripts | lead | ⏳ next | everything |
| B5a | `packages/airi-bridge` | agent C | ✅ **done** — 164 tests, real `.moc3` loaded in a Node VM | B5 |
| **N1** | **agent ↔ core bridge** | lead | ✅ **done — the agent teaches.** `agent_bridge.py`, live-verified across all 5 outcomes | — |
| B4 | speech wiring | lead | ✅ **done** — Piper TTS + wLipSync, measured | — |
| B5 | avatar wiring | lead | ✅ **done** — Hiyori Pro renders and lip-syncs | — |
| B6 | memory + background jobs | — | ⏳ waiting on B1 + B3 | — |
| — | integration + E2E | lead | ⏳ waiting on B1–B3 | demo |

Legend: ✅ done · 🔨 in progress · ⏳ queued · ⛔ blocked

---

## Definition of done

A component is **not** done until every box is ticked. No exceptions, no "will fix in integration."

### B0 — contracts ✅
- [x] `PROTOCOL.md` covers every wire format
- [x] TS mirror in `src/index.ts`
- [x] Python mirror in `python/bright_contracts/`
- [ ] a test asserting the two mirrors agree on field names *(deferred — do before Phase 2)*

### B1 — classroom-core
- [ ] `GET /health` returns mode + stateVersion
- [ ] `WS /ws` handshake: `client.hello` → `scene.snapshot`
- [ ] `seq` strictly monotonic per connection; `stateVersion` bumps on every mutation
- [ ] `POST /dev/scene` and `POST /dev/say` work (B2 depends on these)
- [ ] `GET /assets/{path}` serves and 404s cleanly
- [ ] SQLite schema + FTS5 recall query returns sensible results
- [ ] **lesson runner plays the sample lesson start to finish with zero LLM calls** ← NS-1
- [ ] grading covers correct / near / wrong / silence / timeout
- [ ] branches followed; a missing branch falls back to the default without crashing
- [ ] mode auto-degrades on agent latency and emits `mode.changed`
- [ ] pytest green
- [ ] README: how to run, env vars, dev endpoints

### B2 — classroom-ui
- [ ] `/classroom` and `/control` both render
- [ ] WS client connects, handles `client.hello`, reconnects with backoff
- [ ] **seq gap → discards local state and takes a fresh snapshot** (never patches across a gap)
- [ ] `SceneRouter` renders idle / text / image / vocabulary / choice fully
- [ ] unknown scene kind → visible error card, never a blank screen
- [ ] clicking a choice emits `interaction.choice` with <100ms visual feedback
- [ ] control panel buttons emit `control.command`
- [ ] mode badge shows only in DEGRADED/OFFLINE
- [ ] `VITE_MOCK=1` runs standalone with no backend
- [ ] `pnpm build` and typecheck pass
- [ ] readable from across a room: large type, high contrast, works projected

### B3 — agent
- [ ] `TeacherAgent` Protocol defined; `DirectAgent` implements it
- [ ] **live test proves `thinking:{"type":"disabled"}` suppresses `reasoning_content`**
- [ ] live test proves tool calling returns a valid `action_id` from the enum
- [ ] streaming SSE parsed into AgentEvents
- [ ] **rejects action_id outside `available_actions`**
- [ ] **rejects stale `state_version`**
- [ ] **single attempt — never retries a tool call in front of a class**
- [ ] system prompt is stable across turns (prompt caching)
- [ ] scaffolding ladder in the prompt; does not jump straight to Vietnamese
- [ ] pytest green (live tests skip cleanly without a key)

### B5a — airi-bridge
- [ ] `createLive2DLipSync` ported verbatim, works
- [ ] **ACT parser retains a 5-char tail; a token split across chunks never leaks as text** ← the #1 reimplementation bug
- [ ] unterminated token dropped at stream end
- [ ] `parseAct` handles bare-string emotion, `{name,intensity}`, numeric-string intensity, unknown emotion → undefined
- [ ] motion-manager ported; lipsync release tail + eye-blink quirk preserved
- [ ] **`getMouthOpen()` 0…0.7 written raw to `ParamMouthOpenY`** — not rescaled
- [ ] playback: 4-way concurrent TTS, strict text-order playback, failed segment stores null so the gate advances
- [ ] special fires *after* its segment's audio
- [ ] muting audio still dispatches specials
- [ ] no Vue / Pinia / vueuse in output
- [ ] MIT attribution headers on ported files
- [ ] builds, typechecks, tests green

### Integration (lead)
- [ ] all services start from one command
- [ ] UI connects to core, renders the sample lesson end to end
- [ ] agent drives the lesson; core validates and rejects bad actions
- [ ] kill the agent mid-lesson → mode drops to OFFLINE → **lesson keeps running** ← NS-1
- [ ] kill and restart the UI mid-activity → resnapshots and resumes correctly
- [ ] avatar speaks in sync with the board
- [ ] second session greets the student by name from memory

---

## Integration test plan

Nobody's unit tests catch these. They are the ones that matter.

| # | Test | Why |
|---|---|---|
| **I1** | ✅ **PASS 2026-08-11.** Sample lesson played end to end over a live WS with **zero LLM calls**: hook → vocabulary → choice → graded `correct` → branch narration → next question. No `seq` gaps. Answer-to-reveal was sub-second (core's own bench: 1.4 ms). | NS-1. The single most important test in the project |
| I2 | Kill the agent mid-lesson | mode must degrade, class must continue, no crash |
| I3 | Kill Chromium/the tab mid-activity, reload | resnapshot must restore the exact activity, not restart the lesson |
| I4 | Feed the agent a deliberately invalid `action_id` | must be rejected and fall back, not retried |
| I5 | Feed a stale `state_version` | must be rejected |
| I6 | Split an ACT token across two SSE chunks | must not be spoken aloud |
| I7 | Two rapid interactions before the first response lands | no state desync, no double-advance |
| I8 | Run a session, end it, start a new one | student remembered by name; `classroom_recall` returns real prior content |
| I9 | Unplug the network mid-lesson (Phase 1) | must degrade gracefully, not hang. Proves the seam is honest |
| I10 | Measure: interaction → visual feedback | must be <100ms (reflex tier, NS-2) |

I1, I2, and I6 are release gates. The others are strongly desired.

---

## 🔴 The number nobody had measured: turning the AI on makes it slower

Every latency row in this document was verified individually. **The column was never summed.** An external review asked for the composed figure; here it is, measured by A/B on the running system:

```
agent OFF (DEGRADED)    1.24 s     runs: 1.26 · 1.23 · 1.24
agent ON  (FULL)        4.45 s     runs: 4.08 · 3.78 · 5.50
────────────────────────────────────────────────────────────
the agent costs 3.21 s per answered question — 3.6× slower
```

For a spoken answer, add STT: **≈ 8.2 s from a child speaking to the board moving.**

So **FULL currently feels worse than OFFLINE.** The intelligence — the entire point of the product — makes it feel broken. The reflex tier does its job (feedback in 3–11 ms), and then the room sits in silence for four seconds.

Two related findings from the same session:

- **The sample lesson contains no activity that expects speech.** Voice input is built, core can grade speech, and the two have never met. An earlier attempt to measure the voice path actually measured a 20 s timer expiring, because the speech answer was correctly ignored by a `choice` activity. *A measurement that looks plausible and answers a different question is the recurring failure mode of this project.*
- The composed path was never run because each half was proven separately — the agent through a silent dev endpoint, the voice with no agent.

### The fix is already designed and was never built

[execution-plan §3](execution-plan.md) describes it: **pre-registration and the instant backchannel.** The dead air is not a compute problem, it is a turn-taking problem.

```
child answers
  →   3 ms   reveal (already)
  → ~100 ms  the teacher RESPONDS — speaking the authored branch narration
              that core already has, through the local TTS that already
              takes 100–190 ms
  →  ~4 s    the agent's decision lands and takes over from there
```

The child is never waiting. The four seconds still pass; they are simply full of teaching instead of silence.

This is **not** hardcoding a response. The authored narration is the floor that NS-1 already requires us to have; the agent adapts on top of it and overrides when it has something better. It is the same two-tier principle applied to *time* rather than to *decisions*.

**This is the highest-value work available before the demo.**

---

## Short answers break small ASR models — and point at the fix

Re-measured on the utterances children actually produce in class (one or two words), rather than the full sentences used the first time:

| Model | s/call | exact | the failures |
|---|---|---|---|
| `tiny.en` | 0.82 | 3/6 | **"Cat." → "Get."** · "Umm... dog?" → "I'm Doug." |
| `base.en` | 8.16 * | 4/6 | |
| `small.en` | 3.73 | 4/6 | "Umm... dog?" → "Um, dog?" ✓ |

\* anomalous — 1.80 s when measured alone. Four agents were competing for CPU. Treat the ratios as real and the absolute numbers as noisy.

**The first benchmark used full sentences and hid this.** Single-word answers are exactly what a class gives, and they are where a small model fails. Switching to `tiny.en` for its 2.9 s saving would buy that time by **marking a child wrong who answered correctly** — the worst trade available in a teaching product.

**But the failure names its own fix.** We know the expected answers: `{cat, dog, bird}`. Open-vocabulary transcription is solving a far harder problem than the one we have. Matching "Get." to the nearest candidate — phonetically, over three options — is easy, and it yields `tiny.en` speed with better-than-`small.en` accuracy, because the model is no longer guessing across all of English.

> ### ✗ CORRECTION — the claim below was wrong
>
> I wrote that constrained recognition would cut ~3 s. **It will not.** An external review checked the code: core already compares the **finished transcript** against `Expect.correct` / `acceptFuzzy` (PROTOCOL §9.4). That improves *grading* after transcription and does nothing to the 3.35 s Whisper call. Making the call itself faster would need the answer set **at the speech service** — a keyword-spotting or forced-alignment path that does not exist and is 2–4 days of work.
>
> Constrained recognition is still worth doing **for accuracy**. It is not a latency fix, and calling it one sent the deadline plan in the wrong direction.
>
> **The measured win is `small.en` → `tiny.en`: 2.69 s, for a config change.** Everything else on the list is inference, not measurement.
>
> Two further corrections to my mental model, both from reading the code rather than assuming it:
> - We are **not** recording a fixed 30 s. Push-to-talk stops on release (25 s cap). Whisper's 30 s *processing* window is why cost is per call — VAD endpointing cannot remove that.
> - **VAD is already enabled** inside `faster-whisper`. It trims silence within a submitted clip; it is not browser-side end-of-speech detection, and in push-to-talk the teacher's finger is a better endpoint than any room VAD.

---

## Defensive error handling hid a total failure

`build_turn_context` called `h.get("text")` on the `RecalledMemory` **objects** `db.recall()` returns. Every single call raised `AttributeError` — and was caught by this, which I wrote:

```python
except Exception as exc:  # noqa: BLE001 — never fail a turn on memory
    log.warning("recall failed: %s", exc)
```

So `recalled` stayed `None` forever. **Memory had never once reached a prompt.** The system reported itself healthy, every turn succeeded, and the feature simply did not exist.

The intent was right: a memory lookup must not take down a class. The mistake was letting "degrade gracefully" mean "degrade silently and permanently." A swallowed exception that fires on *every* call is not degradation, it is a feature that was never wired — and it looks identical to one that works.

**Rule going forward:** a catch-all that exists to protect a lesson must still be loud about *systematic* failure. Log once at `error`, surface it on the facilitator console, and make a test assert the happy path actually produces data — not merely that nothing threw.

This is the same shape as the Live2D chain below, and as the console reporting `FULL` while the agent was dead: **three separate silent failures now, all of which looked like working software.**

---

## The avatar, and what it cost to get there

Hiyori Pro (AIRI's own default character, fetched from AIRI's CDN) renders, idles, blinks, speaks through Piper, and lip-syncs from the audio. Measured: `mouthOpen` produced 146 non-zero samples out of 212 across 38 distinct values, peaking at exactly 0.70 — the documented ceiling.

Getting there took five wrong diagnoses in a row, all mine, and the pattern is worth keeping:

| I concluded | Actually |
|---|---|
| "AIRI ships no character model" | It ships Hiyori. The files are gitignored and downloaded at build time by a Vite plugin — so they are absent from a clone, which is what I looked at |
| "Haru fails because it is a directory model, not a zip" | Both failed, identically |
| "Vite is loading two copies of pixi-live2d-display" | One copy. My probe imported the module **without** the `?v=` query the app used — a different URL is a different module instance, so I measured the wrong object and read a working patch as broken |
| "The zip loader isn't applying" | It applied perfectly. Verified by driving it by hand |
| The real bug | `stage.ts` passed `{ url, id }` where the API requires a **bare string**. Every middleware that turns a source into settings is gated on `typeof source === 'string'`, so all of them silently skipped, and the error surfaced as the uninformative "Unknown settings format" |

Then the mouth still did not move: `createWebAudioBackend()` was called without `lipSyncProfile`, and its own docstring says plainly *"Omit to run without lip-sync — `getMouthOpen()` then always returns 0."* Audio played, `speaking` flipped true, the face sat still. Silent, again.

**The lesson that generalises:** a wrong measurement is worse than no measurement. Four of these five were confident conclusions drawn from a diagnostic that was itself broken. Before trusting a probe, prove the probe observes the same object the product does.

Two genuine API defects in `airi-bridge` were fixed on the way: `SpeechPlayerOptions.audio` was typed `AudioBackend<unknown>`, which — because `play(audio: T)` is contravariant — accepted nothing, not everything; and the `Profile` type was not re-exported, making the lip-sync option impossible to pass with types.

---

## Measured facts (supersede published benchmarks)

Everything here was measured on this project's own hardware on 2026-08-11. Where it contradicts a published number, this table wins and the docs have been corrected.

| Thing | Measured | Note |
|---|---|---|
| Piper load | 1.52 s | **paid once.** The "1,510 ms first-audio" benchmark is this, mislabelled |
| Piper TTS, warm, EN | **100–190 ms** | over HTTP. 0.07× realtime |
| Piper TTS, warm, VI | **96–132 ms** | quality good, exact round-trip through STT |
| Whisper `tiny.en` | 0.66 s/call | 3/3 exact on clean samples |
| Whisper `small.en` | 3.35 s/call | 3/3. **default** |
| Whisper `large-v3-turbo` | 11.5 s/call | 3/3. 17× slower for no gain — **rejected as the live model** |
| MiMo turn cost | ~1,480 prompt / 150–190 completion, 2.7–5.8 s | tool schemas are **44%** of the prompt |
| MiMo prompt cache | ~99% hit on repeat turns | drops to 512–1,024 when `available_actions` changes |

**Conclusions that changed the design:**
- Live TTS is *not* a bottleneck. Pre-rendering narration is now an optimization, not a requirement ([architecture](../design/architecture.md) §6).
- Whisper cost is **per call**, not per second of audio — it always processes a 30 s window. Short answers cost the same as long ones.
- `large-v3-turbo` stays in `models/` only for **offline post-class batch work**, where 11 s is irrelevant and quality is best.
- The STT benchmark used clean Piper audio and **cannot separate these models**. Real child speech in a noisy room will. Do not read it as "tiny is enough."

---

## Open blockers needing a human decision

| # | Blocker | State |
|---|---|---|
| **P1** | **Avatar: licensing + character design** | ✅ **not blocking Phase 1.** Verified 2026-08-11: the Cubism SDK Publication License is required only above **¥10,000,000 (~$67k USD) annual gross revenue**; individuals and small businesses are exempt. Haru is downloaded and legal to develop with. ⚠️ Two separate issues remain for release — see below |
| **P2** | ~~TTS provider~~ | ✅ **resolved** — Piper, EN + VI, running at `:8001`, measured above |
| **P3** | Throwaway lesson content | agent A generating a sample; Ms. Quỳnh's curriculum plugs in later |
| **P4** | Rotate the MiMo API key after prototyping | ⏳ open — it has passed through a chat transcript |
| **P5** | **Real child-speech audio for SP-7** | ⛔ open. Nothing else can settle the STT model choice |

---

## P1 in full — the avatar decision

Two issues that are easy to conflate. Only the second one actually matters.

### Issue 1 — licensing (small, and now quantified)

| Layer | Terms | Our exposure |
|---|---|---|
| **Cubism SDK runtime** (`live2dcubismcore.min.js`, required by `pixi-live2d-display`) | Publication License required only for a "Business" = **annual gross revenue > ¥10,000,000 (~$67k USD)**. Individuals and small businesses exempt | **None today.** Becomes a paid licence only if the project succeeds enough to cross the threshold — a good problem |
| **Haru model** | Live2D Inc. sample material. Free to develop against, **not ours to redistribute** inside a product | Must be replaced before shipping |
| **VRM alternative** | `@pixiv/three-vrm` is **MIT**. VRM is an open glTF-based format. **No runtime licence at all.** VRoid Studio is free and you set your own terms on models you create | Zero |

### Issue 2 — character design (the one that actually matters)

Haru is a Japanese anime character built as a *technical sample*. This product teaches English to children in under-resourced Vietnamese schools. **Even with a perfectly free licence, Haru is the wrong character.**

The real question is not "find a freely-licensed model." It is: **what should this AI teacher look like to a Vietnamese schoolchild?** That question must be answered regardless of licensing, and it belongs to whoever owns the product's identity — not to engineering.

### Decision

| Phase | Avatar | Why |
|---|---|---|
| Phase 1 (now) | **Keep Haru** | licence-exempt, already integrated, unblocks B5. Do not stop for this |
| Before any school demo | **Custom character** | product identity, not law |
| Long-term format | **VRM, not Live2D** | MIT runtime, zero licence exposure, we own the character, and VRoid Studio makes iteration cheap |

Cost of the eventual switch: port `VRMModel.vue` (~1041 lines) to react-three-fiber. `loadVrm()` in `vrm/core.ts` is already framework-free ([reusing AIRI](../design/reusing-airi-and-friends.md) §B), and r3f maps 1:1 onto TresJS (`useFrame`↔`useLoop`, `useThree`↔`useTresContext`). Keeping `airi-bridge`'s emotion dispatch **config-driven** (already required — see `models/live2d/bright-model.json`) means the swap does not touch application code.

**Sources:** [Live2D SDK Publication License](https://www.live2d.com/en/sdk/license/) · [business scale definition](https://help.live2d.com/en/sdk/sdk_007/) · [VRoid Hub VRM licence terms](https://vroid.pixiv.help/hc/en-us/articles/360016417013-About-VRoid-Hub-s-conditions-of-use-and-VRM-license)

---

## Findings from the agent build that need follow-up

Reported by the `services/agent` build, worth acting on:

1. **Tool schemas are 44% of the prompt, and the volatile `action_id` enum lives inside them.** That undercuts the "keep the system prompt stable for caching" plan from [Phase 1 plan](phase-1-plan.md) §4 — the tool block sits in the same cacheable prefix, so cache hits drop whenever `available_actions` changes. The structural fix is Tier C in [architecture](../design/architecture.md) §3 (constrained JSON in one completion, no tool block). Measure it against a small model before Phase 3.
2. **An `enum` is not constrained decoding.** [Doc 03](../design/architecture.md) §3 requires an invalid id be *impossible to emit*; today it is a strong hint plus a hard reject. The reject path is the real guarantee until the serving layer exposes grammar constraints.
3. **The model speaks through `classroom_say`, so the text stream has two sources** — `TextDelta` and the `say` argument. Any inline `<|ACT|>` the model writes lands inside the tool argument. B4/B5 must handle both paths.
4. **A rejection ends the whole turn**, discarding valid calls made earlier in the same round. Safe, but lossy. Revisit with eval data, not intuition.

---

## Risk register — live

| Risk | Status | Mitigation |
|---|---|---|
| Offline promise quietly dies | 🟡 watching | `TeacherAgent` seam; test I9; stated debt in [Phase 1 plan](phase-1-plan.md) |
| Building against a strong model, deploying a weak one | 🟡 watching | tool surface stays sized for E4B; re-run the same scenarios on a small model before Phase 3 |
| Lesson-authoring economics (**#1 project risk**) | 🔴 unaddressed | SP-0 in [open questions](open-questions.md). Not touched by Phase 1 |
| Teacher loses control of the agent | 🟡 partial | control panel in B2; SP-10 not yet run |
| First-audio latency (Piper ~1.5s) | 🟡 known | pre-render authored narration at authoring time ([architecture](../design/architecture.md) §6) |
| Live2D asset licensing | 🔴 open | P1 above |

---

## Next actions, ordered

1. ~~contracts~~ ✅
2. root workspace + one-command run — *lead, in progress*
3. TTS: install Piper, download an English + a Vietnamese voice, wrap in a tiny HTTP service — *lead*
4. Live2D model decision — *needs the human*
5. wait on B1/B2/B3/B5a, then integrate
6. run the integration suite, fix what it finds
7. demo
