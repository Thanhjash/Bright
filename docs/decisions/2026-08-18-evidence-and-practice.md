# Decision: abundant practice, sparse evidence, honest uncertainty

**Date:** 2026-08-18
**Status:** LOCKED
**Source:** [Practice, Assessment, and Evidence for an Autonomous Whole-Class Teacher](../research/external/Practice,%20Assessment,%20and%20Evidence%20for%20an%20Autonomous%20Whole-Class%20Teacher.md)
**Answers:** the question deliberately left open in [tool-surface.md](../design/tool-surface.md)
**Authority:** [NORTH-STAR.md](../NORTH-STAR.md) §6 *what "personalised" means*, NS-5

---

## The decision in one sentence

> **Most of what happens in the room teaches. Only a little of it measures — and
> when measurement fails, we say so instead of guessing.**

The classroom is a different measurement environment from a tablet, and pretending
otherwise is the central error available to us. One microphone and one shared
screen cannot honestly produce thirty simultaneous individual assessments.
**Sparse truthful evidence beats dense fabricated evidence.**

```text
class interaction        → may change what she teaches next
                         → creates NO individual evidence

attributable probe       → may change what she teaches next
                         → MAY create one evidence row

ambiguous response       → no row at all
```

The forbidden move, stated so it can be checked in review:

```text
class chants "banana"  →  30 rows: productive banana = correct     ← NEVER
```

That single line violates attribution, productive-evidence validity, and the
reality of choral masking at once.

---

## 1. Attribution budget, not a choral ratio

Individual evidence comes from **named probes**: ask the question, give everyone
thinking time, *then* select. Never name the child before the thinking starts.

**Starting configuration: 8–12 named probes per 40-minute lesson.** In a class of
30 with even rotation that is roughly one named opportunity per child every three
lessons. Everything else — choral, hand signals, pairs, physical response,
discussion — is teaching, and produces no rows.

This is an operational default to instrument, **not a finding**. The research
looked for an evidence-based choral-to-individual ratio and did not find one: the
often-quoted 70/30 comes from a single small study that could not establish
either condition was superior. **Do not encode a ratio.**

Selection is **deterministic and auditable**:

```
least_recently_probed(objective)
  · number of attributable observations
  · was the last attempt no_decision
  · is productive evidence missing
```

It must **never** select on an inferred "shy learner", "weak student", ability,
personality, or a mastery number. Those do not exist here, and building a queue
that consults them would smuggle them into existence.

---

## 2. The evidence model — two axes, not one scale

**This replaces `correct / near / wrong / uncertain`.** That vocabulary is
readable but `near` silently merges six different things: an acceptable variant,
a dropped function word, doubtful pronunciation, an uncertain recogniser, a
partial hit, and a self-correction. Those have different teaching meanings.

```
decision:           supported | contradicted | no_decision
response_relation:  exact | accepted_variant | partial | other
reason_code:        asr_ambiguous | audio_noise | multiple_speakers
                    | incomplete_target | wrong_lexeme | target_form_error
                    | no_response | …
```

Read together:

| | Means |
|---|---|
| `supported + exact` | ordinary correct evidence |
| `supported + accepted_variant` | the key explicitly permits what they said |
| `contradicted + partial` | a real attributable response that fell short, in a defined way |
| `no_decision + other + asr_ambiguous` | *the child may well have said it; the microphone was poor* |

The principle underneath, which is the most valuable sentence in the research:

> **Uncertainty belongs to the measurement process, not to the child.**

`no_decision` is a first-class outcome, not an error path. A system that feels
less intelligent when the evidence is weak is behaving correctly.

### Evidence metadata

`mode: name | point | ask` is too thin. Record what was actually elicited:

| Field | Why |
|---|---|
| `language_mode` | reception · production · interaction — CEFR's vocabulary, reused rather than reinvented |
| `channel` | listening · speaking · reading · writing · physical |
| `elicitation` | independent · prompted · **imitative** · choral · peer_supported |
| `attribution` | individual · pair · class |
| `response_constraint` | selected · closed_constructed · open_constructed |
| `purpose` | practice · check · assessment |
| `attempt` · `repair` | first vs repeat; none / self-repair / prompted |
| `context_exposure` | familiar item · family variant · novel exemplar |
| `scaffold_used` | none · repeat · picture · simpler · model · L1 |
| `item_id` · `item_family_id` · `family_version` | provenance; detects a repeated context masquerading as a second observation |
| `judge_rule_version` · `asr_model_version` · `decode_mode` · `expected_set_id` | measurement provenance |
| `audio_quality_flags` | categorical clipping / noise / overlap |

Still no raw transcript, and no raw child audio retained by default.

### Delete the confidence number

`confidence = min(1.0, attempts/4)` reaching *certain* at four attempts is
indefensible — those four can share one picture, one day, one prompt, one
response mode and one scoring bias. **More observations do not cure construct
dependence.**

Report the evidence instead of a score:

```
productive / independent   supported 3 · contradicted 0 · no_decision 1
dates observed 2 · families 2 · novel exemplars 1 · last 2026-08-17
receptive                  supported on 3 attributable checks
```

Derived **coverage status** is allowed because it describes the dataset, not the
child: `productive evidence missing` · `needs another date` · `only prompted
evidence present` · `novel-context observation missing`.

---

## 3. Three tiers of content — the answer to authored vs generated

| Tier | What | May create evidence? |
|---|---|---|
| **A — authored items** | prompt, key, distractors, objective, evidence mode, elicitation, assets — all explicit | **yes** |
| **B — authored item families** | teacher declares a pattern and its permitted values; **Core** instantiates deterministically | **yes** |
| **C — model pedagogical language** | transitions, explanations, examples, encouragement, within a closed vocabulary | **never** |

The dividing line, checkable in code review:

> **If correctness cannot be derived mechanically from teacher-authored data,
> the activity must not create durable learner evidence.**

A 4B model may never invent an evidence-bearing question, key, distractor,
scoring rule, or target phrase. Distractors come from authored contrast sets:

```
fruit:
  target: banana
  contrasts: [apple, mango, orange]     ← safe
"invent two plausible wrong answers"    ← not equivalent
```

Authoring cost is the real counter-argument, and the answer is **factorisation**,
not free generation: teachers author objectives, slot sets, contrast sets and
family rules once; deterministic code produces the permutations.

When a family cannot be instantiated safely → **choose another authored family.**
Never → ask the model to improvise.

**Why this matters more here than anywhere else:** the small local model is
already the teaching agent. Letting the same weak model write the item, decide
the key, hear the child imperfectly, and judge the answer creates **correlated
failure across the entire evidence chain**.

### The gate that would reopen it

Free generation may become evidence-bearing only after validating the *exact*
deployed model, quantisation, prompt, language pair and item type — with a human
audit large enough to bound the defect rate (order of magnitude: zero critical
defects in ~600 independently reviewed items ≈ 95% upper bound near 0.5%). Passing
it for picture-vocabulary MCQs validates picture-vocabulary MCQs and nothing else.

Expect item-family expressiveness to pay off sooner than this gate.

---

## 4. Authoring syntax — ordinary markdown plus one bounded construct

Do **not** invent a YAML-heavy miniature programming language: clean for
engineers, progressively miserable for teachers. Keep prose as prose and add one
visible block:

```md
:::item {#banana-name type=speak objective=vocab.banana}
Show: asset://img/banana-03.webp
Ask: What's this?

Accept:
- banana
- a banana

Evidence: productive
Elicitation: independent
:::
```

```md
:::family {#fruit-point type=listen-point objective=vocab.fruit}
Pattern:
Point to the {fruit}.

Values:
- fruit: banana | asset://img/banana.webp
- fruit: apple  | asset://img/apple.webp

Choices: 3
Evidence: receptive
:::
```

A teacher can infer that without documentation. `[x]` in a choice list is
**authorial truth**, never a control that appears pre-ticked on the screen.

Author-facing vocabulary stays semantic — `type · objective · evidence ·
elicitation · use · accept · asset`. Never `widget`, `graderClass`, `toolCall`,
`jsonSchema`.

**And the file remains curriculum guidance plus an item bank — never a script.**
Prose says *how to teach*; item blocks say *which validated interactions exist*;
`Evidence:` says which probes can support which claims. The agent selects from
the bank; it is never obliged to execute the document. This is the same lock as
[teacher-agent-not-cassette](teacher-agent-not-cassette.md), reached
independently by an outside reviewer.

---

## 5. Judging speech

Constrained recognition over a small expected-answer set is the right approach —
**with a real no-decision path**:

```
audio → recogniser → does the evidence support one candidate?
                       yes → compare to the authored answer
                       no  → no_decision
```

not:

```
audio → force nearest of {banana, apple, mango} → compare
```

The second is a classifier masquerading as transcription.

| Method | Verdict |
|---|---|
| Normalised exact match | only when recognition is trustworthy |
| Fuzzy edit distance | candidate retrieval only — **never** the final judge |
| Phonetic matching | not for durable correctness until separately validated |
| Constrained decoding | **best closed-response approach**, with no_decision |
| LLM judging ASR text | **no** for durable evidence — it cannot recover acoustic information ASR already lost |
| Pronunciation score | **refuse today** |

Child L2 speech is exactly where ordinary ASR breaks, and worse: language-model
components can **repair the learner errors a teaching system needs to preserve**.
Reference figures on a comparable population sit near 0.30 WER. That can support
longer transcription; it is catastrophic as grounds for calling a one-word
beginner answer wrong.

---

## 6. Pacing, spacing, stopping, correcting

**Spacing: class granularity, not per-child.** Distributed practice has a
moderate pooled advantage over massed (d ≈ 0.54). Getting most of that benefit
needs only:

```
objective_id · introduced_at · last_class_practice_at
class_practice_count · last_individual_probe_at

due = introduced before AND not practised recently
      AND still lacking desired elicitation coverage
```

No SM-2, no per-child flashcard queue, no BKT.

**Stopping: dose-and-switch, not a mastery rule.** After a success, vary the
exemplar or the response mode rather than asking the same thing five more times.
After roughly two failures on the same representation, change the scaffold — do
not grind. The scheduler's question is *"what kind of elicitation has this
objective not yet had?"*, never *"has the child crossed 0.85?"*

**Correction: branch by failure type.** One universal ladder is not supported by
the corrective-feedback literature.

| Failure | Move |
|---|---|
| meaning / comprehension | repeat once → **gesture or picture** → simpler → concrete example → brief L1 gloss |
| lexical retrieval | wait → semantic or picture cue → partial form cue → model → imitate → **return later for independent retrieval** |
| production / form | brief recast → room for self-repair → explicit cue only if the form matters → keep communicating |
| communicative roleplay | lighter and less disruptive than controlled practice |

At Pre-A1 a picture conveys meaning faster than replacing incomprehensible
English with different incomprehensible English.

**A modelled correction followed by successful repetition is not independent
evidence.** Store the scaffold.

**Activity rhythm: 4–7 minutes** per interaction pattern before changing
participation mode. A product default to instrument, not doctrine. There is no
credible universal attention-span rule and we will not encode one.

---

## 7. The item types, and the traps

Core practice, no individual evidence: **choral response · chants and songs ·
TPR · hand signals / ABCD cards · think-pair-share · information-gap pairs.**

Core class check: **picture matching · multiple choice · listen-and-point.**

Primary individual evidence: **named picture naming · cold/warm calling** — one
child, after the room has rehearsed.

The traps, all of which look like evidence and are not:

| Trap | What it actually shows |
|---|---|
| **listen-and-repeat** | perception and imitation — **not** independent retrieval. Tag `elicitation: imitative` |
| **chants and songs** | a strong chorus completely conceals a silent child |
| **pointing / TPR** | listening comprehension, never oral production |
| **ordering, supplied-word sentence building** | if the words are on screen, there is no lexical retrieval |
| **repeated picture sets** | recognition of the artwork, not the word. Rotate exemplars |
| **public sequential multiple choice** | copying. Commit before reveal |

**Options:** default to three when two genuinely plausible distractors exist; two
for meaningful contrasts (he/she, singular/plural, confusable sounds). Never
manufacture a silly third distractor to lower the chance floor. **No
correction-for-guessing** over a handful of observations — precision without
validity.

**Listening sequence:** orient → show the response affordance → **no transcript**
→ play → protected wait → commit → optional second play → commit → *only now*
reveal the transcript. If readable text containing the answer appeared first, the
observation is no longer listening evidence. There is no evidence for "the
transcript must appear N seconds later"; the rule is construct-based.

---

## 8. Attribution without cameras — this reopens an earlier decision

The research is direct: **do not build facial recognition to solve classroom
attribution.** The problem is more cheaply and transparently solved by calling a
child's name, a seating and turn-taking scheme, or eventually **printed coded
response cards scanned by the one existing camera** — the PaperClickers approach:
one capture device, printed cards, no per-child electronics.

Face recognition would add privacy, demographic-bias, pose, occlusion,
enrolment and restart problems **merely to infer an identifier a printed code can
simply state.**

This conflicts with [identity-is-perception](2026-08-18-identity-is-perception.md),
taken earlier the same day, which adopted the teammate's YuNet + SFace component.
That decision's *boundaries* survive intact — perception answers only "which
`student_id`", uncertain identity means no write, embeddings are student data.
What changes is the **mechanism ranking**:

```
1. a named probe — she asks a child by name, and knows who answered
2. a printed coded card, scanned by the existing camera
3. face recognition — only if 1 and 2 prove insufficient, and only after
   the consent, calibration and bias work that decision already requires
```

Face recognition is demoted from *the plan* to *a fallback we have not yet
justified*. That decision is amended, not reversed.

---

## 9. Assets

No turnkey freely-licensed Pre-A1 children's item bank exists. Expect to author
the pedagogical bank ourselves. For the symbolic layer:

| | Licence | Ship it? |
|---|---|---|
| **Mulberry Symbols** | CC BY-SA 4.0 | **yes**, with attribution + share-alike |
| **OpenMoji** | CC BY-SA 4.0 (graphics) | **yes**, same |
| **Wikimedia Commons** | per file | yes, item by item, with a machine-readable attribution manifest |
| **Open English WordNet** | CC BY 4.0 | yes — for validators. **Not** a beginner syllabus |
| **ARASAAC** | CC BY-**NC**-SA | avoid — NC creates ambiguity for support models and future distribution |
| **Cambridge Pre-A1/A1 materials** | copyright retained | **no.** "Free download" is not a redistribution licence. Benchmark against; do not bundle |
| **Open Images** | per image | curate a small reviewed subset offline; never the runtime database |

This is the replacement path for the copyrighted textbook pages.

---

## 10. Repos to read (not to depend on)

**R/exams** (GPL-2/3) — how experts represent families of valid items.
**PaperClickers** (GPLv2) — attributable responses from a classroom with no
per-child devices. The research's strongest recommendation is to read these two
*before* cloning another AI tutor, because they address our two genuinely
unsolved problems.

Also worth reading, none as a dependency: Moodle GIFT grammar, H5P's interaction
taxonomy and validation approach, Numbas' variable-driven generation,
PrairieLearn's separation of generation from grading.

---

## 11. What this changes in the tree

| | Change |
|---|---|
| `teacher_os.OUTCOMES` | `correct/wrong/uncertain/near` → the two-axis model. **A wire-contract change** |
| `_name_skill_stats` | delete the confidence number; report counts, dates, coverage |
| `keys.md` (written today) | rewrite outcomes onto the two axes |
| `skills/scaffold-down` (written today) | one ladder → branch by failure type |
| `skills/invite-an-individual` | add the attribution budget and the deterministic fairness queue |
| `record_evidence` schema | subject + the metadata table above |
| Library format | add `:::item` / `:::family` blocks; Core instantiates families |
| `identity-is-perception` | amended — see §8 |

None of this is urgent before the demo. **All of it is cheaper now than after a
curriculum is authored against the old shape** — the same argument that applies
to giving `record_evidence` a subject.

---

## What the research confirmed without being asked

Reached independently, which is the strongest signal available that these were
right: no invented mastery score · no pronunciation percentages · the board holds
no grade · receptive ≠ productive · the model may not fill gaps in the curriculum
ontology · **and the markdown must never become a lesson script.**
