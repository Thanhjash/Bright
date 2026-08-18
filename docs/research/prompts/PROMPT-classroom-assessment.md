# Deep research prompt — practice, assessment and evidence for an autonomous classroom teacher

**Written:** 2026-08-18
**For:** an external deep-research run (GPT / Gemini deep research)
**Feeds:** [tool-surface.md](../../design/tool-surface.md) §"assessment left open", and a future decision on practice-item design
**Do not act on this document.** It is a question, not an answer. A finding
becomes doctrine only when a `decisions/` file adopts it.

---

## How to use this

Copy everything below the line into the deep-research tool. It is written to be
self-contained — the researcher has never seen this repository.

---

# RESEARCH BRIEF

You are advising the engineering lead of **Bright**, a donated, fully offline AI
English teacher for remote, under-resourced classrooms. Answer as a principal
engineer who also understands learning science: specific, evidence-backed,
willing to say "this is not established" and willing to tell us we are wrong.

## The system you are advising

An **autonomous teaching agent** — not a tutoring app, not a chatbot with an
avatar. An agent harness (currently Hermes) drives a small language model that
reads a markdown curriculum library the way a coding agent reads a repository,
and acts through a small set of typed tools. A separate service ("Classroom
Core") owns all I/O, the clock, the database, safety validation and restart. The
model never renders HTML, never touches a filesystem, and never chooses from a
menu of pre-authored moves.

**The room:**

- **One shared projected screen.** No device per child. No per-child keyboard.
- **20–40 children per class**, ages roughly 8–11, CEFR **Pre-A1 to A1**.
- Mother tongue Vietnamese, target language English — but both are declared
  configuration; the design must work for other language pairs.
- **One microphone in the room.** Speech recognition is `faster-whisper`-class,
  offline, and is unreliable on very short utterances and on child L2 speech.
- **A human adult is present but is NOT a co-teacher.** They boot the machine
  and handle the room. They must never make a teaching decision, and must never
  be required to operate an interface during the lesson.
- Fully **offline**. Cheap Intel hardware, 16 GB design target. A local ~4B
  model eventually (Gemma-class; scores ~42% on the Tau2 agentic tool-use
  benchmark, so it is *not* reliable at complex tool orchestration).
- The product is **given away** — target population on the order of 40 million
  children. Content must be authorable by teachers, in markdown, with no build
  step and no engineer.

**Hard constraints that cannot be negotiated away.** If your recommendation
violates one, say so explicitly and argue why it is worth it:

1. **The model may never invent a mastery score, a learner profile, or a
   personality label about a child.** Every claim about a learner must be
   traceable to a recorded, categorical observation with provenance.
2. **No raw transcripts as long-term memory.** Durable student memory is
   structured evidence rows only (`student_id`, `objective_id`, outcome, how it
   was elicited, when).
3. **No uncalibrated numeric scores shown to anyone** — in particular no
   pronunciation percentages without a validation study.
4. **Receptive and productive evidence are different things.** A child who
   *points* at the banana has not shown they can *say* "banana". Conflating
   these is treated as a measurement-validity failure, not a rounding error.
5. **Retrieval must scope to one learner before it ranks anything** — no
   semantic search across children.
6. **General first, optimised second.** English is the first subject; the design
   must not make a second subject (maths, geography) require new code.
7. Reflex interactions (a tap, a highlight) must never wait on the model.

## What we already decided, so you do not re-derive it

- Curriculum truth is markdown + `asset://` media. Retrieval is scoped file
  reads plus keyword search; dense/graph retrieval is deferred behind a measured
  gate.
- Student truth is SQL evidence rows. Bayesian Knowledge Tracing, Elo, deep
  knowledge tracing, and agent-memory frameworks (Mem0, Letta, Graphiti) are all
  rejected for now — BKT is a candidate only after pooled cohort data exists.
- The agent's tools are *verbs a teacher does*: read the library, write on the
  board, show an image, play a recorded clip, say one line, record evidence.

---

## THE QUESTIONS

### Part 1 — What "a practice item" should even be, on one shared screen

Most educational technology assumes one learner, one device, one input box.
**We have thirty children and one screen.** Nearly all of the item-design
literature and all of the tooling assumes otherwise.

1. What does the research and the practice of **whole-class formative
   assessment** say about eliciting evidence from many learners on a shared
   display — choral response, mini-whiteboards, hand signals, cold-calling,
   think-pair-share, exit tickets? Which of these translate to a system where
   the *teacher* is a machine with one microphone and one camera?
2. Which of those techniques produce evidence that is **attributable to an
   individual child** versus only to the class? How do skilled human teachers
   handle that trade-off, and what is lost?
3. Is there a defensible design in which **most** interactions are unattributed
   (class-level) and only a **few** are attributed (a named child answers)? What
   ratio do effective teachers actually use, and what does that imply for how
   often our agent should call on someone by name?
4. **Fairness / turn-taking:** what is known about equitable participation
   (avoiding the loudest child dominating), and how have automated systems
   attempted it? What actually works?

### Part 2 — Item types and their evidence value at Pre-A1/A1

5. For Pre-A1/A1 English with children, enumerate the practice/assessment item
   types worth supporting, and for **each** give: what it actually measures,
   whether it yields receptive or productive evidence, how well it works on a
   shared screen with no per-child input, and its known failure modes with young
   L2 learners.
   Cover at least: picture-matching, multiple choice, listen-and-point,
   listen-and-repeat, gap-fill/cloze, sentence building, ordering, matching
   pairs, spot-the-difference, TPR (total physical response), chants and songs,
   information-gap pair work, roleplay, and open production.
6. **Which of these are traps?** Specifically: which item types *look* like
   evidence of language ability but mostly measure something else (test-wiseness,
   memory of the picture set, guessing, the child copying a neighbour)?
7. What is the evidence on **guessing correction** for young learners on
   two- and three-option items? Is a 3-option item meaningfully better than a
   2-option one at this age?
8. How should **listening** items sequence audio, question, wait, and transcript
   reveal? Is there evidence about revealing the written form too early turning a
   listening task into a reading task?

### Part 3 — Authored items vs generated items

This is our sharpest open question.

9. What is the current evidence on **LLM-generated practice items** for language
   learning — quality, error rates, and the specific failure modes (wrong
   distractors, ambiguous keys, off-level vocabulary, cultural mismatch)?
10. Is there a defensible **middle design**: teacher-authored item *templates* or
    *item families* in markdown, from which the agent instantiates variants
    within tight constraints? What does the assessment literature say about item
    families / automatic item generation, and what validity evidence exists?
11. If items are generated at runtime by a **~4B local model with no internet and
    no human reviewer in the room**, what safeguards are actually effective?
    Where is the line past which generation should be refused?
12. Our curriculum is markdown authored by real teachers, deliberately with no
    build step. **What is the best markdown syntax for authoring interactive
    items?** Survey what exists — LiaScript, Markdown-based quiz DSLs, GIFT,
    Moodle XML, H5P, Anki formats, Jupyter-based approaches. Judge them on:
    authorability by a non-programmer, expressiveness, ease of machine
    validation, and whether an agent can read them as *instructions to teach*
    rather than as a script to execute. Give concrete syntax examples.

    **We have already read LiaScript, so do not simply re-describe it.** We know
    it offers `- [(X)]` single choice, `- [[X]] `multiple choice, `[[answer]]`
    typed cloze, `?[...]` open ungraded, survey vectors and matrices, `##` per
    slide, and `{{n}}` / `--{{n}}--` to split shown content from spoken content;
    licence is Boost 1.0. We also know it has **no** matching, ordering,
    drag-and-drop, flashcard or spaced-repetition item type, and that its runtime
    assumes one device per learner. What we need from you is: (a) does anything
    beat it for non-programmer authorability, (b) how would you extend it to the
    item types it lacks without losing that authorability, and (c) how should an
    *agent* read such a file — as an item bank it selects from, or as a lesson it
    performs?

### Part 4 — Judging a response without lying about it

13. A child speaks; ASR returns imperfect text. What are the defensible
    approaches to **judging** that against an answer key — exact, fuzzy,
    phonetic, constrained decoding against an expected answer set, LLM-as-judge?
    Give measured error characteristics where they exist, particularly for
    **children's L2 speech**, which is known to degrade general ASR badly.
14. What is the state of the art on **not over-claiming**: how should a system
    represent "the child probably said it but the microphone was poor"? What
    outcome vocabulary do real formative-assessment systems use, and is a
    `correct / near / wrong / uncertain` scheme defensible?
15. What **evidence metadata** is worth recording per observation so that later
    analysis is valid — prompted vs independent, first attempt vs repeat, novel
    vs familiar context, receptive vs productive, assessment vs practice? Is
    there an established ontology we should adopt rather than invent?
16. How wrong is it to give a *confidence* number over 3–8 observations, and what
    is the honest alternative? We currently compute something that reaches
    "certain" after four attempts and we believe that is indefensible.

### Part 5 — Pacing, spacing and what the agent should do next

17. What does the retrieval-practice and **spaced repetition** literature
    actually support for 8–11-year-olds in a *classroom* setting (not an app,
    not per-child scheduling)? Can spacing be done at class granularity, and is
    it worth it?
18. How should an agent decide **when to stop drilling** a word and move on, and
    when to come back to it — using only counts, recency and elicitation
    coverage, with no mastery model?
19. What is known about **error correction and recasting** with young L2
    learners — immediate vs delayed, explicit vs implicit? Our agent currently
    scaffolds English → simpler English → picture → example → mother tongue.
    Is that ladder supported by evidence, and is the ordering right?
20. Is there evidence about the **optimal length and rhythm** of a Pre-A1
    activity for this age — how long before attention is lost, how many
    exchanges per objective?

### Part 6 — Open-source we should read

21. Identify open-source projects worth cloning specifically for **item
    authoring, item banks, or classroom formative assessment** — not general
    tutoring chatbots. We have already surveyed `LiaScript/teaching-agent` (a
    prompt-spec framework, not a runtime) and `A-R007/Multi-Agent-Study-Assistant`
    (a cloud-dependent Streamlit demo with no grading code and no licence file);
    neither is a dependency candidate. Find better ones. For each: repo URL, licence, activity, what to steal, what
    not to merge, and whether it runs offline on CPU. We are specifically
    interested in LiaScript and any markdown-native course/quiz DSL.
22. Are there **open, freely-licensed item banks or picture-vocabulary corpora**
    at Pre-A1 for English, redistributable at zero cost as part of a donated
    appliance? Licensing must be checked properly — "free to use" is not enough.

---

## Output format

1. **Executive verdict** — the three decisions you would make in our position,
   stated as decisions, with the strongest counter-argument to each.
2. **Item-type table** — every type, what it measures, receptive/productive,
   shared-screen viability, failure modes, verdict for us.
3. **Authored vs generated** — a clear recommendation with the gate that would
   change it.
4. **Markdown authoring syntax** — a concrete proposal with examples, judged
   against the alternatives.
5. **Judging and evidence ontology** — what to record, what to refuse to claim.
6. **Repos and corpora** — table with licences.
7. **What you would tell us NOT to build**, and why. Be blunt here; we have
   already deleted one architecture that was wrong.

## Ground rules

- Distinguish **established findings** from **your engineering judgement**.
  Label the second as such.
- Cite sources. Where evidence is thin or contested, say so rather than
  smoothing it over.
- Where a claim comes from a vendor or a project's own documentation, say so.
- Prefer things that work offline, on CPU, at zero licence cost.
- Where you disagree with a constraint listed above, argue it directly. We would
  rather be corrected now than after authoring a curriculum.
