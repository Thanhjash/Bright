# Deadline Review: Five Days to an Intel × UN Demo

**Reviewed:** 2026-08-11
**Scope:** repository snapshot inspected on 2026-08-11; no product code was changed.

**Freeze the product around one rehearsed, cloud-independent demo path; stop trying to make the breadth of the vision look finished.** The team should spend the five days cutting the voice wait, proving the exact room setup, and making agent failure invisible to the lesson. The current system has an unusually strong deterministic floor, but its judged differentiators—voice, autonomy, and offline intelligence—are either slow, reactive, or cloud-dependent. Shipping more activity types will not repair that contradiction.

> **Snapshot warning:** while this review was in progress, `SceneRouter.tsx` changed from routing five activity types to placeholders to routing new concrete components (`apps/classroom-ui/src/stage/SceneRouter.tsx:15-26,50-75`). Those components exist now; that does **not** make them demo-ready. The integration suite's stated coverage is I1–I10 around system seams, not targeted behavioral coverage of these five boards (`tests/README.md:117-130`), and `sentence_builder` explicitly says its drag semantics are an unproven protocol guess (`apps/classroom-ui/src/stage/BoardLayer/SentenceBuilderBoard.tsx:4-17`). Recommendations below use the final inspected snapshot, not the earlier tracker wording.

## 1. Voice Latency

**Verdict: switch the judged demo to `tiny.en` now, then use a real-room accuracy gate to decide whether to keep it. Do not build streaming ASR this week.**

The repository already contains the decisive measurement: `tiny.en` takes 0.66 s/call versus 3.35 s/call for `small.en`, while both scored 3/3 on three clean samples (`services/speech/app.py:42-55`). That is a measured **2.69 s reduction**, or about 80% of ASR compute latency, for an environment/default change rather than a new architecture. The default is still `small.en` (`services/speech/app.py:60-62`). Nothing else on the proposed list offers that much measured latency for so little engineering.

The caveat is severe, not cosmetic. The samples were Piper-generated, clean, noise-free English, and the source itself warns that real child speech will degrade `tiny.en` faster (`services/speech/app.py:52-55`). The prior research found no model validated specifically on children's L2 English and says off-the-shelf child/code-switched ASR should not be assumed (`docs/research/notes/2026-08-11-edge-stack-viability.md:53-62`). Therefore the switch is a **demo decision**, not evidence that `tiny.en` is the production model.

### Ranking: latency won per engineering day

Only the first row has a measured latency win in this repository. The other savings are explicit engineering estimates/inferences, not repo measurements.

| Rank | Option | Likely latency win | Engineering cost | Latency won/day | Judgment |
|---|---|---:|---:|---:|---|
| 1 | `small.en` → `tiny.en` | **2.69 s measured** | 0.25–0.5 day, including room test and rollback | **5.4–10.8 s/day** | Do it. Highest leverage by an order of magnitude. |
| 2 | Streaming/incremental ASR | Inference: perhaps 1–3 s to a useful partial | 3–5 days plus cancellation, UI/service protocol, and test work | ~0.2–1.0 s/day | Wrong week. It consumes the whole deadline and creates a new seam. |
| 3 | Constrained recognition against expected answers | **0 direct latency with the current implementation**; potentially a future faster/safer recognizer | 2–4 days for audio-aware constraint plumbing and evaluation | Unproven | Valuable for accuracy, not a five-day measured latency fix. |
| 4 | VAD endpointing | **Approximately 0 in the default push-to-talk path** | 1–2 days for reliable automatic endpointing | Approximately 0 | The teacher's button release already supplies the endpoint. |
| 5 | Start the LLM from a partial transcript | Inference: overlap some ASR and 2.7–5.8 s agent time | Streaming dependency plus speculative-turn cancellation/state work, 2–4 additional days | Worst dependency-adjusted return | Do not do it. A wrong partial can launch the wrong pedagogy turn. |

Two terminology corrections matter:

- The system is not recording a fixed 30-second utterance. Push-to-talk ends recording on release, capped at 25 seconds (`apps/classroom-ui/src/speech/micRecorder.ts:37-38,140-177`). Whisper's internal 30-second processing window is why compute cost is per call (`services/speech/app.py:42-44`). VAD endpointing cannot remove that model cost.
- VAD filtering is already enabled inside `faster-whisper` (`services/speech/app.py:200-208`). That filters silence inside a submitted clip; it does not provide browser-side end-of-speech detection. In default PTT mode, the human already provides more reliable endpointing than room VAD; the UI comments explicitly reject automatic mode as the default in a room with thirty children (`apps/classroom-ui/src/speech/useVoiceInput.ts:27-32`).

Constrained recognition is strategically correct but currently overstated. Core already compares the **finished transcript** against `Expect.correct` and `acceptFuzzy`; exact/containment and fuzzy rules are protocol-defined (`packages/contracts/PROTOCOL.md:200-203,355-370`). That improves grading robustness after transcription. It does not constrain Whisper decoding and does not make the 3.35-second call faster. A true expected-answer decoder needs the answer set at the speech service or a separate keyword/forced-alignment path; I did not find that plumbing in the repo.

### Concrete five-day recommendation

1. Make `tiny.en` the demo model.
2. On Day 1, run at least 30 rehearsed utterances from several non-native speakers in the **actual projected-speaker + demo-microphone arrangement**, with crowd noise. Include every accepted answer and plausible wrong answers.
3. Pass only if closed-answer grading is at least as reliable as `small.en` on that set and no wrong answer is systematically turned into a correct one. This threshold is a deadline recommendation, not an existing repo metric.
4. If it fails, revert to `small.en`; do not start an ASR research project. Mask the remaining wait with immediate deterministic acknowledgement and an explicit listening/thinking state. The UI already exposes named phases and timers (`apps/classroom-ui/src/speech/useVoiceInput.ts:48-74,160-180`).

Do **not** load both Whisper models and build a confidence fallback unless the Day 1 room test proves a specific repeatable `tiny.en` failure that `small.en` fixes. The service currently loads one model once at startup (`services/speech/app.py:93-119`); dual-model residency and retry logic add memory, cold-start, and another silent branch for an unmeasured benefit.

## 2. The 5-Day Cut List

**Verdict: ship one short lesson that proves voice, memory, adaptive scaffolding, avatar speech, and failure recovery. Cut every activity that does not strengthen one of those five moments.**

### Must ship in the judged path

1. **One authored 6–8 minute demo lesson, not a catalogue.** Use `text`, `image`, `vocabulary`, and `choice`, which are directly routed and already form the verified LLM-free path (`apps/classroom-ui/src/stage/SceneRouter.tsx:52-61`; `services/classroom-core/data/sample_lesson_run.json:15-77`). Add exactly one short, closed-set `speech` answer. The current sample lesson contains only choice expectations (`services/classroom-core/data/sample_lesson_run.json:57-77,132-153`), so “voice works” is otherwise a side-panel demonstration rather than part of the lesson.
2. **The returning-student greeting.** It is the cleanest visible proof that this is not generic courseware. Core performs a restricted `say_only` memory turn before the first activity and bounds failure so the lesson still starts (`services/classroom-core/app.py:113-124,145-202`).
3. **Two deliberate answer paths:** one wrong answer and one silence. The agent must use different language and select a legal scaffold path. Core exposes authored branch targets, repeat, next, and `say_only`—not arbitrary activities (`services/classroom-core/agent_bridge.py:117-179`).
4. **Avatar + real local Piper TTS.** This is already warm at classroom speed, and the speech driver is connected to real audio/lip-sync (`apps/classroom-ui/src/speech/speakingDriver.ts:1-15,37-70`). Do not polish it; merely prove the exact demo sequence does not interrupt itself.
5. **A rehearsed network/agent kill.** I1 proves the no-agent lesson path and I2/I9 define the relevant release behavior (`tests/README.md:121-130`). This should be a visible feature of the presentation, not a hidden engineering claim.
6. **Matching only as a conditional stretch activity.** A real component now emits normalized drag answers and paints optimistic feedback (`apps/classroom-ui/src/stage/BoardLayer/MatchingBoard.tsx:45-95`). Keep it only if a Day 1 browser test covers touch, mouse, correct, wrong, rapid second input, and fallback. If any one fails, remove it from the demo lesson; do not debug it during rehearsal week.

### Explicitly abandon or descope

| Cut from judged demo | Why |
|---|---|
| `sentence_builder` | It invents `slot1…slotN` client semantics that the protocol does not define, and its own comment says no authored drag lesson depends on the guess (`apps/classroom-ui/src/stage/BoardLayer/SentenceBuilderBoard.tsx:4-17`). High seam risk, low narrative gain. |
| `pronunciation` | The board admits scoring does not exist (`apps/classroom-ui/src/stage/BoardLayer/PronunciationBoard.tsx:2-6`). The north star forbids uncalibrated pronunciation percentages (`docs/NORTH-STAR.md:304-312`). A decorative phoneme board invites the exact judge question the product cannot answer. |
| `roleplay` | Its phrase selection is intentionally local and emits no event; actual grading is only the final speech event (`apps/classroom-ui/src/stage/BoardLayer/RoleplayBoard.tsx:13-17`). With no off-script conversation path, this is a prompt card, not AI roleplay. |
| `explore` | The visual component now emits point events (`apps/classroom-ui/src/stage/BoardLayer/ExploreBoard.tsx:15-19,32-44`), but the agent cannot leave the compiled lesson and `unhandled_utterance` is not built (`docs/NORTH-STAR.md:72-79`). Recreate the “world opens up” moment using tested image/vocabulary/choice primitives. |
| `video` | It remains an explicit readable placeholder; playback is not built (`apps/classroom-ui/src/stage/BoardLayer/stubs.tsx:1-24`). |
| Pronunciation scoring | Not started, needs real calibration data, and creates child-harm/reputation risk if wrong. |
| Local Gemma/OpenVINO implementation | Not run once; published numbers are on premium Lunar Lake and GPU support was reported as preview/nightly-dependent (`docs/research/notes/2026-08-11-edge-stack-viability.md:33-51`). Do not turn the five-day build into a serving-stack spike. |
| Hermes migration | `DirectAgent` already owns the required interface. A runtime swap adds no judged behavior (`services/agent/bright_agent/base.py:105-125`). |
| Global i18n / Vietnamese fallback configuration | Important product debt, irrelevant to whether this one demo survives. State it honestly in the deck. Do not build a localization system. |
| Avatar replacement or VRM port | Keep the sample for demonstration, label it “placeholder—not distributable,” and show the owned-VRM plan. No re-rig this week. |
| More board polish, animations, video, content breadth | The current risk is composed behavior, not visual scarcity. |
| Pre-rendering all narration | Piper is already 100–190 ms warm (`docs/archive/state-of-the-project.md:22-31`). This is optimization work, not the bottleneck. |

The tracker says the five placeholder activities “must ship” (`docs/archive/tracker.md:9-17`). That priority is wrong for a judged demo. Even after the late UI work, breadth remains weakly tested and does not repair the cloud/autonomy/voice story. Cut it.

## 3. What Is the Team Not Seeing?

**Verdict: the highest-severity invisible risk is ecological validity—the system can pass every current gate while failing with actual children in an actual room.**

The process is excellent at software seams and almost blind to the physical/pedagogical system boundary. The integration harness deliberately uses a fake LLM and fake TTS, and its browser path is UI → fake TTS and proxy → core → fake LLM (`tests/README.md:70-103`). The ASR comparison used three clean synthetic Piper samples (`services/speech/app.py:42-55`). The product target is 20–40 children around one projected screen with no technical operator (`docs/NORTH-STAR.md:87-98`), but the implemented runtime is explicitly one named student at a time (`services/classroom-core/app.py:65-67`).

That means all ten integration IDs can be green while these catastrophic truths remain undiscovered:

- the mic hears the projector/avatar or crowd more strongly than the selected child;
- `tiny.en` or `small.en` systematically mishears children's L2 speech;
- push-to-talk requires the facilitator to become a co-teacher and manage every speaking turn;
- the agent's “good” scaffold confuses, embarrasses, or talks over a child;
- thirty children cannot tell who was called on because the state model knows one student, not a room.

The safeguards miss this by design. I1–I10 protect state, sockets, rejection, memory persistence, network bounds, and tap latency (`tests/README.md:117-130`). They do not measure learning, group attention, classroom acoustics, operator workload, or child comprehension. The project status admits there is no pedagogical evidence (`docs/archive/state-of-the-project.md:35-52`). More unit or integration tests cannot close this gap.

The five-day response is not a study. It is one adversarial room rehearsal: projected audio on, the actual microphone, at least five people talking/noising, multiple non-native speakers, one facilitator who did not write the code, and the exact demo script. Log every time a human has to explain, restart, select a student, or rescue a turn. If the facilitator must make teaching decisions, the “autonomous” claim fails the north star's own test (`docs/NORTH-STAR.md:64-83`).

## 4. Architecture Judgment

**Verdict: today this is a lesson player with an advisory AI branch selector—AI garnish. The architecture can support more autonomy, but the product does not currently earn the label “autonomous teacher.”**

The control flow is unambiguous:

1. External code starts the lesson (`Core.start_lesson`), optionally asks the agent for a restricted greeting, then starts the deterministic runner (`services/classroom-core/app.py:93-124,145-202`).
2. The runner owns activity entry, narration, duration, grading, reveal, and authored branch fallback. It invokes the decision gate only after a graded outcome (`services/classroom-core/runner.py:493-534`; `services/classroom-core/agent_bridge.py:610-624`).
3. `AutoTurn` refuses to run unless mode is `FULL`, gives the model one bounded turn, and returns `None` on slow/broken/illegal behavior so the authored branch wins (`services/classroom-core/agent_bridge.py:650-715`).
4. Core—not the model—computes `available_actions`. The agent may select authored `goto` targets, `repeat_activity`, `next_activity`, or `say_only` (`services/classroom-core/agent_bridge.py:82-191`). The executor rejects any unoffered action and stale state (`services/classroom-core/agent_bridge.py:438-459`).
5. The prompt explicitly tells the model to pick exactly one action and finish quickly (`services/agent/bright_agent/prompt.py:22-44,118-128`). It does not hold a session loop or wake itself.

This constraint is good architecture. `available_actions` is not the reason the product lacks autonomy; it is the safety boundary that makes a small model viable. The problem is **initiative and authority over the arc**. The model cannot start the session, decide that an explanation has landed without an incoming outcome, accept an off-script question, choose a student from 30, create a new activity, or end the class unless Core calls it and offers a corresponding compiled action. The north star already records exactly these gaps (`docs/NORTH-STAR.md:72-79`).

Reactive-only invocation is a shallow code gap: Core could call the same bounded agent at session-start and activity checkpoints without changing the contract. **True autonomous teaching is not a five-day gap.** It also requires off-script utterance handling, multi-student attention, pacing over a whole session, and self-recovery. Do not widen tools or let the model control the DOM. If the team adds anything, add at most one visible, bounded initiative checkpoint—e.g. the existing memory greeting—and describe the demo honestly as “an offline-resilient adaptive lesson engine with an emerging teacher agent.” Do not spend this week relabeling an advisory branch hook as autonomy.

## 5. Demo Risk

**Verdict: the most likely room failure is the hosted MiMo turn timing out or becoming slow, producing repeated six-second holes exactly where the team claims offline autonomy. The cheapest insurance is a deterministic local scripted agent/fallback for the rehearsed lesson, plus a preflight that selects it before judges enter.**

The cloud dependency is direct and default: `DirectAgent` points to the hosted MiMo endpoint and reads its API key from the environment (`services/agent/bright_agent/direct.py:40-69`). Although the HTTP client allows 20 seconds, the classroom gate gives a turn 6 seconds (`services/agent/bright_agent/direct.py:51-54`; `services/classroom-core/config.py:108-116`). On timeout, `AutoTurn` returns to the authored branch, so the lesson survives (`services/classroom-core/agent_bridge.py:669-690`). That is good availability and bad theater: the judges still watch a long pause, and the adaptive sentence/action never arrives.

Worse, a failed live turn does not itself change mode in the inspected code; `AutoTurn` records the failure and returns `None` (`agent_bridge.py:669-715`). Mode changes happen in `ModeController.health_probe` (`services/classroom-core/modes.py:84-129`), whose default interval is 60 seconds (`services/classroom-core/config.py:118-121,173-175`). Therefore, **inference from the inspected control flow:** a cloud outage can cause repeated bounded failures until the next probe. I9 proves a black-holed turn is bounded and Core stays alive (`tests/test_i9_network_unplugged.py:30-49`); it does not make six seconds feel acceptable.

### Minimum-cost mitigation

1. **Create a deterministic `TeacherAgent` implementation for the one demo lesson**: keyed by activity/outcome, returning pre-approved `classroom_say` text and a legal current `action_id`. This is not a local LLM and must not be described as one. It is the reliable demonstration of the architecture's OFFLINE/DEGRADED behavior.
2. **Preflight the hosted model before the demo.** If it cannot complete two representative turns inside the chosen budget, start in scripted/offline mode. The current startup preflight checks files and Python dependencies but does not test MiMo reachability or credentials (`scripts/dev.sh:54-65`).
3. **Make the offline path the primary rehearsed path.** Use hosted MiMo only for one optional “live adaptive AI” moment. If it fails, the script continues without explanation or manual repair.
4. **Keep a local screen recording of the complete demo** on the laptop as catastrophe insurance. It is the backup for hardware/browser failure, not the presentation plan.

Do **not** attempt Gemma/OpenVINO from zero as the insurance policy. A new model server, model conversion/runtime, small-model behavior evaluation, and Intel-device performance are four simultaneous risks. The interface makes a later swap cheap (`services/agent/bright_agent/base.py:105-125`); it does not make an untested model reliable in five days.

### Other in-room failures to rehearse

- **First narration is silent.** Browsers suspend `AudioContext` until a gesture; the app only unlocks on pointer/key input (`apps/classroom-ui/src/speech/speakingDriver.ts:133-150`). The kiosk script carries the required autoplay flag (`infra/kiosk/kiosk.sh:81-86`). Use that exact launch path, not a casually opened browser tab.
- **Microphone blocked, missing, or owned by another app.** These are explicit runtime paths (`apps/classroom-ui/src/speech/micRecorder.ts:81-110`). Grant permission and close conferencing software before the room fills.
- **The demo lesson never exercises voice.** The shipped sample uses choice expectations, not speech (`services/classroom-core/data/sample_lesson_run.json:57-77,132-153`). Put one closed speech activity into the rehearsed lesson.
- **Teacher speech interrupts itself.** Every new `speech.say` starts an interrupting turn, not a queue (`apps/classroom-ui/src/speech/speakingDriver.ts:100-123`). The agent is prompted to speak and then act (`services/agent/bright_agent/prompt.py:26-33`); the chosen activity can immediately emit authored narration. Rehearse that exact transition and ensure the agent's line is not cut off.
- **Sample avatar becomes a judge credibility trap.** The current project decision keeps Haru for Phase 1, while separately stating the model is not redistributable (`docs/archive/tracker.md:293,306`). Call it a placeholder before a judge asks; do not imply it ships.
- **Compromised API key.** The tracker says the key passed through a chat transcript and must be rotated (`docs/archive/tracker.md:279`). Rotate it before public use.

## 5-Day Plan

| Day | Do—ordered by priority | Do **NOT** do |
|---|---|---|
| **Day 1** | Freeze the demo script and one lesson. Switch to `tiny.en`. Run the real-room 30-utterance ASR comparison against `small.en`; choose by results. Add the single speech activity to the demo lesson. Gate matching with a narrow mouse/touch/rapid-input test; cut it immediately if red. Rotate the MiMo key. | No streaming ASR. No partial-transcript LLM. No new activity implementation. No visual polish. |
| **Day 2** | Implement and test the deterministic scripted/offline agent path for the exact demo states. Add hosted-model startup preflight and an explicit automatic choice of cloud versus scripted/offline mode. Verify the lesson finishes with Wi-Fi disabled from before startup. | No Gemma/OpenVINO spike. No Hermes. No dual-Whisper fallback unless Day 1 produced a specific reproducible need. |
| **Day 3** | Run the complete judged path: start → remembered-name greeting → voice answer → wrong vs silence scaffold → avatar speech/lip-sync → agent/network kill → uninterrupted finish. Fix only failures in that path. Verify agent speech is not interrupted by authored narration. | No `sentence_builder`, pronunciation, roleplay, explore, or video in the demo. No pronunciation scoring. |
| **Day 4** | Conduct the adversarial room rehearsal with projector, speakers, actual mic, crowd noise, multiple speakers, and a non-developer facilitator. Exercise mic denial, browser reload, cloud blackhole, TTS failure, and the offline switch. Record timings and every human rescue. | No feature work triggered by aesthetic feedback. No avatar migration. No global-language configuration. |
| **Day 5** | Run all ten integration IDs and confirm the three release gates. Run the exact demo twice: once with hosted MiMo healthy, once with network absent. Freeze binaries/config/content. Capture the backup video and a one-page operator recovery card. | No merges after the freeze except a blocker on the rehearsed path. No dependency upgrades. No “one last” activity or animation. |

### Do NOT do, even if it feels strategically important

- Do not claim the hosted-agent demo is fully offline.
- Do not claim the current system is an autonomous teacher.
- Do not claim child-speech accuracy from three synthetic samples.
- Do not show pronunciation feedback that was authored by hand as if it were scored.
- Do not spend the seven-day buffer coding. Use it for daily rehearsal, the deck, judge Q&A, hardware duplication, and only drop-in asset replacement.
- Do not let the phrase “Intel competition” panic the team into an unbounded local-model integration. A reliable, honest deterministic offline demo plus a clearly isolated cloud agent is stronger than a broken OpenVINO checkbox.
