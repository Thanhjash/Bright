# Research verdict

There are two separate conclusions here.

**ASR:** do **not** replace `faster-whisper small` yet. But also do **not** accept “one language per utterance” as an architectural fact. Whisper's language token is conditioning, not a hard vocabulary gate. Vietnamese-English mixed transcription is possible in one pass, and 2026 mixed-speech results prove it. The strongest practical challenger for Bright is **PhoWhisper**, because you can keep essentially the same CTranslate2/faster-whisper serving stack. **Parakeet CTC 0.6B VI-EN** is the more interesting purpose-built challenger, but NVIDIA has not supplied the evidence Bright needs, especially Intel CPU results and child code-switch accuracy. ([arXiv][1])

**TTS:** keep **VieNeu-TTS v3 Turbo** as the leading candidate, but downgrade its status from “recommended” to **“must pass Bright acceptance testing.”** I found evidence that its text front end and model are designed for VI-EN code-switching, but not independent evidence demonstrating that an intra-sentence VI↔EN switch preserves perceived speaker identity, accent and prosody. For Bright's authored curriculum, an even better answer exists: **pre-render accepted mixed-language utterances during content build, rather than solving them live every lesson.** ([Hugging Face][2])

---

## 1. First correction: Whisper is not monolingual “by construction”

This statement in the brief should change:

> “Whisper emits one language token per utterance ... so a mid-sentence switch cannot be transcribed correctly by construction.”

That's not what the language token does. It conditions decoding toward a language, but multilingual Whisper retains a shared multilingual token vocabulary. It can therefore emit English words after Vietnamese words.

The strongest empirical proof is the March 2026 TSPC Vietnamese-English code-switch study. On its 1.18-hour mixed VI-EN evaluation set:

| Model                   | Mixed VI-EN WER |
| ----------------------- | --------------: |
| **TSPC SSL + joint FT** |      **19.06%** |
| **PhoWhisper-base**     |      **27.90%** |
| Whisper-large-v3-turbo  |          31.60% |
| wav2vec2-vn-base        |          38.06% |
| Qwen3-ASR-0.6B          |          38.93% |
| Whisper-base            |          59.45% |

These are actual code-switched utterances, not monolingual Vietnamese benchmarks. ([arXiv][1])

There is an important catch. The TSPC corpus is **not representative of Bright children**. Training contains 7.32 hours of CS speech, partly synthetic, and the evaluation subset is only 1.18 hours. The paper itself notes limited coverage and synthetic-data generalization as limitations. ([arXiv][1])

So the correct doctrine is:

> **Whisper supports mixed-language output, but utterance-level language conditioning can bias decoding and its VI↔EN code-switch accuracy is not established for Bright.**

If Bright's HTTP wrapper additionally restricts output/token selection after detecting `vi` or `en`, that restriction should be investigated separately. It is not intrinsic to Whisper.

---

# 2. ASR ranked table

I would rank deployment candidates like this.

| Rank                       | Candidate                                     | Actual mixed VI-EN evidence                                                                                                                                                                                                                              | Child evidence       | Intel CPU / RAM                                                                                                                                                                                                         | Licence                                                                                                                   | Bright integration                                                                          |
| -------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **0, production baseline** | **faster-whisper `small` INT8**               | No Bright-like CS benchmark. Whisper family demonstrably can CS, but smaller models degrade substantially on published CS sets. ([arXiv][1])                                                                                                             | None matching target | CTranslate2 measured `small` INT8 at ~1.477 GB RAM on i7-12700K. 13 min audio processed in 102 s, RTF ≈0.13, but **not a valid 1–4 s latency measurement and not low-cost Intel**. ([GitHub][3])                        | MIT                                                                                                                       | **Already done**                                                                            |
| **1 challenger**           | **PhoWhisper-small / base**                   | PhoWhisper-base **27.90% mixed WER** in TSPC. On ViMedCSS, zero-shot PhoWhisper helps Vietnamese overall but remains poor on English insertions; fine-tuning greatly improves seen CS vocabulary but hard/unseen English remains difficult. ([arXiv][1]) | None matching Bright | No published qualifying Intel 1–4 s INT8 benchmark. Same Whisper architecture/runtime class after CT2 conversion, so similar resource class is a reasonable expectation, **not a measurement**.                         | BSD-3-Clause. ([GitHub][4])                                                                                               | **Low**. CTranslate2 can convert Whisper-compatible Transformers checkpoints. ([GitHub][3]) |
| **2 challenger**           | **NVIDIA Parakeet-CTC-0.6B Unified VI-EN CS** | Built explicitly for VI-English CS, but NVIDIA's published card gives Vietnamese benchmark numbers, **not a mixed VI-EN WER comparable to TSPC/ViMedCSS**. ([Hugging Face][5])                                                                           | None                 | **No qualifying Intel result.** NVIDIA documents/test hardware around NVIDIA GPU architectures. 600M params gives an INT8 weight floor around 0.6 GB, actual RSS will be higher and is unpublished. ([Hugging Face][5]) | NVIDIA Open Model License, redistribution/commercial use possible with notice/terms, legal review required. ([NVIDIA][6]) | **High**. New NeMo/ONNX/runtime adapter behind Bright HTTP contract                         |
| **3**                      | **Qwen3-ASR-0.6B**                            | **38.93% WER** on TSPC CS set, worse there than PhoWhisper-base and Whisper-large-v3-turbo. ([arXiv][1])                                                                                                                                                 | None                 | Official work focuses mostly on accelerated/GPU paths; no qualifying Bright-like Intel INT8 1–4 s result found.                                                                                                         | Apache-2.0. ([Hugging Face][7])                                                                                           | Medium/high, new runtime                                                                    |
| **Research ceiling**       | **TSPC**                                      | **19.06%**, best directly relevant public number I found. ([arXiv][1])                                                                                                                                                                                   | None                 | Authors describe low-resource design, but training/deployment is PyTorch and reported training used RTX 3090. No appliance CPU benchmark. ([arXiv][1])                                                                  | Paper is CC BY; I did **not** establish a separately redistributable production checkpoint/runtime licence                | High / research implementation                                                              |

### Parakeet's English limitation is real

The earlier survey got this right.

NVIDIA describes the checkpoint as unified Vietnamese-English code-switching, but an NVIDIA response explicitly cautions that it is primarily Vietnamese-focused and handles **some common English words inside Vietnamese**, rather than functioning as unrestricted English ASR. ([Hugging Face][8])

That happens to align quite closely with one Bright use case:

> “Con muốn nói **hello**.”

But it does **not** establish performance for:

> “I think this is a banana, nhưng con không chắc.”

Nor does it establish child L2 pronunciation robustness.

So Parakeet deserves a bake-off, not adoption.

---

## 3. PhoWhisper is more interesting than it first looks

PhoWhisper was trained as a Vietnamese ASR model on roughly 844 hours of Vietnamese speech, rather than specifically as a child bilingual model. ([GitHub][9])

Yet we now have two pieces of directly relevant evidence.

TSPC's mixed test gives **27.90% WER for PhoWhisper-base**, beating Whisper-large-v3-turbo's 31.60% on that particular set. ([arXiv][1])

ViMedCSS provides another real VI↔EN test domain. It contains Vietnamese sentences containing English medical terminology, with 34.6 hours and 16,576 utterances. Zero-shot results show an instructive failure mode: PhoWhisper can improve Vietnamese transcription without necessarily improving the switched English pieces. Fine-tuning PhoWhisper-small with code-switch guidance gets roughly **23.67% WER / 19.50% CS-WER** on the regular test set, but on a deliberately hard set its **CS-WER rises to 57.29%**. ([arXiv][10])

That is highly relevant to Bright.

It says:

**memorized/familiar English islands are tractable; unseen English vocabulary and pronunciation remain a serious problem.**

Bright has an unusual advantage, though. Its curriculum vocabulary is partially known beforehand. Unlike open-domain dictation, we often know that today's plausible English targets are `banana`, `market`, `hello`, `yellow`, etc.

That is exploitable without turning the teacher into a scripted lesson engine.

---

# 4. My ASR recommendation

### Do not replace `faster-whisper small` now.

Instead run this hierarchy:

**Production today**

`faster-whisper small INT8`

**Bake-off A**

`PhoWhisper-small -> CTranslate2 -> existing HTTP service`

**Bake-off B**

`Parakeet CTC 0.6B -> new adapter -> same HTTP contract`

**Research comparator**

Qwen3-ASR and, if reproducible/licensable, TSPC.

PhoWhisper should be tested first simply because the engineering risk is tiny compared with Parakeet. CTranslate2 explicitly supports converting compatible Hugging Face Whisper models, so Bright doesn't need to redesign Classroom Core merely to evaluate it. ([GitHub][3])

I would also benchmark four Whisper decoding conditions using the **same audio**:

`auto`, forced `vi`, forced `en`, and your current deployment-language policy.

That will tell you how much of the current problem is actually the acoustic model versus Bright's language decision.

Do not permanently run two complete ASR decodes per child utterance unless testing shows you need it. That is a brute-force workaround which trades an accuracy problem for latency.

---

# 5. Children: the benchmark we need does not exist

I could not find a public corpus matching all of these simultaneously:

**Vietnamese L1 + English L2 + ages 8–14 + intra-utterance VI↔EN switching + spontaneous speech + ordinary classroom reverberation/noise + 20–40 children.**

There are useful fragments of evidence, but they do not close the gap.

TLT-school contains school-age learners around 9–16 speaking non-native English/German and is useful evidence that child L2 ASR materially differs from ordinary adult speech, but these are European learners rather than Vietnamese children. ([ACL Anthology][11])

Vietnamese child-speech work exists too. The VLSP Vietnamese mispronunciation effort includes young Vietnamese children, around ages 5–7, but it is the wrong age range, largely Vietnamese rather than VI↔EN mixed speech, and a different task. ([VLSP][12])

So for the actual product question, **Bright has to collect its own acceptance corpus.**

And I would not train on it initially. First use it purely as a locked evaluation corpus.

---

# 6. Smallest corpus I would trust

I would consider **36 children sufficient for engineering exploration, but not sufficient for a shipping decision**.

My minimum responsible go/no-go corpus is:

### 72 children, 5,760 utterances

| Dimension           | Requirement                                                                                  |
| ------------------- | -------------------------------------------------------------------------------------------- |
| Children            | **72**, ages 8–14                                                                            |
| Regions             | North, Central, South                                                                        |
| Real rooms          | **6 classrooms**, two per region                                                             |
| Children/class      | 12 target speakers/classroom                                                                 |
| Evaluation split    | 36 development/calibration, **36 fully locked**, child-disjoint and preferably room-disjoint |
| Utterances/child    | **80**                                                                                       |
| Total               | **5,760 utterances**                                                                         |
| Duration            | roughly 4 hours of target child speech if average utterance ≈2.5 s                           |
| Classroom condition | Actual 20–40-child classroom occupancy/background, not only synthetic noise                  |

The 80 utterances per child should be exactly:

| Type                                                       | Per child |
| ---------------------------------------------------------- | --------: |
| Vietnamese only                                            |        12 |
| L2 English only                                            |        12 |
| VI→EN, exactly one switch                                  |        16 |
| EN→VI, exactly one switch                                  |        16 |
| Two or more switches                                       |         8 |
| Spontaneous teacher-question responses                     |         8 |
| Difficult curriculum / short English islands / confusables |         8 |
| **Total**                                                  |    **80** |

Critically, don't make everything read speech. At least the 8 spontaneous cases should elicit things such as:

> Con nghĩ it's a cat.

> I don't know cô ơi.

> Con muốn nói yellow.

rather than asking the child to imitate a transcript.

You also need both English **single-word islands** and longer English spans. Parakeet may look excellent if your benchmark contains only `hello`, `banana`, `red`, `blue`, while failing badly once children produce an actual English clause.

---

## Annotation specification

Every audio item should have:

**Verbatim transcript**, including Vietnamese diacritics and actual disfluencies.

**Normalized scoring transcript**, using a frozen normalization policy for casing, punctuation, digits, contractions and filler handling.

**Token-level language IDs**:

`VI`, `EN`, `NAME/OTHER`

plus explicit switch boundaries.

Also annotate overlap, false start, truncation, unintelligible region, prompted versus spontaneous, microphone distance, classroom, age band, regional accent, device and measured noise/SNR where practical.

Every mixed utterance should be independently transcribed by **two annotators and adjudicated**. Double-annotate at least 20% of the monolingual controls too.

Do not bootstrap confidence intervals across 5,760 “independent” utterances. They aren't independent. Cluster/bootstrap by **child and classroom**, otherwise the confidence bounds will look much better than reality.

---

# 7. ASR shipping thresholds

I would refuse to ship a replacement unless the **locked 36-child set** meets all of these:

| Metric                                                      |                                            Required |
| ----------------------------------------------------------- | --------------------------------------------------: |
| Mixed VI↔EN WER                                             |                                            **≤20%** |
| Vietnamese-token WER                                        |                                            **≤15%** |
| English switched-token WER                                  |                                            **≤25%** |
| Curriculum target-word recall                               |                                            **≥97%** |
| Target-word recall under live-classroom noise               |                                            **≥95%** |
| Gross hallucination / translation / wrong-language failures |                                **<0.5% utterances** |
| Worst major age/region/noise subgroup mixed WER             |                                            **≤30%** |
| Candidate improvement over current faster-whisper           |               **≥20% relative mixed-WER reduction** |
| Allowed monolingual regression                              | **≤1 percentage point absolute** in either VI or EN |

The ≥20% relative improvement requirement is important. Going from, say, 24% WER to 23% WER does not justify replacing a working runtime.

The paired candidate-vs-baseline improvement should also have a 95% confidence interval excluding zero after clustering by child/classroom.

### Shipping-box latency

Benchmark with the **LLM and TTS already resident**, not on an otherwise empty workstation.

For 1–4-second child utterances I would require:

* **p95 end-of-speech → final transcript ≤600 ms**
* **p99 ≤1,000 ms**
* incremental ASR RSS **≤1.5 GB**
* no swapping
* zero model/runtime failures over a **10,000-utterance soak**

Those are Bright acceptance requirements, not claims that any candidate currently achieves them.

And this exposes an important research result: **I found no published CPU benchmark for Parakeet, PhoWhisper or Qwen3-ASR that legitimately answers your exact “1–4 s clip on cheap Intel with other models resident” question.**

We need to measure it ourselves. Anything more precise would be fake precision.

---

# 8. TTS: VieNeu-TTS v3 Turbo

The underlying recommendation is directionally good.

VieNeu v3 Turbo is unusually aligned with Bright:

* Vietnamese and English in the training/model design
* explicit bilingual/code-switching support
* offline inference
* ONNX Runtime CPU path
* INT8 CPU model
* permissive Apache-2.0 project/model positioning. ([Hugging Face][2])

Its current frontend, SEA-G2P, explicitly targets Vietnamese with English code-switch handling and is Apache-2.0. ([GitHub][13])

But there is a particularly relevant warning: an open SEA-G2P issue reports inaccurate detection of English substrings in Vietnamese-English code-switched text. ([GitHub][14])

That's almost exactly Piper's failure class wearing a more sophisticated coat.

So **Bright should not make automatic language detection inside authored pedagogical text authoritative.**

The content author/model already knows which span is English.

Carry that information.

---

## Does the same VieNeu speaker survive the language boundary?

Mechanically, the model can maintain the same speaker conditioning/reference across the utterance. VieNeu's built-in voices are represented with stable speaker/reference conditioning rather than selecting a separate speaker just because the input language changes. ([Hugging Face][2])

But your actual question is perceptual:

> Does it still sound like one teacher, with no accent/timbre/prosody discontinuity?

**Not established.**

I found no independent controlled test of VieNeu v3 Turbo measuring speaker similarity or MOS specifically before and after a VI→EN or EN→VI boundary.

Likewise, I found no published independent **first-audio latency measurement on a low-cost Intel Bright-like box** that I would accept as evidence. Maintainer throughput claims are useful for engineering triage, not adoption.

So the correct status is:

> **VieNeu v3 Turbo: best candidate, evidence incomplete, acceptance test mandatory.**

Not “rejected,” and not “adopted.”

---

# 9. TTS ranked table

| Rank             | Candidate                    | Intra-sentence VI-EN evidence                                                                                                                                                                                      | CPU / RAM fit                                                                                                                                 | Licence                                                                                                                                                                                    | Verdict                                         |
| ---------------- | ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------- |
| **1**            | **VieNeu-TTS v3 Turbo INT8** | Explicit VI-EN/code-switch design; same voice conditioning possible. **No independent controlled boundary-quality study found.** SEA-G2P also has a current English-substring detection issue. ([Hugging Face][2]) | Designed for ONNX/CPU INT8. No qualifying independent Bright-like Intel TTFA/RSS measurement found.                                           | **Apache-2.0**. ([PyPI][15])                                                                                                                                                               | **Test, likely winner**                         |
| **2**            | **MOSS-TTS v1.5**            | Official work claims multilingual/code-switch capability, and v1.5 includes Vietnamese among its language set. ([GitHub][16])                                                                                      | Main Local Transformer path uses a Qwen3-4B backbone, far less attractive beside Bright's resident LLM/ASR on a 16 GB CPU box. ([SGLang][17]) | Apache-2.0. ([GitHub][16])                                                                                                                                                                 | Good comparator, **wrong appliance size**       |
| **3**            | **Gwen-TTS 0.6B**            | VI and EN advertised, but I found no convincing VI↔EN intra-sentence benchmark. ([Hugging Face][18])                                                                                                               | 0.6B is manageable in principle, but published/tested path is GPU-oriented and no target Intel result found.                                  | Model advertises MIT, but training provenance involves large-scale crawled TikTok Vietnamese audio, creating a redistribution/provenance question I would not ignore. ([Hugging Face][18]) | **Do not ship without legal provenance review** |
| **Disqualified** | **OmniVoice**                | Technically multilingual/cross-lingual                                                                                                                                                                             | Irrelevant after licence failure                                                                                                              | Code may be Apache, but pretrained weights are **CC-BY-NC** because of training-data constraints. ([Hugging Face][19])                                                                     | **FAIL immediately**                            |

One useful additional data point against blindly trusting cross-language speaker cloning: OmniVoice's own material warns that cross-lingual generation can retain accent characteristics associated with the reference language. ([GitHub][20])

In other words, “same speaker embedding” does **not** imply “no accent break.”

---

# 10. The cheaper architecture is better

This is where I would change Bright's design.

## A. Authored curriculum speech: pre-render it

For:

> “This is a banana. Chuối, banana.”

why are we synthesizing it in the classroom at all?

The text lives in a curriculum library. Treat accepted speech audio just like an accepted image or clip.

At curriculum-build time:

**text → VieNeu → human/batch acceptance → compressed audio asset**

Then Classroom Core simply plays it.

That gives you:

* **0 ms synthesis latency at lesson time**
* zero variation between classrooms
* no language-detection failure
* human-auditable pronunciation
* no TTS CPU contention with the resident LLM
* deterministic behavior
* the ability to reject one bad line without rejecting a model

And storage is cheap.

This is not making Bright a scripted teacher. The **decision about what to teach remains agentic**. You're merely caching deterministic realizations of known pedagogical language.

That distinction is important.

---

## B. Dynamic speech: language spans must be typed data

Instead of:

```text
"This is a banana. Chuối — banana."
```

internally make the speech plan equivalent to:

```text
EN: "This is a banana."
VI: "Chuối"
EN: "banana."
```

The final speech surface can still be one utterance.

The critical change is that Bright already **knows the intended language**, so don't force G2P/LID to rediscover information the teacher just generated.

SEA-G2P's open VI-English substring-detection issue is exactly why this is preferable. ([GitHub][14])

I would make language-span metadata part of the `say` pathway before I would replace ASR or TTS models.

---

# 11. Should we concatenate separate VI and EN synthesis?

Yes, as a fallback.

For pedagogical constructions such as:

> “Chuối, banana.”

> “Đây là a cat.”

boundary segmentation is a completely defensible boring solution.

The cost is predictable:

**Prosody resets.** Two independent synthesis calls do not know the phrase-level intonation trajectory of the other side.

**Timbre can jump.** If you use different VI and EN voices, children may hear two teachers.

**Accent can jump.** This becomes especially obvious on short in-clause switches.

**Latency gets extra fixed overhead.** Two synthesis invocations cost more than one, although independent spans can sometimes be generated concurrently.

**Punctuation boundaries are forgiving.** `“Chuối. Banana.”` is vastly easier to splice naturally than `“Con muốn nói hello với cô.”`

So I would establish this fallback order:

**one bilingual model + typed language spans**
→ if unacceptable, **span synthesis using one closely matched speaker/voice system**
→ if still unacceptable, **rewrite dynamic mixed speech so switches coincide with prosodic boundaries**.

There is nothing pedagogically sacred about eliminating a 100 ms natural pause around a translation pair.

Production cloud TTS interfaces, while unsuitable as Bright dependencies, provide useful architectural precedent: major providers expose explicit language-span controls in SSML rather than asking one global language guess to govern every token. What their proprietary engines do internally, including whether they literally concatenate independent synthesis, is not public and should not be assumed. ([Microsoft Learn][21])

---

# 12. TTS acceptance corpus

For each teacher voice:

**240 utterances**, fully blinded during listening evaluation.

| Type                           |   Lines |
| ------------------------------ | ------: |
| VI→EN one switch               |      60 |
| EN→VI one switch               |      60 |
| English one-word islands in VI |      40 |
| Vietnamese islands in EN       |      20 |
| 2+ switches                    |      20 |
| Matched monolingual controls   |      40 |
| **Total**                      | **240** |

Use the **actual Bright curriculum vocabulary**, particularly colors, numbers, animals, classroom commands, names and pairs vulnerable to VI phonological substitution.

Three independent bilingual VI/EN adult raters per sample are enough for the engineering gate. Children come later for comprehension/usability validation, not for discovering obvious TTS defects.

Measure separately:

* Vietnamese word/tone correctness
* English word correctness
* same perceived speaker across switch
* accent jump
* boundary glitch
* prosodic discontinuity
* overall naturalness

### Pass criteria

| Criterion                            |                                Pass |
| ------------------------------------ | ----------------------------------: |
| Curriculum-keyword pronunciation     |     **≥99% majority-rater correct** |
| Same perceived speaker across switch |                      **≥95% clips** |
| Obvious accent/timbre/prosody break  |                       **<5% clips** |
| Naturalness                          |                        **≥4.0 / 5** |
| Mixed-vs-monolingual MOS penalty     |                            **≤0.3** |
| Recurrent systematic error           | **none occurring on ≥3 test lines** |

For **dynamic** speech on the shipping miniPC:

* p95 TTFA **≤350 ms** if genuinely streaming
* p95 RTF **≤0.6**
* incremental TTS RSS **≤750 MB**
* zero failures across **10,000 generated lines**
* no swapping with LLM + ASR + TTS resident

For pre-rendered curriculum speech, those latency requirements simply disappear.

That is another reason pre-rendering is such a large win.

---

# 13. Architecture I would actually ship

The resulting system would look like this:

```text
                         ┌──────────────────────┐
 authored curriculum ───►│ build-time VieNeu   │
 + typed VI/EN spans      │ + QA                │
                         └──────────┬───────────┘
                                    │
                              accepted audio
                                    │
                                    ▼
                               play_clip
                                   
 dynamic teacher text
         │
         ▼
 ┌───────────────────┐
 │ typed VI/EN spans │
 └─────────┬─────────┘
           ▼
 ┌───────────────────────┐
 │ VieNeu v3 bilingual   │
 │ one voice / utterance │
 └──────────┬────────────┘
            │ fails QA
            ▼
       span synthesis
       + boundary join


 CHILD SPEECH
      │
      ▼
 microphone/VAD
      │
      ▼
 faster-whisper small INT8      ← production baseline
      │
      ├── PhoWhisper             ← first challenger
      │
      └── Parakeet VI-EN CTC     ← second challenger
      │
      ▼
 semantic evidence / teacher
```

That preserves Bright's agentic nature while moving things that **do not need runtime intelligence** out of the critical path.

---

# 14. What I would change in the research brief / doctrine

Three things.

**First, delete “cannot transcribe mixed language by construction.”** Replace it with “utterance-level language conditioning can bias code-switched decoding; Bright's actual mixed-speech performance is unmeasured.” The published results make the former wording untenable. ([arXiv][1])

**Second, VieNeu should remain “recommended candidate,” not “recommended solution.”** Its engineering fit is excellent, but the exact thing Bright cares about, audible intra-sentence VI↔EN continuity, has not been independently demonstrated.

**Third, don't make ASR model selection the only lever.** Bright owns unusually strong context: curriculum vocabulary, recent board state, exercise target words, and the teacher's own preceding prompt. That context should eventually be used for **recognition scoring/evidence interpretation**, without mutating raw ASR into what the teacher expected the child to say. Keep raw transcript and contextual interpretation separate.

That last separation matters pedagogically. If a child says the wrong English word, a curriculum-biased decoder must not silently “correct” them and manufacture evidence of mastery.

---

# Bottom line

If I were freezing a Bright decision today, **August 18, 2026**:

> **ASR:** KEEP `faster-whisper small INT8`. Fix the assumption around the language token. Benchmark PhoWhisper first because it is nearly a runtime drop-in. Benchmark Parakeet second because it is explicitly VI-English CS, but its vendor itself warns that English coverage is limited and there is no target Intel/child evidence. Do not replace anything before the 72-child locked evaluation.

> **TTS:** PROVISIONALLY KEEP VieNeu-TTS v3 Turbo as candidate #1. Do not call it adopted. Introduce typed VI/EN spans immediately, because automatic substring language inference is unnecessary and demonstrably fallible. Pre-render curriculum utterances. Use live mixed VieNeu only for genuinely dynamic teacher speech.

> **Model research:** TSPC's 19.06% mixed WER is the most interesting 2026 research signal I found. It says purpose-built VI↔EN phonological modeling can beat generic multilingual ASR. But its 1.18-hour evaluation, synthetic training component, absence of Bright-age children, and lack of an immediately established appliance-ready distribution make it a research direction, not a production dependency. ([arXiv][1])

Most importantly, **the missing experiment is no longer another model survey**. Public evidence has reached its limit. The 72-child corpus plus a benchmark on the actual Intel SKU will tell you more than another 30 model cards.

I can also watch for new VI-EN ASR/TTS releases that materially change this decision.

[1]: https://arxiv.org/html/2509.05983v4 "TSPC: A Two-Stage Phoneme-Centric Architecture for Code-Switching Vietnamese-English Speech Recognition"
[2]: https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo "https://huggingface.co/pnnbao-ump/VieNeu-TTS-v3-Turbo"
[3]: https://github.com/SYSTRAN/faster-whisper "https://github.com/SYSTRAN/faster-whisper"
[4]: https://github.com/VinAIResearch/PhoWhisper/blob/main/LICENSE "https://github.com/VinAIResearch/PhoWhisper/blob/main/LICENSE"
[5]: https://huggingface.co/nvidia/parakeet-ctc-0.6b-Vietnamese "https://huggingface.co/nvidia/parakeet-ctc-0.6b-Vietnamese"
[6]: https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/ "https://www.nvidia.com/en-us/agreements/enterprise-software/nvidia-open-model-license/"
[7]: https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf "https://huggingface.co/Qwen/Qwen3-ASR-0.6B-hf"
[8]: https://huggingface.co/nvidia/parakeet-ctc-0.6b-Vietnamese/discussions/3 "https://huggingface.co/nvidia/parakeet-ctc-0.6b-Vietnamese/discussions/3"
[9]: https://github.com/VinAIResearch/PhoWhisper "https://github.com/VinAIResearch/PhoWhisper"
[10]: https://arxiv.org/html/2602.12911v1 "https://arxiv.org/html/2602.12911v1"
[11]: https://aclanthology.org/2020.lrec-1.47/ "https://aclanthology.org/2020.lrec-1.47/"
[12]: https://vlsp.org.vn/vlsp2023/eval/vmd "https://vlsp.org.vn/vlsp2023/eval/vmd"
[13]: https://github.com/pnnbao97/sea-g2p/blob/main/README.md?utm_source=chatgpt.com "sea-g2p/README.md at main"
[14]: https://github.com/pnnbao97/sea-g2p/issues?utm_source=chatgpt.com "Issues · pnnbao97/sea-g2p"
[15]: https://pypi.org/project/vieneu/ "https://pypi.org/project/vieneu/"
[16]: https://github.com/OpenMOSS/MOSS-TTS "https://github.com/OpenMOSS/MOSS-TTS"
[17]: https://sgl-project.github.io/sglang-omni/cookbook/moss_tts_local.html "https://sgl-project.github.io/sglang-omni/cookbook/moss_tts_local.html"
[18]: https://huggingface.co/g-group-ai-lab/gwen-tts-0.6B/blob/6cc7486b5cde2c134f0ca980c59b78e1a0fa55c6/README.md?utm_source=chatgpt.com "README.md · g-group-ai-lab/gwen-tts-0.6B at ..."
[19]: https://huggingface.co/k2-fsa/OmniVoice "https://huggingface.co/k2-fsa/OmniVoice"
[20]: https://github.com/k2-fsa/OmniVoice "https://github.com/k2-fsa/OmniVoice"
[21]: https://learn.microsoft.com/sr-cyrl-rs/azure/ai-services/speech-service/speech-synthesis-markup-voice "https://learn.microsoft.com/sr-cyrl-rs/azure/ai-services/speech-service/speech-synthesis-markup-voice"
