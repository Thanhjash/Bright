# Review — the Changemakers teaching package and asset drop

**Date:** 2026-08-18
**Source:** `Changemakers - Inputs/` (assets) + a teammate-authored system prompt, operating policy, and Grade 3 Unit 1 teaching package
**Status:** review. Evidence and recommendations — **nothing here is doctrine until a `decisions/` file adopts it.**
**Reads against:** [NORTH-STAR.md](../../NORTH-STAR.md) · [teacher-agent-not-cassette.md](../../decisions/teacher-agent-not-cassette.md) · [teaching-loop.md](../../design/teaching-loop.md) · [tool-surface.md](../../design/tool-surface.md)

---

## 0. What actually arrived

| | Verified |
|---|---|
| Textbook | `Book - Grade 3.pdf` — **80 pages**, Global Success Grade 3 **Tập 1** (volume 1 of 2) |
| Audio | **108 MP3 tracks, 73.8 minutes**, mean 41 s — the whole book's audio, not just Unit 1 |
| Page images | **15 JPG + 15 PNG**, pages 1–15 only (`image N` = `page N+1`) |
| Total | 183 MB |

**Mapping check: the teammate's asset table is correct.** `9.jpg` is page 10, Unit 1 Lesson 1, and the Track 5 / Track 6 headphone icons are printed on the page exactly as the manifest claims. Spot-checked directly.

**This changes something material.** `content/library/` has been 8 markdown files and 1,777 words — the single biggest gap between the north star and reality, because the whole argument for running an agent harness is *"there is a large library and the teacher finds her own way through it."* An 80-page book with 74 minutes of native-speaker audio is that library. Remaining page images are extractable from the PDF ourselves; only volume 1 is present.

---

## 1. What is genuinely strong and should be adopted

Ranked by how much it improves Bright.

### 1.1 The safety and escalation policy — we have nothing, and this is the highest-stakes gap

Part 2 §3 requires the agent to **stop instructional flow and hand control to the facilitator** on: physical danger or fighting; visible emotional distress; equipment failure past one retry; **any disclosure suggesting abuse or neglect**; and class-wide disengagement past five minutes.

The abuse-disclosure handling is exactly right and worth quoting as written:

> the AI should not question further; it should say *"Thank you for telling me. Please talk to [facilitator name] now,"* and stop.

Our doctrine covers *technical* failure in detail ([teaching-loop.md](../../design/teaching-loop.md) §3) and **says nothing at all about human failure**. For a system pointed at children this is a bigger hole than any of the engineering gaps we have been tracking. Adopt substantially as written.

Also correct: the agent never enforces discipline beyond a verbal redirect. Physical or behavioural discipline is the facilitator's, exclusively.

### 1.2 The learners have three languages, not two — this corrects our north star

> *First language is an ethnic minority language (H'Mông, Dao, Tày), with Vietnamese as their functional second language and English as a third.*
> *Do NOT assume fluent Vietnamese comprehension.*

Our library declares `home_language: Vietnamese` and our scaffolding ladder ends in "home-language explanation". **For the actual deployment that is wrong.** Vietnamese is the *school* language, not the home language, and the bottom rung of our ladder may not land.

This does not weaken NS-7 — it proves it. It shows our declaration is too coarse. We need three slots, not two:

```
home_language      the child's mother tongue          (H'Mông / Dao / Tày …)
school_language    the shared classroom language      (vi)
target_language    what is being taught               (en)
```

The ladder's bottom rungs then read *school language*, and *home language* is a rung we may not be able to serve at all — which is itself worth knowing and stating honestly rather than discovering in a classroom.

### 1.3 Choral-first, individual-second

> *Always build confidence with whole-class repetition before calling on individuals. Never put a single student on the spot without a group warm-up first.*

This is a direct, practical answer to the shared-screen participation problem that
[the assessment research prompt](../prompts/PROMPT-classroom-assessment.md) Part 1 asks about, and it arrived before the research did. It belongs in a skill (`elicit-a-word`, `invite-an-individual`).

Paired with: *invite, never force*; treat silence and wrong answers as normal; never correct in a way that could embarrass a child in front of peers.

### 1.4 Assessment philosophy — independent convergence with our doctrine

> *No lesson-level grading, scoring, or ranking is shown to students. Assessment exists only as an internal signal.*

This is exactly our rule that the board holds the language and never a score, and that judgement lives privately in `record_evidence`. Two people reached it separately. That is the strongest evidence we have that the rule is right.

Also matching: *"never announce marks, compare children, or show a ranking"*, and *"if identity is not available, store anonymous class-level counts only."*

### 1.5 A legal basis for the consent policy

Part 2 §6 grounds face and voice processing in **Nghị định 13/2023/NĐ-CP**: children's facial and voice data is sensitive personal data; explicit verifiable guardian consent naming facial recognition and voice recording; **additional consent from the child if aged 7+**; **silence is not consent**; minimise retention; persist only derived pedagogical signals.

Our [identity decision](../../decisions/2026-08-18-identity-is-perception.md) has the right instincts — embeddings not photographs, consent enforced structurally, uncertain identity means no write — but **no legal citation**. Adopt the citation and the child-assent requirement, which we did not have.

### 1.6 TBLT as the named framework

Pre-task → Task Cycle → Post-task, with *communication over correctness*: at Pre-A1 a child who conveys the right meaning with imperfect grammar has succeeded; do not interrupt mid-task; save correction for post-task, brief and positive.

Our north star lists a nine-stage flow (HOOK → INPUT → … → EXIT CHECK) which is more granular but less principled and not a recognised framework. TBLT is the right spine, and the nine stages fit inside it.

### 1.7 Multigrade — a requirement we had never considered

Combined-grade classrooms are normal in remote highland schools. Their rule: alternate direct attention between grade-groups in bounded blocks (≈5 min) rather than running one linear script; differentiate complexity, keep the theme and vocabulary pool shared so groups rejoin for a whole-class close.

We have no concept of this anywhere. It is real and it changes what "the class" means.

### 1.8 Facilitator interface constraints

Operational messages to the facilitator in Vietnamese, teaching to students in English; facilitator messages *"short, actionable, and never requiring English literacy — a red alert icon plus a short Vietnamese phrase, not an English error log."*

That is a hard constraint on `/control` that we had not written down.

### 1.9 `listen_for_class_response(expected_phrases, timeout_seconds)`

A **class-level** listening primitive rather than individual ASR. This is a genuinely good idea and partly answers the shared-screen problem: detect whether the room said the thing, without attributing it to anyone. Worth carrying into the tool-surface work.

### 1.10 Pacing constraints and asset discipline

Max 2 new items per 10-minute block (G3–5), 4 for G6+. Wait 4 s after a question. 2–3 choral rounds before an individual invitation. And: *"do not call Google Drive at runtime; load all assets from local storage for offline operation"* — correct instinct, matches our appliance model.

---

## 2. Where it conflicts with locked doctrine

These are not criticisms of the work — the pedagogy is good. They are places where the *shape* would break something we already decided.

### 2.1 The package is structured as a cassette — this is the one real disagreement

`step_id: L1-01 … L3-11`, each with a scripted `ai_says`, a timing window, and a `state_order` state machine:

```
STARTUP_CHECK → PRE_TASK → TASK_BRIEF → TASK_PRACTICE
→ CHECK_UNDERSTANDING → POST_TASK → MEMORY_WRITE → END
```

and the instruction *"Treat this document as the authoritative lesson-flow specification. The agent must follow its `ai_says` … fields."*

That is a lesson player. It is precisely what the owner rejected on 2026-08-16 in
[teacher-agent-not-cassette.md](../../decisions/teacher-agent-not-cassette.md): *if the agent walks an authored graph, we did not need Hermes.*

**The honest version of the disagreement:** at Pre-A1, with a 4B local model, on a projector in front of thirty children, a tight script is *safer*. This document is the best argument for the cassette anyone has made. The counter-argument is the one already locked: a script does not survive the second subject, cannot handle what is not in it, and makes the agent decorative.

**The resolution — and it costs almost nothing.** Every piece of *content* in the package survives; only the *shape* changes. A unit playbook carries:

| Keep, as the map | Drop, as the script |
|---|---|
| the locked vocabulary bank, and *"do not teach `What's your name?` in this unit"* | `step_id` sequences with clock windows |
| the canonical final dialogue and success criterion | exact `ai_says` lines as lines to recite |
| which track and which page panel serve which purpose | `state_order` as an enforced machine |
| the phase shape (pre-task → task cycle → post-task) | "advance at minute 22" |
| the fallbacks — *if low participation, choral rehearsal then retry* | — |

The `ai_says` lines become **examples of good teacher language** the agent may read and imitate, which is genuinely useful for a small model. They stop being a tape.

The constraint *"do not advance because time elapsed if most of the class did not attempt the target phrase"* is excellent pedagogy and belongs in a skill. `state_order` in Core is the part that must not happen.

### 2.2 Tools take file paths

`display_image(input: image_asset_path)` and `crop_or_zoom_image(image_asset_path, region_or_activity_id)`.

NS-3: the agent never sees a path. `asset://` ids only, resolved and validated by Core, refused if they do not exist. This is a small fix and a non-negotiable one — a model that can name a path can name the wrong path.

`crop_or_zoom` by **activity id** rather than pixel region is the right instinct and should survive: *"do not project a full textbook page longer than needed; show the exact panel."*

### 2.3 Memory fields that could become invented profiles

```
student_memory:
  confidence_trend: [low/medium/high per unit]
  participation_pattern: ["responds well in pairs, hesitant individually"]
class_mastery_estimate:
  greeting: low|medium|high
```

`participation_pattern` is legitimate — it is the *working preferences* tier, and a real teacher would say it to a colleague. `confidence_trend` and `class_mastery_estimate` are one step from a label the model invented.

The rule that reconciles them is already in the north star: **if you cannot point at the observations behind it, it is not knowledge about a child.** Every one of these fields must be *derived* from counted evidence, rebuildable, and never written directly by the model as an impression.

### 2.4 The startup check versus "no buttons"

Part 2 §1 requires a mandatory three-point check with the facilitator — roster, grade mode, safety — before Phase 1.

This is **compatible**, but the framing needs care. The adult boots the appliance and confirms the room; that is not a teaching decision and not a per-utterance button. What must not happen is the check becoming a gate the teacher waits behind every session, or the facilitator being handed a decision about *what to teach*.

Grade mode and roster are better read from the **deployment declaration** (NS-7) than asked every morning, with the facilitator confirming rather than entering.

### 2.5 Vision policy is broader than our identity decision permits

Their allowed signals: raised hand, pair formation, general participation, student turn completion. Our decision says perception answers exactly one question — *which `student_id` is this*.

Their prohibitions are good and match ours (no emotion diagnosis, no biometric profiling, no scoring from face analysis). But participation sensing is a genuine expansion and needs its own decision: it is arguably reflex-tier signal rather than identity, and it never reaches the model as an image.

### 2.6 Copyright

Global Success is Vietnam Education Publishing House and Macmillan. The teammate flagged it correctly: fine for a private prototype, **not** for a donated global appliance.

That is now the **second** asset with this problem, alongside the Hiyori avatar. Both are the same class of risk, and the north star's rule is explicit: *every dependency must be legally shippable at zero cost; "free for now" is a liability, not a saving.*

Worth saying plainly: the textbook is the right thing to build the prototype against and the wrong thing to ship. The structure — a unit map, a locked vocabulary bank, a canonical dialogue, tracks and panels — is reusable with openly licensed or team-authored material. The pedagogy is ours; the pages are not.

---

## 2.7 One factual error in the package

The package locks the wellbeing answer as **"I'm good, thank you."**

The textbook says **"Fine, thank you."** — printed on page 12 in the model
dialogue and again in the Lesson 3 chant on page 14, and it is what Tracks 9, 10
and 14 say aloud.

This is not a style preference. The children hear the recording. A teacher
drilling a different wording than the audio produces a contradiction the class
cannot resolve and the teacher cannot explain.

`content/library/units/gs3-u1-hello/map.md` uses the book's wording, `keys.md`
accepts "Good, thank you" as `near` and models the book's line back, and
`test_the_unit_locks_its_own_vocabulary` pins it so it cannot drift again.

**Worth saying generally:** the locked vocabulary bank must be checked against
the recordings, not only against the page. This is the first thing to verify for
every future unit.

---

## 3. Recommended disposition

| Item | Action |
|---|---|
| Escalation / safety policy | **Adopt substantially as written.** Write it into doctrine — this is the largest hole in ours |
| Three-language reality | **Correct the north star.** `home / school / target`, not `home / target` |
| Consent policy + Nghị định 13/2023 citation + child assent at 7+ | **Adopt** into the identity decision |
| Choral-first, invite-never-force, communication-over-correctness, pacing caps | **Adopt as skills** (NS-6) |
| TBLT three-phase spine | **Adopt** as the frame; keep the nine stages inside it |
| Multigrade | **New requirement.** Needs its own design pass |
| Facilitator UX in Vietnamese, icon-first | **Adopt** as a `/control` constraint |
| `listen_for_class_response` | **Carry into the tool-surface work** |
| Unit 1 content, vocabulary lock, canonical dialogue, asset manifest | **Adopt as the first real unit playbook** — re-expressed as a map |
| `step_id` / `state_order` / scripted `ai_says` as authority | **Do not adopt.** Re-express as a map; keep the lines as examples |
| `display_image(path)` | **Do not adopt.** `asset://` only |
| `confidence_trend` / `class_mastery_estimate` as model-written | **Do not adopt** unless derived from counted observations |
| Copyrighted textbook pages | Prototype only. Replacement plan needed before any distribution |

---

## 4. What this does not settle

The core question in [the assessment research prompt](../prompts/PROMPT-classroom-assessment.md) — how thirty children answer on one shared screen with attributable evidence — is **not** solved here. Choral-first and `listen_for_class_response` are a partial answer for the *unattributed* half. The attributed half (which child produced what) still depends on identity, and the package correctly declines to solve it.
