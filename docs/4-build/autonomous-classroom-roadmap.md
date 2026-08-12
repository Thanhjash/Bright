# Autonomous Classroom Product — competition roadmap

**Updated:** 2026-08-12  
**Authority:** current execution roadmap  
**North Star:** one autonomous AI teacher for 20–40 children on a shared board

This roadmap replaces feature-count planning with evidence gates. It deliberately
does not attach optimistic dates: work is ordered by dependency and product risk.
Move as fast as possible, but never declare a later gate while its evidence is fake.

Research and rationale: [CTO autonomous-classroom audit](../5-research/2026-08-12-cto-autonomous-classroom-audit.md).

## Implementation checkpoint — 2026-08-12

The first v3 vertical slice is mechanically green: Core 224 tests; agent 82 non-live
tests with four live-provider cases deselected; AIRI 165 tests; two mocked Chromium v3
flows; content 7 tests plus the lesson self-test. The Market Food candidate runs 37–39
minutes in headless simulation. This is implementation evidence, not a release claim.

| Gate | Current state |
|---|---|
| G0 product truth | **Mostly implemented:** Protocol v3/toolchain/CI/capability states; provenance and legal decisions remain |
| G1 real teaching product | **Candidate implemented:** full executable draft; curriculum approver unassigned |
| G2 classroom teacher spine | **Partial:** roster/fairness/assignments/checkpoint writes; memory, restore and pacing execution incomplete |
| G3 oral interaction | **Partial:** one answer-station sampled turn; full recovery and room evidence absent |
| G4 product UX | **Partial:** setup/status/emergency redesign and mocked Chromium gate; first-time facilitator proof absent |
| G5–G8 | **Open:** no real composed provider/room/hardware, local Gemma, appliance or governance proof |

## Competition-ready definition

A build is competition-ready only when it can run a real 35–45 minute lesson for a
20–40 learner roster, with the AI owning teaching decisions, pacing, participation
and recovery. The operator performs setup and room safety, not teaching.

The live demo may present a shorter excerpt, but it must use the same lesson,
runtime, recovery paths and hardware as the full autonomous rehearsal. There is no
separate “scripted demo product”.

## NOW — the shortest honest path

### G0 — Restore product truth

**Why first:** content artifacts and release claims cannot be trusted while the
compiler/runtime contracts disagree.

- Keep lesson compiler output aligned with Protocol v3 and keep self-test green. *(Implemented.)*
- Add CI for contracts, Python, UI/AIRI, content compile/lint/play and packaging.
- Create one clean-checkout command that builds, tests and produces an evidence manifest.
- Separate health into `liveness`, `readiness` and `teachable`.
- Treat speech/audio as a classroom capability distinct from agent mode; never call
  a silent, advancing lesson “offline-ready”.
- Lock the first learner wedge and name a curriculum approver.
- Verify the competition organizer/rulebook wording before public claims.
- Decide root code/content licences; add NOTICE/SBOM/asset-model-voice provenance.
- Replace stale status claims with the four-state release matrix.

**Exit gate**

- clean checkout produces a valid v3 lesson and runs all authored paths to DONE;
- CI, dependency/content/model hashes and test artifacts are tied to a commit;
- no restricted/unprovenanced artifact is silently bundled.

### G1 — One real teaching product *(candidate implemented; approval open)*

Build one teacher-approved 35–45 minute communicative lesson, not more fixtures.

Recommended arc:

1. hook;
2. comprehensible input;
3. whole-class chorus/gesture;
4. guided practice;
5. pair/small-group task;
6. sampled individual retrieval;
7. production/roleplay;
8. bounded EXPLORE;
9. exit check and closure.

Every activity needs timebox, correct/near/wrong/uncertain/silence/timeout outcomes,
an easier recovery and a safe default. Map outcomes to Vietnam 2018 + CEFR young
learner “can do” descriptors after the learner wedge is confirmed.

Instrument SP-0:

- human author/review hours separate from model time;
- branch/default coverage and headless no-stall simulation;
- narration duration, board density, locale coverage;
- media/audio/license provenance;
- pre-test, exit check, one-week delayed retrieval and transfer task.

**Exit gate**

- 100% executable paths reach DONE without manual Skip;
- one 20-minute equivalent costs no more than 8 human hours after tooling;
- curriculum approver signs content and assessment rubric;
- no public learning-efficacy claim before delayed/transfer evidence.

### G2 — Core becomes a classroom teacher *(spine implemented; policy execution partial)*

Add a Core-owned `ClassSessionController`; do not put this authority in Hermes.

Data model:

- classes, class members, attendance, session participants;
- session owner separate from current target learner;
- participation ledger and turn assignments;
- persisted lesson/session checkpoint plus startup restore;
- confidence/evidence-backed learner observations.

Deterministic policies:

- fair call queue, cooldown and students-to-check;
- selected individual / group / anonymous / uncertain answer scopes;
- session clock, stage time budgets and pace checkpoints;
- silence/noise/two-speaker/confused-class/failed-activity recovery;
- class energy reset and exit/closure;
- memory write only for a selected/confirmed learner.

Hermes receives minimal aggregate state and current target, then chooses only among
legal actions. It never receives or owns the whole roster.

**Exit gate**

- simulated 40-student session has no cross-student memory write;
- every learner is scheduled for at least one meaningful participation mode;
- named turns satisfy deterministic fairness/cooldown policy;
- agent restart does not lose Core state; Core restart restores roster, target, lesson
  and participation state from the checkpoint;
- the lesson can complete with Hermes/model/network absent.

### G3 — Autonomous oral interaction and recovery *(one sampled turn implemented)*

Use the minimum honest classroom topology:

- one answer position with a measured directional/handheld mic;
- AI calls the learner; next capture belongs to that learner;
- group/choral response never becomes individual evidence;
- automatic capture is state-driven; facilitator does not PTT every answer;
- no face/voice biometric identity in NOW.

Implement `unhandled_utterance` and bounded recovery:

- low confidence/noise → authored neutral retry;
- relevant off-script question → short Hermes response inside lesson boundary;
- unsafe/unrelated/ambiguous → neutral boundary and return to lesson;
- agent/TTS/ASR failure → immediate authored fallback and self-restart;
- correctness and conversational helpfulness remain separate.

**Exit gate**

- zero false accepts for wrong/silent cases in the consented release corpus;
- child stop-speaking → first meaningful sound p95 <2.5 s, hard fail >4 s;
- cancellation → local silence <100 ms;
- no feedback hole >2 s because authored backchannel is always available;
- room noise/two-speaker/echo paths never write confident individual memory.

### G4 — Product UX, not an engineering console *(first v3 redesign implemented)*

Target operator journey:

```text
Setup class → roster/attendance → choose lesson → audio/projector/mic preflight
→ Start → quiet autonomy status → Pause/Emergency/Resume → session summary
```

Required UX changes:

- Setup Wizard instead of env-only lesson/class selection.
- Stage shows whom the AI called, response mode and clear turn-taking cues.
- Control prioritizes “what Bright is doing, why, what is next, room readiness”.
- Keep Pause/Emergency/Resume prominent; move Back/Skip/Repeat/Takeover behind a
  recovery/debug disclosure, require reason, and log their use.
- Resolve the physical topology: how Stage and authenticated Control appear on the
  actual appliance, not merely as two URLs.
- Test projector contrast, long Vietnamese, 100–150% scaling, touch targets,
  disconnected/degraded states, avatar failure and mic/audio-device changes.
- Make emergency controls sticky at `1024×768` and `1366×768`; use clear focus styles
  and guarded activation for destructive/emergency actions.
- On required speech failure: stop progression, retry, use cached/pre-generated
  audio, then enter an explicit safe pause with actionable recovery.

**Exit gate**

- a first-time facilitator starts unaided after cold boot;
- zero routine pedagogical taps in three full sessions;
- Pause/Emergency/Resume is found and completes in <10 s;
- one physical voice per turn; no overlapping Stage/Control output;
- keyboard, touch and projector viewport E2E pass in Chromium.

### G5 — Real composed product evidence

Replace the Core-wire smoke as release proof with a composed harness:

- two real Chromium contexts: Stage and Control;
- Core + AIRI + Piper + ASR + pinned Hermes;
- real playback events, not Python-fabricated ACKs;
- modes: authored-only, ScriptedAgent, hosted Hermes, model killed mid-turn;
- capture TTFT, ASR, TTS, first-audio, cancellation and reflex distributions;
- 35–45 minute soak and target audio hardware.

Keep the existing Core-wire smoke, but label it correctly as a protocol smoke.

**Exit gate**

- three consecutive full autonomous sessions: zero crashes/stalls and zero routine
  operator teaching decisions;
- model/network killed mid-session: lesson completes and mode visibly degrades;
- reflex p95 <100 ms under full load;
- cold boot → teachable ≤3 min;
- no uncorrelated/stale terminal or memory mutation.

### G6 — Local Gemma/OpenVINO competition path

Preserve the Option B seam. Bright only talks to Hermes; provider/model/base URL are
profile/deployment concerns.

- Pin Hermes runtime/config and test real MCP/SSE behavior.
- Build one provider conformance suite for hosted and local.
- Add OVMS/Gemma service/image for the target Intel box.
- Test legal action selection, schema validity, policy boundary, stale tools,
  cancellation and no-parallel mutation.
- Measure 2K/4K context, TTFT/decode, RSS/PSS, thermal and sustained 45-minute load.
- Verify local endpoint before enabling `local-trusted` privacy policy.
- Keep dedicated ASR canonical; evaluate Gemma native audio later behind `AsrProvider`.

**Exit gate**

- tool selection ≥85%, schema validity 100%, critical policy violation 0;
- target decode ≥8 tok/s while classroom latency gates remain green;
- no swap/thermal collapse during a 45-minute session;
- killing Hermes/Gemma still completes the authored lesson 100%.

### G7 — Appliance, recovery and offline distribution

- Pin OS, Python, Chromium, drivers and architecture-specific wheels.
- Make blank-image installation fully offline, including Hermes/Core dependencies.
- Persist checkpoint atomically and resume safely after Core/power loss.
- Add watchdog, disk-full policy, DB backup/restore and privacy-safe diagnostics.
- Sign USB packs with a baked public key.
- Version and rollback app + content + model + DB migration as one release.
- Fault-inject power pull, full disk, corrupt WAL/DB, missing audio and killed services.

**Exit gate**

- 10 power cuts: no corruption; resume correct activity ≤30 s;
- interrupted USB update leaves active release unchanged;
- incompatible update rolls back the whole stack;
- zero-internet boot and lesson completion;
- support bundle diagnoses injected faults without child data/secrets.

### G8 — Child safety, privacy and legal ship

- Data inventory with purpose, retention and deletion per field.
- Institution + guardian/child consent, withdrawal, export/delete/correct workflow.
- DPIA and cross-border assessment while hosted inference exists.
- Pseudonymous learner IDs and device-theft policy/encryption decision.
- Real capability auth for Stage/Control/admin; per-device secret rotation/recovery.
- Root LICENSE, THIRD_PARTY_NOTICES, SBOM, model/voice/media/content licence manifest.
- Replace Hiyori/Haru with an owned/cleared child-tested character.
- Collect child/room recordings only after approval and consent workflow exists.

**Exit gate**

- raw transcript/audio cannot be recovered from logs, DB, backups or support bundles;
- delete/withdrawal removes all intended copies;
- signed update is mandatory;
- no restricted asset is in distribution bundle;
- privacy/legal/curriculum owners sign the release evidence.

## Competition release gates

| Gate | Required evidence |
|---|---|
| R0 Reproducible | Clean checkout/image builds offline; CI green; content/compiler/runtime contract aligned |
| R1 NS-1 | Network + Hermes + Gemma absent; real lesson completes |
| R2 Composed | Real browser Stage/Control + AIRI + speech + Hermes; no fake playback ACK |
| R3 Autonomous class | 20–40 roster, fair AI call queue, automatic capture, no adult teaching loop |
| R4 Ecological safety | Consented child/noisy-room corpus; zero false praise/accept for wrong or silence |
| R5 Performance | Reflex p95 <100 ms; response first-audio p95 <2.5 s; stable thermal/RAM |
| R6 Recovery | Service/browser/power failures self-recover; release rollback is atomic |
| R7 Local Intel | Gemma/OpenVINO provider, tool, latency and resource conformance on target box |
| R8 Human factors | New facilitator starts unaided; emergency action <10 s; three full autonomous runs |
| R9 Governance | Consent, DPIA, delete/export, licences, SBOM and signed updates complete |

## NEXT — after the first autonomous vertical slice

- Authoring Studio: branch preview, teacher approval/versioning, voice/media generation.
- One coherent 4–6 lesson unit with skill graph and spaced retrieval.
- Roster-scoped longitudinal memory, absence handling and correction UX.
- Two to three consented classroom pilots; instrument every intervention cause.
- Signed content packs, backup/export/delete and educator-readable diagnostics.
- Owned character validated for attention/listening/turn cues, not attachment mechanics.

Pilot gates: ≥90% sessions complete without technical help; emergency recovery <10 s;
no privacy/safety incident; learning evidence directionally positive on immediate,
delayed and transfer measures.

## LATER — scale only after product proof

- Locale Pack contract: UI, fallback language, ASR/TTS, curriculum mapping, cultural
  assets, fonts, accessibility, safety strings and licences.
- Offline fleet/channel distribution with signed packs and rollback.
- Privacy-safe aggregate analytics when a device reconnects.
- Additional locales and accessibility modes.
- Camera/perception/identity only after measured need, consent and accuracy gates.
- Pronunciation score only after child/accent calibration.

## Explicitly not NOW

- copying/embedding Hermes into AIRI;
- replacing dedicated ASR with Gemma audio before provider and room benchmarks;
- face recognition, voice biometrics or automatic identity claims;
- full-duplex always-listening classroom audio;
- a fleet cloud/LMS before one appliance teaches reliably;
- producing many lessons before SP-0 authoring economics is known;
- decorative avatar polish before ownership, turn cues and classroom legibility;
- public “AI teaches better” claims without delayed and transfer evidence.

## Immediate execution order

1. Close remaining G0/G1 governance: curriculum approval, competition wording,
   licences/provenance and reproducible evidence artifact.
2. Complete G2 execution: stage budgets/pacing/recovery, class-aware memory and Core
   checkpoint restore; prove a simulated 40-learner full session.
3. Expand G3 from one sampled answer-station turn to all authored oral/recovery paths.
4. Run real composed Chromium + Stage/Control + AIRI + Piper + ASR + pinned hosted
   Hermes tests, then repeated full-session and room gates (G4/G5).
5. Run local Gemma/OpenVINO conformance and appliance hardening in parallel once
   the real workload exists (G6/G7).
6. Governance is continuous, with a hard gate before child recordings or shipping (G8).

The fastest path is not fewer gates. It is removing work that does not prove an
autonomous class, and running independent evidence workstreams in parallel.
