# Practice, Assessment, and Evidence for an Autonomous Whole-Class Teacher

**Research date:** August 18, 2026  
**Context:** Bright, an offline autonomous English teacher for 20–40 children, ages roughly 8–11, CEFR Pre-A1 to A1, one shared screen, one room microphone, no per-child device.

The core conclusion is uncomfortable but useful: **Bright should not try to reproduce a one-child-one-device tutoring system at classroom scale.** The classroom is a different measurement environment. Whole-class activity is excellent for teaching, rehearsal, engagement, and deciding what to do next, but most of it is intrinsically weak as durable evidence about an individual child. Formative-assessment guidance explicitly emphasizes gathering broad evidence from all pupils, simultaneous commitment, and using those signals to adapt teaching, rather than pretending every classroom interaction is an individually scored test. citeturn19view4turn17search0

The resulting architecture should therefore be asymmetric: **many cheap, unattributed teaching interactions, a small number of deliberately attributable probes, and an aggressive willingness to record `uncertain` rather than manufacture certainty.**

## Executive verdict

### Decision: make whole-class interaction abundant, but make individual evidence sparse and deliberate

**Decision.** Most Bright interactions should be class-level or pair-level and should **not** create student evidence rows. Individual evidence should come only from explicitly attributable probes, normally a named child answering after everyone has had thinking time, or later from a machine-readable physical response system whose identity mechanism has actually been validated.

This matches the strongest practical principle in whole-class formative assessment: ask questions that expose thinking across the room, obtain simultaneous commitment where possible, and use the pattern to determine the next instructional move. EEF specifically recommends all-pupil response systems such as mini-whiteboards, ABCD cards, and finger voting, with answers committed before simultaneous reveal to reduce copying and hesitation. citeturn19view4

Choral responding can dramatically increase the number of opportunities to respond, but it destroys individual attribution. The literature comparing choral with mixed responding is small and specialized. One elementary study explicitly used a **70% choral / 30% individual** mixed condition, but could not establish that either mixed or purely choral responding was superior. That 70/30 split is therefore **not an evidence-based optimum** and should not become Bright doctrine. citeturn17search2

Cold-calling research is more encouraging, although much of it comes from older students and higher education rather than 8–11-year-old L2 classrooms. Studies found that frequent cold calling could increase subsequent voluntary participation without reducing reported comfort, and another study found that high cold-calling conditions closed a gender participation gap seen under low cold-calling conditions. citeturn17search18turn17search5 An automated system has also been studied that poses the question first, gives everybody thinking time, and then randomly selects a respondent, a sequence much better than naming a child before the thinking begins. citeturn17search7

**Engineering judgment.** I would not encode a target "choral-to-individual ratio." I would instead encode an **attribution budget and a fairness queue**. A sensible starting configuration for a 40-minute lesson is roughly **8–12 named probes**, with the remaining dozens of opportunities being choral, simultaneous-sign, pair, TPR, or class discussion. In a 30-child class, 10 attributable probes per lesson gives every child approximately one named opportunity every three lessons if selection rotates evenly. In a 40-child class, 8–12 gives roughly one every three to five lessons. Those numbers are an operational starting point, not a finding from learning science.

Selection should be deterministic from auditable facts such as:

`least_recently_sampled(objective)`, number of attributable observations, whether the last attempt was `uncertain`, and whether productive evidence is missing.

It should **not** select based on an inferred "weak student," "shy learner," "low ability," personality, or mastery probability.

The strongest counter-argument is that this gives Bright much less individualized evidence than a tablet tutor. Correct. **That is reality, not a defect in the model.** One microphone and one shared display cannot honestly provide 30 simultaneous individual assessments. Sparse truthful evidence is preferable to dense fabricated evidence.

### Decision: teacher-authored item families, deterministic variants, no free-form runtime assessment generation

**Decision.** Bright should treat teacher-authored items and teacher-authored **item families** as curriculum truth. The agent may choose among them and Classroom Core may instantiate bounded variants deterministically. A runtime 4B model should not be allowed to invent an evidence-bearing question, key, distractors, scoring rule, or target phrase.

This is strongly aligned with the older automatic-item-generation literature. Traditional AIG is built around **item models**, essentially controlled templates in which assessment-relevant features are specified by domain experts and only sanctioned variables are manipulated. citeturn14search13 Modern reviews of LLM-based AIG show a rapidly expanding literature, but a heterogeneous one spanning different models, domains, evaluation methods, and definitions of item quality. A 2025 review identified 60 relevant LLM-AIG studies, which is evidence that the field is active, not evidence that unattended 4B generation has become assessment-safe. citeturn23search11

There is especially little justification for extrapolating results from large cloud models, university assessment, medical education, or human-reviewed pipelines to **unreviewed, local, quantized 4B generation for 8–11-year-old beginner L2 learners**. That particular proposition is not established.

**Engineering judgment.** The safe dividing line is simple:

> **If correctness cannot be derived mechanically from teacher-authored data, the generated activity must not create durable learner evidence.**

The strongest counter-argument is authoring cost. At your scale, manually writing every surface variation is expensive. The answer is not unconstrained generation. It is **factorization**: teachers author objectives, exemplars, slot sets, contrast sets, pictures, acceptable expressions, and family rules once, then deterministic code generates many valid permutations.

### Decision: speech judgment must contain a first-class `no_decision`

**Decision.** For closed spoken responses, use a small expected-answer set and child-speech-aware ASR if available, but **never force the recognizer's best hypothesis into correct/incorrect**. If the signal cannot support a decision, record no learner claim.

Children's L2 speech is exactly where ordinary ASR assumptions break. Michot and colleagues note that systems trained mostly on adult native read speech transfer poorly to young language learners, and that language-model components can actually "repair" learner errors that a language-teaching system needs to preserve. Their work used about 85 hours of spontaneous English from Swiss pupils in grades 4–6 specifically to address this problem. citeturn19view3turn20search1 The project's current ChaLL-300M model card reports, on its target data, WER around **0.30 ± 0.01**, CER around 0.16, and an error-preservation metric substantially short of perfection. Those are project-reported results on a specific population, not validation for Vietnamese children or a room microphone. citeturn20search15

A 30% word-error rate can still support useful longer-utterance transcription. It is catastrophic evidence for assuming that a one-word beginner response was wrong because the recognizer emitted a different one-word string.

The strongest counter-argument is that `uncertain` makes the product feel less intelligent. Good. **It should feel less intelligent when the evidence is weak.** The alternative is lying.

## Shared-screen practice and item types

### What transfers from skilled whole-class teaching

The useful whole-class techniques divide into three categories.

| Technique | What Bright actually learns | Individual attribution | Fit with one mic/camera | Recommendation |
|---|---|---:|---|---|
| **Choral response** | Whether the room can participate, approximate class fluency/rhythm, gross misunderstanding | No | Excellent for teaching; terrible for individual speech recognition | **Core practice. Never fan one choral answer into 30 student rows.** |
| **Mini-whiteboards** | Simultaneous constructed responses and misconception patterns | Human teacher: often yes. Machine: only if vision/identity is reliable | Good if physical boards exist; OCR at classroom distance is a separate validation problem | **Strong class assessment. Individual evidence only after validated capture.** |
| **ABCD cards / hand signals / finger voting** | Distribution of selected responses | Usually no without robust identity mapping | Very good for instant whole-class checks | **Core class-level check.** |
| **Printed coded response cards** | Individual selected response | Potentially yes | Strong technical fit if one camera can scan them | **Promising phase-two capability.** |
| **Cold/warm calling** | One child's attributable response | Yes | Excellent, provided one child speaks at a time | **Primary source of individual spoken evidence.** |
| **Think-pair-share** | Practice, explanation, interaction, then a sample of the room | Pair discussion itself generally no; sampled report yes | Good practice, poor room-mic transcription | **Core pedagogy, sampled evidence only.** |
| **Exit ticket** | Individual end-of-lesson response | Yes on paper, but machine capture is the problem | Poor baseline fit without scanning workflow | **Do not make it operationally required.** |

EEF's advice is particularly relevant to Bright: it recommends protected thinking time before selection, all-pupil response methods, and simultaneous commitment before revealing answers. citeturn19view4 That sequence maps almost perfectly onto an autonomous machine teacher:

**ask everyone → wait → everyone commits → inspect class signal → optionally sample one named child → respond instructionally.**

That is much better than chatbot-style:

**ask one child → wait while 29 children become audience members → score child → repeat.**

PaperClickers is worth studying because it solved a closely related infrastructure problem: one teacher-side Android device plus printed student cards, created specifically as a low-cost classroom response system by UNICAMP researchers. citeturn16search3 Its code is GPLv2. fileciteturn4file0L1-L2 This is a better conceptual precedent for Bright than conventional clicker systems requiring a connected handset for every learner.

**Engineering judgment:** should you implement visual attribution, use **explicit physical identifiers**, such as coded answer cards, rather than face recognition. Facial recognition would add privacy, demographic-bias, pose, occlusion, enrollment, and restart problems merely to infer an identifier that a printed code can state directly.

### The crucial evidence distinction

A skilled teacher often works from intentionally mixed-resolution evidence. They glance across whiteboards, hear the class, notice hesitation, then ask a few children to explain. EEF's whole-class checking guidance explicitly frames these signals as information for choosing the next teaching move, not as a requirement to produce a psychometric record for each student. citeturn19view4

Bright should preserve that distinction architecturally:

```text
class interaction
    -> may change what the agent teaches next
    -> does NOT create individual learner evidence

attributable individual probe
    -> may change what the agent teaches next
    -> MAY create an evidence row

unattributable / ambiguous response
    -> no individual evidence row
```

Never do this:

```text
class chants "banana"
    -> 30 rows saying productive banana = correct
```

That would simultaneously violate attribution, productive-evidence validity, and the reality of choral masking.

### Item-type table

CEFR distinguishes reception, production, interaction, and mediation rather than treating language competence as one undifferentiated skill. citeturn18search4turn18search8 Cambridge's current Pre-A1/A1 young-learner assessments likewise use materially different listening, reading/writing, and individual speaking tasks. At Pre-A1, for example, Cambridge uses listening to pictures, three-picture listening choice, following oral instructions, picture-supported word recognition, cloze-like missing words, and one-to-one speaking. citeturn19view0 At A1, it adds listening matching, dialogue completion, more extensive cloze, sentence completion, and fuller picture-based speaking. citeturn19view1

The table below is therefore deliberately strict about what each interaction can justify.

| Item type | What it actually measures | Evidence | Shared-screen viability | Principal failure modes | Verdict for Bright |
|---|---|---|---|---|---|
| **Picture matching** | Recognition of a spoken/written word or description against visual alternatives | Receptive | **Excellent** | Picture cue may dominate language; recurring art can be memorized; neighbor copying | **Core.** Rotate visual exemplars. Do not call it productive vocabulary. |
| **Picture naming** | Retrieval of a lexical item from a visual referent | Productive, controlled | **Good when named child responds** | ASR on one word; picture ambiguity; accepts memorized picture-label association | **Core individual probe**, with `uncertain` available. |
| **Multiple choice** | Recognition/discrimination among supplied alternatives | Usually receptive | **Excellent** | Guessing, test-wiseness, cueing, implausible distractors, following neighbors | **Core class check; weak as single-trial individual evidence.** |
| **Listen-and-point** | Comprehension of spoken language linked to an object/picture/location | Receptive listening | **Excellent** | Point may be hard to observe; neighbors; picture-set memory | **Core.** Never interpret as ability to say the target. |
| **Listen-and-repeat** | Ability to imitate a recently heard sequence, plus some perception/articulation | Productive but **imitative**, not independent retrieval | **Excellent for choral practice**, reasonable individually | Echoing without understanding; ASR expected-answer bias; group masking | **Practice core. Evidence must be tagged `imitative`; never substitute for independent production.** |
| **Gap-fill / cloze** | Depends on design: lexical retrieval, grammatical form, or reading comprehension under contextual constraint | Controlled productive or mixed | **Medium** without writing devices | Context and first-letter cues; copying; may test spelling more than target language | **Support**, but objective and modality must be explicit. |
| **Sentence building** | Controlled construction of a sentence | Productive if learner generates words; much less so if all words supplied | **Medium–high** | Word-bank cues make it recognition/order rather than genuine production | **Support.** Store whether response was supplied-choice or constructed. |
| **Ordering** | Recognition of grammatical/discourse sequence | Usually receptive/controlled | **High** | Can solve from mechanical patterns; supplied words remove lexical retrieval | **Good practice/check, weak productive evidence.** |
| **Matching pairs** | Association between two representations | Receptive | **High** | Process of elimination; matching by visual rather than linguistic cues | **Core practice; modest evidentiary value.** |
| **Spot-the-difference** | Listening, questioning, describing, comparison | Productive + interaction when genuinely spoken | **Good pair activity**, hard for one room mic | Partner does the work; memorized descriptions; overlapping speech | **Strong communicative practice, sample individual turns only.** |
| **TPR / physical commands** | Comprehension of oral commands | Receptive listening | **Excellent** | Following peers; action ambiguity; teacher overinterprets action as language production | **Core Pre-A1 practice/check.** Never productive evidence. |
| **Chants and songs** | Rehearsal, rhythm, phonological patterning, formulaic language participation | Primarily practice, not clean assessment | **Excellent** | Copying, masking, memorized sequence, no individual attribution | **Keep enthusiastically, but almost never record individual evidence.** |
| **Information-gap pair work** | Genuine information exchange, listening and spoken interaction | Productive + receptive + interaction | **Pedagogically excellent**, technically difficult | One child dominates; partner supplies language; room microphone overlap | **Core practice. Individually sample after or during controlled turns.** |
| **Roleplay** | Formulaic or semi-open communicative production and interaction | Productive + interaction | **Good for selected pairs** | Script memorization, peer prompting, scoring ambiguity | **Support.** Evidence only for identifiable turns and explicit objective features. |
| **Open production** | Independent lexical/syntactic/functional language production | Productive | **Medium** pedagogically, **hardest technically** | ASR errors, huge legitimate answer space, LLM-judge subjectivity | **Essential for language learning, but initially practice-heavy and evidence-light.** |

A recurring rule emerges: **the more communicatively authentic an item becomes, the more difficult its automatic scoring becomes.** That is not an argument against communicative activities. It is an argument against demanding that every good teaching activity also be an automatically scored measurement event.

### The traps

The most dangerous item types are not necessarily bad teaching activities. They are activities that tempt the system into claiming a stronger construct than was actually elicited.

**Listen-and-repeat is the biggest trap.** A child who immediately echoes "I like bananas" has shown something useful about auditory perception and imitation. They have not demonstrated that they can independently retrieve and formulate *I like bananas* tomorrow.

**Chants and songs are an even bigger attribution trap.** They are valuable group practice, but a strong chorus can completely conceal a silent or confused learner.

**Pointing and TPR are productive-evidence traps.** A correct action supports listening comprehension, not oral production. Your hard constraint here is exactly right.

**Ordering and supplied-word sentence building are production traps.** If `I / bananas / like` is already displayed, putting the pieces into order does not show independent lexical retrieval.

**Repeated picture sets are memory traps.** If banana always means the same yellow cartoon in the same location, Bright may end up measuring recognition of that artwork.

**Public sequential multiple choice is a copying trap.** EEF's recommendation that everybody commits before simultaneous reveal directly addresses this. citeturn19view4

### Two versus three options and "guessing correction"

There is **no good young-learner-specific evidence I found establishing a universally superior two-option or three-option format for Pre-A1 children**.

The arithmetic chance floor is obvious: 50% for two options, 33.3% for three. But item quality is not determined by that fraction. General multiple-choice research has repeatedly found that three alternatives often perform comparably to larger numbers of alternatives because item writers struggle to make additional distractors plausible. citeturn18search10 That literature does not prove that a three-option item is psychometrically "better" than a well-designed two-option discrimination for young L2 learners.

**Engineering judgment:** default to **three options when you have two genuinely plausible distractors**. Use two options for pedagogically meaningful contrasts such as `he/she`, singular/plural pictures, or two confusable sounds. Never manufacture a silly third distractor merely to lower chance probability.

Do **not** implement correction-for-guessing over three, five, or eight observations. A mathematical correction applied to tiny, heterogeneous classroom observations creates precision without validity. One selected-response trial should normally be one categorical observation, not a miniature ability estimate.

### Listening sequence

Cambridge Pre-A1 and A1 young-learner paper tests expose the visual task and then play recordings twice. citeturn19view0turn19view1 This is a useful precedent, but not a law that every Bright audio must always be played twice.

For Bright, I recommend:

```text
orient to task
    ↓
show response affordance / pictures
    ↓
do NOT show transcript or written target
    ↓
play audio
    ↓
protected wait
    ↓
commit response
    ↓
optional second play, according to item protocol
    ↓
commit/final response
    ↓
only now reveal transcript / spelling / explanation
```

**Established construct principle:** listening and reading are distinct modes of reception in the CEFR. citeturn18search8

**Engineering judgment:** therefore, if readable text containing the answer appears before the listening response, do not label the resulting observation `listening_only`. It has become reading-supported or multimodal evidence.

I found no credible experimental literature establishing that "the transcript must appear exactly N seconds after audio." Do not invent such a rule. The defensible rule is construct-based: **keep information that can independently reveal the answer hidden until the listening observation is complete.**

## Authored vs generated

### What the evidence supports

The automatic-item-generation literature gives you a much better middle path than either extreme:

1. hand-author every individual exercise forever, or
2. let an LLM write arbitrary questions at runtime.

Classical AIG uses expert-developed **item models or families**, with explicit manipulable elements. citeturn14search13 Modern LLM-AIG research broadens what can be generated, but reviews still show highly heterogeneous task domains, models, and evaluation procedures rather than a settled general-purpose generation technology. citeturn23search11

That is exactly where Bright should land.

### Recommended three-tier content model

**Tier A: authored items.** Every semantic fact is explicit:

```text
prompt
correct answer(s)
distractors, if any
objective
evidence mode
elicitation type
assets
```

These may create learner evidence if the response itself is trustworthy.

**Tier B: authored item families.** Teachers declare a constrained set of substitutions and the runtime instantiates them deterministically.

Example:

```text
pattern: "Point to the {fruit}."
fruit:
  - banana -> asset://fruit/banana.webp
  - apple  -> asset://fruit/apple.webp
  - mango  -> asset://fruit/mango.webp
```

The program, not the LLM, knows that `{fruit}` and its image are the key. The answer is a consequence of structured data.

**Tier C: model-created pedagogical language.** The model can give a transition, brief explanation, example, or perhaps practice variation within a closed vocabulary. Such material should initially be **non-evidence-bearing**. It should never define its own ground truth.

That division exploits the language model for what it is comparatively useful at, flexible discourse, while keeping measurement semantics outside it.

### Safeguards that are actually worth building

For a 4B offline model, the most effective safeguards are the ones that **reduce the model's authority**, not prompts asking it to be careful.

An evidence-bearing item should pass deterministic checks for schema validity, objective existence, asset existence, allowed vocabulary, permitted item type, answer cardinality, unique key, modality compatibility, and family version. A listening item cannot silently contain readable answer text. A productive objective cannot be satisfied by a point response.

Distractors for durable assessment should come from **authored contrast sets or deterministic domain rules**, not a request like "invent two plausible wrong answers."

For example:

```text
fruit:
  target: banana
  contrasts: [apple, mango, orange]
```

is safe.

```text
LLM: "Come up with three plausible fruit options"
```

is not equivalent.

The runtime must also have a completely ordinary failure path:

```text
family cannot be instantiated safely
    -> choose another authored family
```

not:

```text
family cannot be instantiated safely
    -> ask model to improvise
```

### Refusal boundary

I would forbid runtime generation from creating durable evidence whenever any of these is true:

The model must determine the correct answer; correctness depends on subtle world knowledge; the model invents distractors; the task contains unrestricted free production that requires semantic judging; the model introduces vocabulary outside an approved lexicon; the item depends on interpreting an image whose semantics are not already authored; the target is pronunciation quality; or multiple answers could reasonably be accepted but the authored data does not enumerate or parameterize them.

That prohibition is especially important because the small local model is also the teaching agent. Letting the same weak model **write the test, decide the key, hear the child imperfectly, and judge the answer** creates correlated failure across the entire evidence chain.

### The gate that would change my recommendation

**Engineering judgment, proposed validation gate:** free generation can move from "practice only" toward evidence-bearing use only after Bright validates the **exact deployed model, quantization, prompt, language pair, and item type**.

For critical defects such as wrong key, no valid answer, multiple defensible keys, target-language error, or construct mismatch, I would require a predeployment human audit large enough that zero or near-zero defect rates actually constrain the upper statistical bound, not a demonstration on 50 cherry-picked items. As an order of magnitude, zero critical defects in roughly 600 independently reviewed generated items corresponds to an approximate 95% upper bound around 0.5% under simple binomial assumptions. That is an **engineering risk threshold**, not an educational standard.

Even passing that gate would justify only the item types actually tested. Passing picture vocabulary MCQ generation does not validate generated roleplays, cloze, pronunciation tasks, or another L1/L2 pair.

My expectation is that you will get more value sooner by improving item-family expressiveness than by trying to pass this gate.

## Markdown authoring syntax

### First, one correction to the brief

Your LiaScript license note appears stale. **As of August 18, 2026, the current LiaScript repository declares BSD-3-Clause**, not Boost 1.0. citeturn14search3 Pin and verify the exact commit you redistribute, but I would update the research brief before that old license statement propagates.

### How the alternatives compare

| Format | Non-programmer authorability | Expressiveness | Machine validation | Fit for an autonomous teacher | Verdict |
|---|---:|---:|---:|---:|---|
| **LiaScript** | **Excellent** | Good for its existing quiz primitives | Medium | **High**, because content and quiz notation remain readable | Best starting design language, but extend semantics rather than adopt runtime assumptions. Current repo says BSD-3-Clause. citeturn14search3 |
| **Moodle GIFT** | **Good** for conventional quiz authors | Good for MCQ, T/F, short answer, matching, numerical, missing-word | **High** | Medium-low, format describes questions rather than teaching intent | Best conventional quiz DSL to steal ideas from. Moodle documents GIFT as a plain-text quiz format with a broad set of standard question types. citeturn6search0turn6search24 |
| **Moodle XML** | Poor by hand | Very high | **Very high** | Low | Good interchange format, awful teacher source of truth. Moodle itself is GPL-3.0. citeturn16search22 |
| **H5P** | Good through a GUI, poor as raw source | **Very high** | High within its library model | Low-medium | Excellent interaction reference, wrong storage/runtime architecture. H5P's question base and many official content types are MIT-licensed, but licensing is per library. citeturn15search7turn15search39 |
| **Anki text formats** | Excellent for cards | Very low for classroom assessment | High | Low | Useful inspiration for note/card separation, not a teaching DSL. Official Anki import formats are fundamentally field-oriented note/card data. citeturn6search2turn6search5 |
| **Jupyter / nbgrader** | Poor for ordinary teachers | Powerful for code/free response | High | Very low | Wrong audience and execution model. nbgrader is built around notebook assignments and grading workflows. citeturn6search3turn6search8 |
| **R/exams** | Medium for technical authors, poor for your target teacher | **Very high**, including parameterized exercises | High | Medium as inspiration, low as dependency | The best example here of Markdown plus item generation, but it requires R/Pandoc and therefore violates your no-build/no-engineer authoring goal. Current CRAN release 2.4-4 is dated July 31, 2026 and is GPL-2 \| GPL-3. citeturn16search16 fileciteturn3file0L1-L2 |

R/exams is especially worth reading because it explicitly generates assessments from Markdown/LaTeX exercises and supports multiple output ecosystems. citeturn16search16 But its power comes partly from executable R and an authoring toolchain. That is precisely what you should **not** require from a volunteer teacher writing Bright curriculum.

### What I would actually design

Do **not** invent a YAML-heavy miniature programming language. That would be clean for engineers and progressively miserable for teachers.

Keep ordinary Markdown as ordinary Markdown, and add one visibly bounded semantic construct:

```md
### Fruit review

We have learned banana, apple and mango.

:::item {#banana-point type=listen-point objective=vocab.banana}
Listen: asset://audio/point-banana.ogg

- [x] asset://img/banana-02.webp
- [ ] asset://img/apple-03.webp
- [ ] asset://img/mango-01.webp

Evidence: receptive
Use: whole-class, sampled
:::
```

A teacher can infer what that means without documentation.

`[x]` is **authorial truth**, not a control that appears already checked on the classroom screen.

For picture naming:

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

For matching:

```md
:::item {#animal-match type=match objective=vocab.animals}
Match:

- cat => asset://img/cat.webp
- dog => asset://img/dog.webp
- bird => asset://img/bird.webp

Evidence: receptive
:::
```

For ordering:

```md
:::item {#like-bananas type=order objective=grammar.like}
Put in order:

1. I
2. like
3. bananas

Evidence: controlled
:::
```

The runtime shuffles the displayed pieces. The source preserves the correct sequence in the most obvious form a teacher could write.

For a pair information gap:

```md
:::item {#fruit-gap type=info-gap objective=functions.asking-likes}
A sees:
- Mai likes bananas.
- Nam likes apples.

B sees:
- Linh likes mangoes.
- Hoa likes oranges.

Goal:
Find out what every child likes.

Useful language:
- What does {name} like?
- {name} likes {fruit}.

Evidence: interaction
Use: pair-practice
:::
```

For a bounded item family:

```md
:::family {#fruit-point type=listen-point objective=vocab.fruit}
Pattern:
Point to the {fruit}.

Values:
- fruit: banana | asset://img/banana.webp
- fruit: apple  | asset://img/apple.webp
- fruit: mango  | asset://img/mango.webp
- fruit: orange | asset://img/orange.webp

Choices: 3
Evidence: receptive
:::
```

The important part is architectural: **Classroom Core, not the model, instantiates that family**.

### Keep metadata semantic, not presentational

The minimum author-facing vocabulary should be close to what a teacher means:

```text
type
objective
evidence
elicitation
use
accept
asset
```

Do not expose:

```text
widget
component
layoutGrid
graderClass
eventHandler
toolCall
jsonSchema
```

Those are implementation details.

A richer internal normalized representation can exist after parsing, but the markdown should stay teacher-readable.

### How the agent should read the file

**Treat the file as curriculum guidance plus an item bank, not as a script to perform linearly.**

This distinction is fundamental.

Bad:

```text
slide 1
then item 1
then say sentence 3
then slide 2
then item 2
```

That makes Hermes a complicated PowerPoint player.

Better:

```md
## Objective
Children understand and can say four fruit words.

## Teaching notes
Introduce with pictures. Keep written forms hidden during the first
listening discrimination. Use pair practice before individual production.

## Practice items
:::item ...
:::

:::item ...
:::

## Check items
:::item ...
:::
```

The prose tells the agent **how to teach**. Item blocks tell it **which validated interactions are available**. Evidence tells it which probes can support which claims.

The agent selects among the bank according to the current objective, what forms of evidence are missing, time, prior item exposure, and class response. It should not be obliged to "execute the document."

That gives you autonomy without turning curriculum authors into prompt engineers.

## Judging, evidence, pacing, and correction

### Judging spoken answers

The candidate approaches are not equivalent.

| Method | Appropriate role | Main failure | Verdict |
|---|---|---|---|
| **Normalized exact match** | Closed text or highly constrained spoken answer after ASR | ASR mistake becomes learner mistake | **Accept only when recognition is sufficiently trustworthy.** |
| **Fuzzy edit distance** | Candidate retrieval / typo handling | In short answers, a one-character/one-word difference may be linguistically critical | **Never make it the final speech judge.** |
| **Phonetic matching** | Research/diagnostic aid around pronunciation variants | Can equate target and meaningful pronunciation error; language/accent dependent | **Do not use for durable correctness until separately validated.** |
| **Constrained decoding over expected answers** | Closed oral vocabulary/phrase tasks | Decoder can force poor audio into the nearest legal answer | **Best closed-response approach, but only with a no-decision path.** |
| **LLM judging ASR text** | Potential qualitative feedback on open practice | Cannot recover audio information lost by ASR; introduces another uncalibrated model | **Do not use for durable learner evidence.** |
| **Pronunciation score** | Potential future specialized subsystem | Requires child-L2 validation and interpretable construct | **Refuse today.** |

The key ASR paper for your problem does more than say children's speech is hard. It notes that ordinary ASR language modeling can **erase the very grammatical or lexical mistakes the teacher needs to observe**. citeturn19view3 That alone is enough to reject the idea that a fluent-looking transcript is ground truth.

For closed vocabulary items, constrained recognition is nevertheless useful because Bright often knows a small legitimate answer set:

```text
expected:
  banana
  apple
  mango
```

But the outcome must look like:

```text
audio
  -> recognizer
  -> evidence supports one candidate?
       yes -> compare candidate to authored answer
       no  -> no_decision
```

not:

```text
audio
  -> force nearest of banana/apple/mango
  -> compare
```

The latter is a classifier masquerading as transcription.

### Do not store `near` as a mysterious scalar category

`correct / near / wrong / uncertain` is understandable to humans, but I would **not** use it as the canonical evidence model.

`near` combines too many different things:

- learner produced an acceptable variant;
- learner omitted a function word;
- pronunciation was questionable;
- ASR was uncertain;
- response partly met the objective;
- learner self-corrected.

Those have different pedagogical meanings.

I recommend two axes:

```text
decision:
  supported
  contradicted
  no_decision

response_relation:
  exact
  accepted_variant
  partial
  other
```

plus a reason:

```text
reason:
  asr_ambiguous
  audio_noise
  multiple_speakers
  incomplete_target
  wrong_lexeme
  target_form_error
  no_response
  ...
```

Then:

```text
supported + exact
```

is ordinary correct evidence.

```text
supported + accepted_variant
```

means the key explicitly permits the variant.

```text
contradicted + partial
```

means a real, attributable response fell short in a defined way.

```text
no_decision + other + asr_ambiguous
```

means exactly what you need for "the child may have said it, but the microphone was poor."

**Uncertainty belongs to the measurement process, not to the child.**

That distinction is important enough to put into the data model.

### Evidence metadata worth keeping

There is no single established educational ontology I found that already combines CEFR language mode, response attribution, scaffolding, item-family provenance, and ASR decision provenance. CEFR gives you a principled vocabulary for reception, production, interaction, and mediation, which you should reuse rather than inventing competing language-mode labels. citeturn18search4turn18search8

I would record approximately this:

| Field | Why it matters |
|---|---|
| `student_id` | Attribution |
| `objective_id` | What claim the observation bears on |
| `observed_at` | Recency and spacing |
| `item_id` | Exact elicitation provenance |
| `item_family_id` + `family_version` | Detect repeated/variant contexts |
| `language_mode` | `reception`, `production`, `interaction` |
| `channel` | `listening`, `speaking`, `reading`, `writing`, physical response |
| `elicitation` | `independent`, `prompted`, `imitative`, `choral`, `peer_supported` |
| `attribution` | `individual`, `pair`, `class` |
| `response_constraint` | `selected`, `closed_constructed`, `open_constructed` |
| `purpose` | `practice`, `check`, `assessment` |
| `attempt` | First attempt versus repeat |
| `repair` | None, self-repair, prompted repair |
| `context_exposure` | Familiar item, family variant, novel exemplar |
| `scaffold_used` | None, repeat, gesture/picture, simpler language, model, L1, etc. |
| `decision` | `supported`, `contradicted`, `no_decision` |
| `response_relation` | `exact`, `accepted_variant`, `partial`, `other` |
| `reason_code` | Why that decision was made |
| `judge_rule_version` | Reproducibility |
| `asr_model_version` | Measurement provenance for speech |
| `decode_mode` | Open versus constrained |
| `expected_set_id/hash` | What recognition/scoring was constrained against |
| `audio_quality_flags` | Categorical clipping/noise/overlap/VAD problems |

I would **not** store a raw transcript as durable memory, which agrees with your constraint. I would also avoid retaining raw child audio by default unless there is a separately justified consent, safeguarding, retention, and research protocol. That is not necessary to make Bright's teaching loop work.

### Four observations cannot make someone "certain"

Your suspicion is correct.

A system that reaches **"certain" after four attempts** is indefensible unless "certain" is explicitly defined as nothing more than "our deterministic coverage rule has four qualifying observations." It cannot honestly mean a calibrated probability that the child has mastered the objective.

Four attempts can all share the same picture, day, prompt, response mode, peer cue, and scoring bias. More observations do not cure construct dependence.

Your constraints already point toward the better answer: report the evidence itself.

Instead of:

```text
banana mastery: 94%
confidence: certain
```

store or derive:

```text
productive / independent
  supported: 3
  contradicted: 0
  no_decision: 1

dates observed: 2
item families: 2
novel exemplars: 1
last observed: 2026-08-17

receptive evidence:
  supported on 3 attributable checks
```

That tells a later analyst vastly more and pretends vastly less.

A UI or scheduling component can use a categorical **coverage status** such as:

```text
productive evidence missing
needs another date
only prompted evidence present
novel-context observation missing
```

Those describe the dataset. They do not claim a latent ability.

### Spacing and retrieval should be class-level first

The classroom evidence for spacing is now strong enough that I would implement it, but not as a per-child SuperMemo clone.

A 2025 classroom-learning meta-analysis screened more than 3,000 articles and retained 22 reports with 31 effect sizes and over 3,000 participants. It found a moderate overall advantage for distributed over massed practice, reported as **d = 0.54, 95% CI [0.31, 0.77]**. citeturn22search0turn22search8 A 2025 study also reports retrieval-practice benefits in real primary-school settings. citeturn22search5 At the same time, primary-school vocabulary findings have not been uniformly positive across every spacing and retrieval manipulation, so there is no justification for pretending one magic interval schedule has been established for Bright's exact context. citeturn22search1

**Engineering judgment:** schedule **objectives at class granularity**.

Keep:

```text
objective_id
introduced_at
last_class_practice_at
class_practice_count
last_individual_probe_at
```

Then ensure that material returns after genuine intervening material rather than being exhausted in one massed block.

You do not need:

```text
SM-2 ease factor per child
BKT mastery probability
individual flashcard queues
```

to get the major benefit of spacing.

A good primitive is simply:

```text
due objectives =
    things introduced previously
    AND not practiced recently
    AND still lacking desired elicitation coverage
```

with curriculum constraints deciding how many can return in today's lesson.

### When to stop drilling

There is no established research result of the form:

> "A Pre-A1 child should answer a vocabulary item correctly exactly three times, then the teacher should advance."

Do not encode one.

**Engineering judgment:** use a **dose-and-switch rule**, not a mastery rule.

Within one activity:

```text
successful retrieval
    -> vary exemplar or response mode
    -> do not immediately ask the same thing five more times

repeated failure
    -> after roughly two attempts with the same representation,
       change the scaffold or representation
    -> do not grind
```

Within the lesson, give the objective several opportunities distributed through different activities. Across lessons, bring it back on a later day. An objective with only receptive evidence should continue to receive productive opportunities if production is an intended objective. An objective with only imitation should eventually receive independent retrieval.

The agent's question should be:

> "What useful type of elicitation has this objective not yet had?"

not:

> "Has the child crossed 0.85 mastery?"

That is a much healthier scheduler under your current evidence constraints.

### Error correction: do not use one universal ladder

Oral corrective-feedback research supports corrective feedback generally, but does not establish one universally superior technique or timing across all tasks and learners. Lyster and colleagues' major review distinguishes multiple corrective-feedback types and documents substantial contextual variation. citeturn22search14 Research comparing immediate and delayed feedback also depends on target, task, and learning context rather than yielding a simple universal winner. citeturn22search2

Your existing fixed ladder:

```text
English
→ simpler English
→ picture
→ example
→ mother tongue
```

is therefore **not evidence-based as a universal ordering**.

I would branch by failure type.

For a **meaning/comprehension failure**:

```text
repeat once
→ gesture / picture / physical demonstration
→ simpler English
→ concrete example
→ brief L1 gloss if still blocked
```

At Pre-A1, a picture can convey *banana* more efficiently than replacing incomprehensible English with different incomprehensible English.

For a **lexical retrieval failure**:

```text
wait
→ semantic/picture cue
→ partial form cue if appropriate
→ model the answer
→ choral/individual imitation
→ return later for independent retrieval
```

For a **production/form error**:

```text
brief model/recast
→ opportunity for self-repair
→ explicit cue if target form matters
→ continue communication
```

For a **communicative roleplay**, correction should generally be lighter and less disruptive than during tightly controlled form practice. That is pedagogical judgment consistent with the corrective-feedback literature, not a universal experimentally established sequence. citeturn22search14

Most importantly, **a modeled correction followed by successful repetition is not independent evidence**. Store the scaffold.

### Activity length and rhythm

There is no credible universal "attention span equals age plus N minutes" rule that I would put into Bright. Young-learner guidance emphasizes variety, routines, and active participation, but that is different from a validated optimal duration for a Pre-A1 activity. citeturn22search7

**Engineering judgment:** start with an activity budget around **4–7 minutes** for a single interaction pattern, with much shorter repetitive drill runs inside it, then change the participation mode:

```text
model / demonstrate
→ whole-class attempt
→ short peer or physical practice
→ whole-class check
→ named probe
→ feedback
→ transition or variation
```

The 4–7-minute figure is a product default to test, **not doctrine**.

Instrument the actual classrooms. Measure participation, response latency, abandonment, ASR collisions, teacher-agent restarts, and error patterns. You have a product-specific empirical question that generic "attention span" lore will not answer for you.

## Repos and corpora

### Open-source projects worth cloning

The best repositories are mostly useful as **sources of design patterns**, not dependencies.

| Project / repo | License and activity | What to steal | What not to merge | Offline CPU fit |
|---|---|---|---|---|
| **LiaScript** `https://github.com/LiaScript/LiaScript` | Current repo declares **BSD-3-Clause** and is actively maintained. citeturn14search3 | Human-readable Markdown extensions, course-as-text philosophy, separation of display/narration concepts | One-device-per-learner runtime assumptions; don't turn Bright curriculum into LiaScript execution | **Yes** |
| **R/exams** `https://github.com/cran/exams` | **GPL-2 \| GPL-3**; CRAN 2.4-4 published July 31, 2026. citeturn16search16 fileciteturn3file0L1-L2 | Parameterized item families, metadata, deterministic generation, interchange thinking | R execution, Pandoc/build pipeline, technical authoring requirements | **Yes**, but wrong authoring dependency |
| **Moodle** `https://github.com/moodle/moodle` | **GPL-3.0 or later**, mature and active. citeturn16search18turn16search22 | GIFT grammar, question-bank semantics, answer representation, matching/cloze ideas | The Moodle runtime, database model, UI, LMS assumptions | **Technically yes**, but far too large |
| **H5P** `https://github.com/h5p` | Many core/content libraries are MIT, but check each library individually; official repositories remain active in 2026. citeturn15search7turn15search39 | Interaction taxonomy, semantics/validation approach, accessibility lessons | H5P package/runtime graph and browser-centric authoring architecture | **Yes**, but not attractive as Bright dependency |
| **PrairieLearn** `https://github.com/PrairieLearn/PrairieLearn` | Community Edition primarily **AGPL-3.0**, with licensing distinctions for other portions. citeturn16search13 | Typed/randomized question design, separation of question generation and grading, validation discipline | Python/HTML/JS question code, server stack, higher-ed assumptions | **Possible**, but massive overkill |
| **Numbas** `https://github.com/numbas/Numbas` | **Apache-2.0**. Browser-based open assessment system. citeturn15search2 | Variable-driven question generation, answer-checking design, browser-offline thinking | Mathematics-centric expression engine and full runtime | **Yes** |
| **PaperClickers** `https://github.com/learningtitans/paperclickers` | **GPLv2**, clearly a legacy Android codebase. citeturn16search3 fileciteturn4file0L1-L2 | **Most relevant unique idea:** individual responses using printed coded cards plus one capture device | Old Android implementation, fixed quiz workflow | **Yes**, conceptually excellent |

My strongest recommendation from that table is surprising: **clone R/exams and PaperClickers before cloning another AI tutor.**

R/exams shows how experts represent families of valid items. PaperClickers shows how to get attributable responses from a classroom without buying 30 computers. Those are your actual unsolved problems.

### Corpora and assets

I did **not** find a turnkey, freely licensed, well-curated **Pre-A1 children's English item bank** that I would recommend bundling as Bright's curriculum truth. There are useful components, but you should expect to build the pedagogical item bank yourselves.

| Resource | License | Redistributable in appliance? | Useful for | Caveat |
|---|---|---:|---|---|
| **Mulberry Symbols** | **CC BY-SA 4.0**. Official site explicitly permits commercial or noncommercial project/product use with attribution and share-alike obligations for derived symbols. citeturn21search3 | **Yes**, with compliance | Concrete pictograms, actions, classroom language | AAC pictograms, not a Pre-A1 curriculum and sometimes visually abstract |
| **OpenMoji** | Graphics **CC BY-SA 4.0**, code LGPL-3.0. citeturn21search5 | **Yes**, with attribution/SA | Common objects, emotions, simple semantic contrasts | Emoji aesthetics and coverage are not pedagogically sufficient alone |
| **Wikimedia Commons** | Per-file free licenses; Commons permits only free media but individual attribution/license terms still matter. citeturn23search1turn23search5 | **Yes**, item by item | Real-world photographs and illustrations | You need a machine-readable attribution manifest and content curation |
| **Open Images** | Dataset annotations CC BY 4.0; project material Apache-2.0; released images use Creative Commons attribution licensing in the published dataset. citeturn21search2turn21search14 | **Potentially**, after per-image compliance checks | Large pool of real-world object images | Vastly overbroad, adult/uncontrolled content, attribution and curation burden |
| **Open English WordNet** | **CC BY 4.0**. citeturn23search0turn23search20 | **Yes** | Lexical relations, synonym/hypernym validator support, tooling | Not CEFR-leveled, not child-curated, not pictures, not an item bank |
| **ARASAAC** | **CC BY-NC-SA**, official terms prohibit commercial use. citeturn21search4 | **Possibly for a strictly noncommercial donation model**, but get legal confirmation | Excellent pictogram vocabulary | NC restriction creates unnecessary ambiguity for contractors, support models, or future distribution |
| **Cambridge Pre-A1/A1 materials** | Cambridge provides useful wordlists/sample material, but these are **not an open-content corpus**; Cambridge expressly retains copyright over exam materials and requires permission for reproduction. citeturn18search13turn23search10 | **Do not bundle without permission** | Benchmarking your coverage and task design | "Free download" is not a redistribution license |

For your use case, the cleanest asset strategy is likely:

```text
teacher-authored Bright vocabulary/objective inventory
+
Mulberry/OpenMoji for a baseline symbolic layer
+
carefully curated freely licensed photographs from Commons
+
an attribution manifest generated and shipped with the appliance
```

I would not make Open Images the runtime asset database. Curate a small, reviewed subset offline and ship that subset.

Also, **do not confuse Open English WordNet with a beginner vocabulary syllabus**. Its license is excellent and its lexical graph can help validators, but curriculum level is a pedagogical property you must author separately. citeturn23search0

## What I would tell you not to build

**Do not build synthetic individual evidence from whole-class behavior.** A chorus is not 30 correct responses. A hand vote whose owner cannot be identified is not a child observation. A pair answer is not automatically two observations. This is the most important measurement boundary in the entire design.

**Do not build facial recognition to solve classroom attribution.** The problem is much more cheaply and transparently solved by calling a child's name, using a seating/turn-taking scheme, or eventually scanning an explicit printed code. PaperClickers demonstrates that the last approach is technically plausible without per-child electronics. citeturn16search3

**Do not build a "mastery confidence" system that becomes certain after four attempts.** Delete it. Replace it with counts, dates, contexts, modality, scaffolding, and coverage. Your own constraint against invented mastery scores is correct.

**Do not build unreviewed runtime LLM assessment generation into version one.** Your 4B agent already has a hard orchestration problem. Asking the same model to invent psychometrically valid items gives it a second high-consequence job for which the evidence is substantially weaker. Current LLM-AIG research is active but heterogeneous, while conventional AIG already gives you the safer item-family abstraction. citeturn23search11turn14search13

**Do not build LLM-as-judge for durable spoken evidence.** Once ASR has mistranscribed child L2 speech, a language model looking only at the text has no acoustic information with which to repair the measurement. The child-ASR literature specifically warns that ordinary language models can normalize learner errors rather than preserve them. citeturn19view3

**Do not build pronunciation percentages.** Not "87% pronunciation," not "92% fluency," not a green progress ring. Until the exact scoring method has been validated against expert ratings on children of the relevant ages, L1s, microphones, tasks, and noise conditions, the number has no defensible interpretation.

**Do not build one universal scaffold ladder.** Meaning failure, task-instruction failure, lexical retrieval failure, pronunciation failure, and grammatical production failure require different teaching moves. Oral corrective-feedback research does not support pretending there is one universally optimal sequence. citeturn22search14

**Do not build an individualized spaced-repetition engine yet.** Implement spacing, absolutely. But schedule curriculum objectives at class granularity and use attributable evidence to choose additional probes. Classroom research supports distributed practice, including a moderate pooled advantage over massed practice, without requiring a per-child flashcard scheduler. citeturn22search0turn22search5

**Do not adopt Moodle, H5P, PrairieLearn, Numbas, or R/exams as Bright's runtime architecture.** They solve different deployment problems. Read their item representations, validators, randomization logic, and edge cases. Steal the concepts. Your runtime needs to remain vastly smaller.

**Do not make the markdown a lesson script.** This is particularly important. The system you described is an autonomous teacher because it can interpret curriculum goals, inspect evidence, choose an appropriate teaching action, and adapt. If authors must specify every screen and every next move, you have rebuilt slideware with an LLM in the loop.

**Do not let the model fill gaps in the curriculum ontology.** Unknown objective, unknown answer set, missing image, undefined response mode, ambiguous family, or missing scoring rule should be ordinary validation failures. The agent should choose another valid move. It should never "use its best judgment" to manufacture curriculum truth.

And finally, **do not optimize away uncertainty.** In this environment, with one microphone, children's L2 speech, 20–40 bodies, a small model, and no human co-teacher, uncertainty is not an edge case. It is one of the system's normal inputs.

The architecture should make the honest path the easy path:

```text
many children practise
        ↓
class-level signals guide teaching
        ↓
a few attributable probes produce evidence
        ↓
evidence says exactly how it was elicited
        ↓
poor measurement becomes no_decision
        ↓
counts + recency + modality coverage guide revisiting
        ↓
no invented mastery, no invented confidence
```

That design is less magical than an autonomous tutor that claims to know every child after every utterance. It is also substantially more defensible, more general across subjects, easier to audit, safer on weak local models, and much closer to what the evidence says a real classroom can support.