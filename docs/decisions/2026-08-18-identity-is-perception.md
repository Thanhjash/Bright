# Decision: identity is a perception service, never a model judgement

**Date:** 2026-08-18
**Status:** LOCKED (boundaries) — **AMENDED same day, see the banner below**

> **Amendment, 2026-08-18 (later).** The *boundaries* in this document all stand:
> perception answers only "which `student_id`", uncertain identity means no
> memory write, embeddings are student data, the model never recognises anyone.
>
> What changed is the **mechanism ranking**. External research recommends against
> using facial recognition to solve classroom attribution at all — the problem is
> more cheaply and transparently solved by a named probe or a printed coded card
> scanned by the one camera we already have. Face recognition adds privacy,
> demographic-bias, pose, occlusion, enrolment and restart problems *merely to
> infer an identifier a printed code can simply state.*
>
> ```
> 1. a named probe — she asks a child by name, and knows who answered
> 2. a printed coded response card (the PaperClickers approach)
> 3. face recognition — only if 1 and 2 prove insufficient
> ```
>
> Face recognition is demoted from *the plan* to *a fallback we have not yet
> justified*. See [evidence-and-practice](2026-08-18-evidence-and-practice.md) §8.

**Implements:** [NORTH-STAR.md](../NORTH-STAR.md) §3 *"Identity is the system's job, not the model's"*, NS-5
**Reference implementation:** a teammate's `references/ClassroomAI_ai-core` @ `agent/initial-ai-core`

---

## Decision

A separate, boring, CPU-only service answers exactly one question:

```
image  →  [ {bounds, detection_score, student_id | null, similarity | null}, … ]
```

**Which existing `student_id` is this, and how sure are we.** Nothing else.

The teacher agent never receives an image, a face, an embedding, or a name it is
expected to match to a person. It receives an id, and through that id, that
learner's recorded evidence. A language model must never be asked to recognise
anybody — it cannot, and a confident guess about which child failed a question is
worse than no answer at all.

---

## Why a separate service

| | |
|---|---|
| **NS-2** | Recognition is reflex-tier I/O at camera cadence. It must never sit inside a model turn |
| **NS-5** | Perception establishes *who*. It does not establish *what they know*. Those are different stores with different truth |
| **NS-4** | The detector will be replaced as better small models appear. The `student_id` contract must not move when it is |
| Privacy | A component that touches child biometrics should be small enough to audit in an afternoon, and separable enough to remove entirely |

---

## What the teammate's implementation already gets right

Surveyed 2026-08-18. Two ONNX models from the OpenCV Zoo, pinned at tag `4.10.0`,
downloaded with SHA-256 verification, run through OpenCV on CPU with **no torch,
no CUDA, no GPU path**:

| Stage | Model | Output |
|---|---|---|
| Detection | **YuNet** `face_detection_yunet_2023mar.onnx` | normalised bounding box + confidence |
| Recognition | **SFace** `face_recognition_sface_2021dec.onnx` | 128-d embedding |
| Matching | cosine similarity vs. a local SQLite store | best match per subject, or unknown |

Practices worth adopting wholesale:

- **Embeddings only — raw photographs are never written to disk.** The image
  exists in memory for one call.
- **Consent is enforced by the schema, not by a checkbox.** The enrolment request
  type requires `consent_confirmed: Literal[True]`, so a request without it is
  rejected by validation before any logic runs.
- **Embeddings are scoped to the model that made them** — the store key includes
  a hash of the weights file, so embeddings from a retired model cannot silently
  cross-match against a new one. This is the single best idea in the component.
- **Every weight file is pinned by SHA-256 and fetched by a verifying
  downloader.** That is a supply-chain habit Bright should copy for all of its
  models, not just faces.
- **Clean seam.** The whole component is ~470 lines behind a small protocol
  (`recognize`, `enroll`), depending only on OpenCV, Pydantic and stdlib
  `sqlite3`. It lifts out without dragging in their agent, LLM, speech or UI.

## What we must not inherit

| Do not adopt | Why |
|---|---|
| The cosine threshold `0.45` as a production value | Their own docs call it "only a starting point". There is **no** false-accept / false-reject study, no lighting, distance, or demographic evaluation |
| Their `/health` returning 200 without checking the models actually loaded | Bright has been bitten by exactly this before — a green console over a dead component |
| An unauthenticated enrolment endpoint | Consent asserted by whatever process can reach the port is not guardian authorisation |
| The single-face frontend as evidence of classroom capability | Their backend returns every face; their UI keeps only the highest-confidence one and discards the rest. It is a self-check-in widget, not a roll call |
| Any use for attendance, grading, discipline, or access control | Their own assessment forbids it, and that constraint travels with the code |

**Their honest self-assessment (59/100, explicit no-go for classroom
deployment, biometrics flagged P0-unvalidated) is itself the most valuable thing
in the repository.** We should imitate the practice, not just read the result.

---

## Rules that bind Bright from the first line of perception code

1. **Uncertain identity means no student-memory write.** Below threshold, or two
   plausible subjects, or a face that arrived mid-answer → the observation is a
   classroom event and is discarded. Losing evidence is cheap. Recording a
   child's failure against a different child is not, and it is silent.
2. **Enrolment is deliberate and consented.** The camera matches; it never
   enrols by itself, and it is never shown on the projector.
3. **Embeddings are student data.** Same retention, same deletion, same access
   rules as the `observations` rows they point at. Deleting a learner deletes
   the templates.
4. **Detection never reaches the agent.** No boxes, no scores, no images cross
   into a model prompt.
5. **Calibrate before believing.** A threshold without a measured false-accept
   rate on real classroom images at real distances is a guess wearing a decimal
   point. Until that measurement exists, identity is advisory and evidence
   writes stay conservative.

---

## Sequencing

Identity is **Layer 5**, and this decision does not promote it. What it does is
prevent the two mistakes that would be expensive later:

- Building the teaching loop so that evidence has no subject
  ([the 1:1 audit](../NORTH-STAR.md) §3) — that is a **contract** problem, and it
  should be fixed while there is only one learner to migrate.
- Letting perception grow into the agent, or the agent grow into perception.

## Open questions for the owner

- Who performs enrolment in a real school, and who gives consent — the school,
  the guardian, or both?
- Is a camera acceptable at all in the first deployments, or should the first
  classroom releases bind identity some other way (a named seat, a card, the
  facilitator confirming a roster)?
- Do we adopt the teammate's component, or re-implement the same two models
  behind our own seam? Adoption is cheaper; a shared component across two teams
  needs an owner.
