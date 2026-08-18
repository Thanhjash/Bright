# Deep Research Brief: Storage, Memory, and Retrieval for Bright

## Executive verdict

**Bright should not adopt a single “memory platform” or a single GraphRAG layer. The optimal architecture is three deliberately different stores with three different notions of truth.**

For Bright’s north star, the right design is:

| Store | Canonical truth | Retrieval now | Probabilistic / semantic layer | Recommendation |
|---|---|---|---|---|
| **A. Curriculum / media** | Markdown + assets in the library | scoped file read + SQLite FTS5/BM25 over markdown chunks | Local dense embeddings later, only if measured retrieval failures justify them | **YES now: markdown + FTS. Vectors later. GraphRAG not now.** |
| **B. Student memory** | SQL rows of validated categorical evidence | exact `student_id` scope + objective/recency queries + compact derived state | Counts + recency now; BKT later if cohort data supports fitting | **YES now: SQL evidence. Mem0/Letta/Graphiti as authority: NEVER.** |
| **C. Concept relations** | Authored curriculum relations in markdown | direct read; optionally compile to a tiny SQLite relation table | LLM extraction may suggest candidates, never silently commit them | **YES: authored graph. Auto-generated canonical KG: NEVER.** |

This is not conservatism for its own sake. It follows directly from what each store means.

A coding agent treats source files as truth and its index as disposable. **Store A should work exactly like that.** SQLite FTS5 already supplies phrase, prefix, boolean and proximity search plus built-in BM25 ranking, with no additional database service. BM25 remains a strong general retrieval baseline, while dense retrieval can provide complementary signals, particularly in multilingual settings, which argues for hybrid retrieval later rather than replacing lexical search now. citeturn23search0turn22academia24turn23academia25

A student model is categorically different. “Nguyen understands naming colors with moderate confidence based on four independent elicited responses” is an evidence-backed pedagogical state. It is **not a semantically similar piece of text**. Therefore Store B should be relational first, keyed first, provenance first. Vector similarity is the wrong primitive for its source of truth.

GraphRAG is also solving a different problem. Microsoft’s original GraphRAG work targets global sense-making questions over corpora around the million-token scale, constructing an LLM-extracted entity graph and community summaries before answering global questions. That is impressive technology, but “find the rubric for eliciting `yellow` in Colours” is not that problem. citeturn21academia14

My strong recommendation is therefore:

> **H0 Bright should become more like a good coding agent over a repo, not more like a memory-agent framework.**
>
> Markdown stays authoritative. SQLite becomes the local retrieval substrate. Student evidence remains keyed relational data. Hermes decides what to inspect next. Derived indexes and mastery estimates may be deleted and rebuilt without losing truth.

The most important immediate change is actually **not a new retrieval technology**. It is wiring persisted student evidence back into the teacher loop, because today Bright already has durable evidence but Hermes mainly sees the current-session RAM snapshot. Adding GraphRAG while failing to retrieve the student’s existing evidence would optimize the wrong layer.

## Method taxonomy by Bright store

No method has an inherent universal corpus-size threshold. The volume descriptions below are engineering judgments for Bright, informed by what the methods were designed and evaluated on, not claims that a paper establishes a fixed minimum.

| Method | Problem it actually solves | Data needed to become useful | Update cost / offline story | Hallucination or semantic-risk profile | Bright fit |
|---|---|---|---|---|---|
| **Keyword search / SQLite FTS5 / BM25** | Find passages containing known words, phrases, IDs, headings, near matches | Works immediately, even on tens of docs | Tiny. Index is local SQLite and incremental. FTS5 includes BM25 and weighted columns. citeturn23search0 | Very low indexing hallucination risk. Main failure is lexical mismatch | **A: YES now. B: YES only for secondary recall after exact student scope. C: useful adjunct** |
| **Dense vector RAG** | Semantic similarity where vocabulary differs | Useful once actual synonym, paraphrase or cross-language misses occur | Local embedding model + local vector index. Re-embed changed chunks | No graph hallucinations, but approximate similarity can retrieve plausible-but-wrong material; embeddings are sensitive data, not anonymization. citeturn23academia24 | **A: LATER. B: not authoritative. C: rarely needed** |
| **Hybrid BM25 + dense** | Combine exact identifiers with semantic matching | Needs enough retrieval queries to evaluate fusion | Incremental local indexes, modest ops if kept in SQLite | Lower lexical miss rate, but dense component still introduces semantic false positives | **A: likely H1 winner. B: only within one student’s already-filtered evidence if ever** |
| **Microsoft GraphRAG** | Corpus-wide themes, global summarization, graph-based local/global queries | Paper’s compelling use case was global questions over roughly 1M-token datasets. citeturn21academia14 | Expensive LLM indexing, graph extraction, community detection and summaries; official project explicitly warns indexing can be expensive. citeturn17view4 | LLM-extracted entities/edges/summaries can be wrong; stale derived graph after source edits | **A: LATER only after kill gates pass. B: NEVER. C: NEVER as canonical truth** |
| **LightRAG** | Lighter graph + vector retrieval with incremental updating | Medium/large corpora with genuine entity-relation retrieval problems | Better incremental story than classic GraphRAG, but still operates a graph and vector representation. citeturn21academia13 | Extraction errors become graph structure; extra storage/configuration surface | **A: LATER experiment. B: NEVER as authority. C: candidate-generation only** |
| **nano-graphrag** | Small, hackable implementation for understanding GraphRAG mechanics | Research/demo corpus | About 1,100 source lines excluding tests/prompts, can use local Ollama/transformers, but incremental insert still has graph/community work. citeturn15view1turn18view1 | Same conceptual extraction risks, fewer production safeguards | **A: YES to clone and learn from, NO to merge** |
| **HippoRAG / HippoRAG 2** | Associative and multi-hop retrieval through KG + Personalized PageRank | Valuable when questions genuinely require crossing facts/documents | Can be local, but graph construction plus embeddings/LLMs remain significant | Extracted graph can encode wrong relations; more moving pieces than lexical/hybrid retrieval | **A: LATER research candidate. B: NEVER as truth. C: candidate-generation only** |
| **SQL facts / observations** | Exact provenance, identity isolation, filtering, counting, auditing | Works from first observation | Excellent offline story. SQLite already in Bright | Almost no retrieval hallucination if IDs and constraints are validated | **B: emphatic YES, canonical** |
| **Counts + recency** | Summarize sparse evidence without pretending to know too much | Works at 1 to 8 observations, with uncertainty explicitly shown | Trivial computation, deterministic, rebuildable | Main risk is overinterpreting small samples, not model hallucination | **B: YES now** |
| **Elo-type model** | Jointly estimate learner ability and item/task difficulty from repeated learner-item outcomes | Needs repeated tasks/items across a population so difficulty is estimable | Cheap online updates, offline friendly | Confounds ability with poorly identified item difficulty when data are sparse or selection is adaptive | **B: LATER, after stable item IDs and cohort data** |
| **Bayesian Knowledge Tracing** | Infer latent mastery from sequences using prior, learning, guess and slip parameters | Per-student sequences can be short **if parameters were learned from pooled data**; fitting a bespoke model from 3–8 attempts/student is the wrong use | pyBKT is lightweight and offline | Wrong skill tagging or unstable guess/slip parameters produces confident-looking nonsense | **B: LATER, likely first model worth benchmarking** |
| **Deep Knowledge Tracing / pyKT models** | Flexible neural prediction from large interaction sequences | Typically benefits from substantial interaction datasets; pyKT exists precisely to benchmark many DLKT models across established datasets. citeturn21search0turn21search4 | PyTorch training, model management, more RAM/GPU, harder validation | Opaque latent state; evaluation leakage can materially inflate results, and pyKT researchers found many post-DKT gains surprisingly small. citeturn21search4 | **B: NEVER for H0/H1 production; research-only much later** |
| **Mem0-style memory** | Extract and retrieve persistent facts/preferences from messages and agent activity | Conversation/episode volume | Self-hostable, but introduces extraction, memory ranking and additional persistence semantics | Mem0’s April 2026 algorithm explicitly treats agent-generated facts as first-class memories and performs LLM memory extraction. citeturn15view2turn19search4 | **B: NEVER as Bright memory authority under NS-5** |
| **Letta memory / blocks** | Persistent context as part of a stateful agent runtime | Agent conversations/tasks | Self-hostable, but Letta itself is a stateful-agent platform, including skills/subagents. citeturn15view3turn18view3 | Agent-generated memory/state becomes another behavioral authority | **B: NEVER. Violates one-brain architecture** |
| **Graphiti** | Temporal KG from episodes, entity/relationship extraction and hybrid graph retrieval | Continuous episode stream | Requires graph storage such as Neo4j/FalkorDB/Neptune/Kuzu and an LLM/embedding stack; defaults to OpenAI but supports local compatible endpoints. citeturn16search1 | Episode-to-edge extraction and entity resolution can manufacture or merge incorrect facts | **B: NEVER as authority. C: research only** |
| **Authored tiny concept graph** | Explicit educational relations such as `banana -> yellow` or `apple is-a fruit` | Useful immediately | Edit markdown, optionally compile into SQLite | Essentially zero hallucination if author-reviewed | **C: YES** |

### Why FTS should win Store A now

The important comparison is not “old BM25 versus modern vectors.” It is **cost-adjusted retrieval quality for Bright’s actual query distribution**.

BEIR’s broad retrieval evaluation found BM25 to be a robust baseline, while stronger reranking/late-interaction methods incur higher computational cost. Multilingual Mr. TyDi found its zero-shot dense baseline below BM25 overall, while sparse+dense hybrid retrieval improved over BM25 by contributing complementary evidence. That pattern is exactly why Bright should preserve lexical retrieval and add semantic retrieval as a second signal only when the library demonstrates semantic misses. citeturn22academia24turn23academia25

Bright also has unusually strong lexical anchors that generic RAG systems often lack: unit names, objective IDs, filenames, headings, asset URIs, teaching terms, rubric labels and known curriculum vocabulary. Those are high-information tokens. Throwing them away in favor of pure vector similarity would be a regression.

For media, I would **not embed every image/audio/video in H0**. Put the pedagogical meaning in the surrounding authored markdown: what the asset depicts, which objective it supports, whether it is suitable for naming versus pointing, and its `asset://` URI. Hermes retrieves that instructional context and then calls `show_image`, `play_clip`, etc. A visual embedding can tell you two pictures both contain bananas. It cannot reliably tell you that one was authored to test receptive pointing while the other was authored for productive naming.

### Why graph methods are not nonsense, but still wrong today

Microsoft GraphRAG constructs a graph from source documents and community reports to answer questions that require global sense-making. Its original paper reports improvements for questions such as identifying themes across large corpora around one million tokens. citeturn21academia14 LightRAG combines graph structures and vector representations with an incremental-update design, targeting contextual dependencies and lower update cost. citeturn21academia13 HippoRAG combines LLM-derived knowledge structures and Personalized PageRank, reporting gains on multi-hop QA while reducing retrieval-time cost relative to iterative retrieval methods. citeturn21academia12 HippoRAG 2 further reports that structural retrieval can improve associative and sense-making memory while preserving factual retrieval better than its predecessor. citeturn21academia15

Those are real capabilities. They become relevant when Bright starts asking things like:

> “Across the entire Grade 4 science library, which prerequisite concepts recur in the units where learners typically fail to distinguish evaporation from condensation, and which existing assets address each prerequisite?”

That is plausibly a graph/global retrieval question.

Current questions such as:

> “What objective is being taught in `market-food`, what counts as correct evidence, and which image can I show next?”

are repo-navigation questions. Graph extraction is overhead, not leverage.

## Student memory: the learning-sciences answer

The deepest architectural mistake Bright could make is treating **memory retrieval** and **student modeling** as one problem.

They are not.

Memory retrieval asks:

> What evidence about this learner is relevant right now?

Student modeling asks:

> Given that evidence, what do we presently believe about the learner, with what uncertainty?

The first is a database query. The second is an inference problem.

### Make observations the immutable evidence ledger

Bright already has the right fundamental object: `observations` tied to student, objective/skill, result, session and response/activity provenance.

That should remain the source of truth.

A useful conceptual hierarchy is:

**Level of authority**

`observation evidence > derived objective state > session summary > model-generated pedagogical hypothesis`

The direction must never reverse.

A session summary saying “weak on yellow” cannot supersede four objective-linked observations showing later success. A BKT mastery probability cannot erase the attempts used to calculate it. A language model saying “the student seems confident” cannot create a new objective state unless a valid `record_evidence` event exists.

This is particularly important because BKT itself models a **latent** knowledge state. The original knowledge-tracing work estimated whether underlying production rules had been learned from observable learner performance, and pyBKT exposes priors, learning, forgetting, guessing and slipping as model parameters. citeturn22search0turn16search2 The probability is therefore an inference about evidence, not evidence itself.

### What to use before BKT

For the current 3–8 attempts-per-skill regime, I would use a deterministic summary with uncertainty rather than pretending there is enough information to personalize a four-parameter stochastic model per child.

For each `(student_id, objective_id)`, derive from valid observations:

| Derived field | Meaning |
|---|---|
| `valid_attempt_count` | Number of assessment events that actually tested the objective |
| `success_count` / `failure_count` | Evidence counts |
| `last_observed_at` | Recency |
| `recent_pattern` | e.g. last 3 valid outcomes, compact not transcript |
| `elicitation_modes_seen` | naming, pointing, matching, etc. |
| `independent_context_count` | Whether success repeats across activities rather than one repeated prompt |
| `estimate` | Conservative smoothed success estimate |
| `confidence` | Evidence coverage, not fake certainty |
| `next_evidence_needed` | Derived indication such as “productive naming not yet observed” |

Those fields can live in the existing `skills` representation where appropriate rather than creating another memory system. The state is **a cache over observations**, so it may always be reconstructed.

The sloppy `ask/point` versus `name` grading problem is more important than replacing the statistical estimator. A receptive “point to the banana” success is not evidence of productive “say banana” performance. No BKT or DKT model can rescue bad semantic labeling. Before sophisticated KT, Bright should record enough categorical assessment context to distinguish **what behavior was elicited**.

In other words:

> **Better evidence ontology beats a better estimator at H0.**

### Where Elo fits

Elo is attractive because it is simple, online and computationally cheap. The educational adaptation treats a learner response like an interaction between learner ability and item difficulty, updating estimates as outcomes arrive. But that only becomes useful when Bright has stable, repeatedly used item or activity identifiers across enough students to estimate difficulty rather than simply rediscovering random noise. Adaptive selection can itself complicate convergence and introduce bias in Elo-style ratings, so it should not silently become “mastery truth.” citeturn8search0turn8search2

For Bright, Elo is therefore **not the first upgrade**. It becomes interesting when 20–40-child deployments generate repeated item/objective interactions across classrooms and you genuinely want to learn, for example, that one naming prompt is much harder than another.

### Where BKT fits

BKT is a substantially better conceptual match than DKT because Bright has authored objective IDs and cares about explainable skill state.

pyBKT implements BKT and variants, supports fitting, prediction and cross-validation, and its roster abstraction can keep current learner state after a globally fitted model exists. citeturn16search2turn22search1

But there is a critical distinction:

**Three to eight attempts per learner does not automatically invalidate BKT inference.** It invalidates the idea of fitting reliable per-child/per-skill transition, slip and guess parameters from those three to eight observations.

A sensible future regime is:

1. collect sparse evidence per individual,
2. pool observations from many learners for the same well-defined objective/task family,
3. fit shared BKT parameters,
4. validate those parameters out-of-sample,
5. use each learner’s short sequence to update their latent mastery probability.

That is defensible.

Trying to discover four or more skill-specific parameters from a handful of responses by one child is not.

### Why DKT is the wrong production bet

The original DKT architecture used recurrent neural networks to learn flexible student interaction dynamics rather than manually encoding domain structure. citeturn21search0 That flexibility is precisely what makes it a poor first fit for Bright: Bright already has useful domain structure, sparse observations, strict explainability requirements and very cheap offline hardware.

More importantly, the pyKT benchmark authors explicitly warn that evaluation setup can cause label leakage and performance inflation, and their standardized comparisons found that improvements from numerous later deep-KT approaches were often minimal compared with the original DKT. citeturn21search4

For Bright, a neural KT system would add training infrastructure, opaque latent representations and larger data requirements before fixing the actual bottleneck, namely reliable evidence labeling.

**Recommendation: pyKT is a benchmark/research repo, not a Bright dependency.**

### Why Mem0, Letta and Graphiti fail NS-5

Mem0’s current architecture is optimized around persistent agent/user memories. Its April 2026 update describes single-pass memory extraction, entity linking, hybrid retrieval and, crucially, **agent-generated facts as first-class memories**. citeturn15view2turn19search4 That makes sense for general assistants. It is dangerous for a child evidence store whose central doctrine is “the agent does not get to turn conversational impressions into truth.”

You could technically feed only already-validated `record_evidence` objects into Mem0. At that point, however, Mem0 is solving a problem SQLite already solves more safely and transparently. You would be paying an extraction/ranking/runtime tax to store structured facts you already possess.

So my verdict is:

**Mem0: CLONE for memory-retrieval ideas. NEVER make it the Bright student-memory authority.**

Letta is an even clearer architectural mismatch. Its repository describes it as a platform for stateful agents and exposes local agents, agent SDKs, skills and subagents. citeturn15view3turn18view3 Bright has explicitly chosen one brain, Hermes. Putting Hermes inside, beside or behind a second stateful-agent runtime destroys that architectural clarity.

**Letta: NEVER merge into Bright.**

Graphiti is technically interesting because it builds temporal knowledge graphs from episodes and supports hybrid search and graph-distance reranking. Its own quickstart involves adding text/structured episodes, graph databases and LLM/embedding providers. citeturn16search1 That is almost the inverse of Bright’s desired student-memory contract. Bright already knows the important entity and relation: *student X produced categorical evidence E for authored objective O at time T*. Extracting a second approximate graph from prose introduces uncertainty where there currently is none.

**Graphiti: NEVER as Store B. At most, evaluate its temporal-edge ideas for non-child domains.**

## Open-source repos to clone and evaluate

Star counts below are snapshots from recent GitHub crawls and will move. Where GitHub’s rendered repository page did not expose a reliable last-commit timestamp, I do not invent one; I report the latest visible activity marker instead. This matters because “popular” is not the same as “appropriate.”

| Repo | License / current activity | Install and official demo to run | What Bright should steal | What Bright should not merge |
|---|---|---|---|---|
| **Microsoft GraphRAG**  `https://github.com/microsoft/graphrag`  Clone: `https://github.com/microsoft/graphrag.git` | MIT, about **35.4k stars** in current crawl. citeturn17view4 Recent 2026 project activity is visible; official docs warn indexing can be expensive. | `pip install graphrag` then follow official init/index/local/global query quickstart on a disposable corpus | Distinction between local retrieval and **global corpus questions**; evaluation of whether a query really needs graph/global reasoning | Indexing pipeline, community reports, graph state, or GraphRAG as Classroom Core |
| **HKUDS/LightRAG**  `https://github.com/HKUDS/LightRAG`  Clone: `https://github.com/HKUDS/LightRAG.git` | MIT, about **38.7k stars**; repository news shows active feature work through July 2026. citeturn18view0turn19search3 | `pip install lightrag-hku`; run an official `examples/` SDK sample, preferably with a local-compatible LLM for the offline test | Incremental indexing concepts, dual-level retrieval, hybrid graph/vector evaluation | Four-store/server architecture, extracted KG as curriculum truth |
| **gusye1234/nano-graphrag**  `https://github.com/gusye1234/nano-graphrag`  Clone: `https://github.com/gusye1234/nano-graphrag.git` | MIT, about **4.0k stars**, 155 commits in current crawl. citeturn18view1 | Clone then `pip install -e .`; run the official Dickens `mock_data.txt` demo and compare local/global query results | Small readable reference implementation, roughly 1,100 lines excluding prompts/tests, good for understanding what GraphRAG actually costs conceptually. citeturn15view1 | Nothing production-side. It is a learning specimen, not Bright infrastructure |
| **OSU-NLP-Group/HippoRAG**  `https://github.com/OSU-NLP-Group/HippoRAG`  Clone: `https://github.com/OSU-NLP-Group/HippoRAG.git` | MIT, about **3.9k stars**; GitHub organization activity showed an update on July 29, 2026. citeturn17view3 | `pip install hipporag`; run README quickstart, then a local-LLM variant if available on the evaluation box | Personalized PageRank / associative multi-hop retrieval ideas, especially for future prerequisite discovery | Graph extraction/indexing as student memory; neuro-memory branding is irrelevant to product fit |
| **mem0ai/mem0**  `https://github.com/mem0ai/mem0`  Clone: `https://github.com/mem0ai/mem0.git` | Apache-2.0, about **62.9k stars**; new memory algorithm announced April 2026. citeturn18view2turn15view2 | `pip install mem0ai`; use **synthetic adult/test data only**, run add/search and inspect exactly what gets persisted | Multi-signal retrieval, memory evaluation methodology, explicit user scoping patterns | Message-to-memory extraction, agent-generated facts as learner truth, cloud path, or child conversational memory |
| **letta-ai/letta**  `https://github.com/letta-ai/letta`  Clone: `https://github.com/letta-ai/letta.git` | Apache-2.0, about **24.2k stars**; v0.16.7 was released March 31, 2026 in visible release history. citeturn18view3turn19search5 | `npm install -g @letta-ai/letta-code`; start one local throwaway stateful agent and inspect its memory behavior | Ideas about explicit context blocks and memory observability | **The runtime itself.** It is another agent platform, contradicting Hermes-is-the-teacher |
| **getzep/graphiti**  `https://github.com/getzep/graphiti`  Clone: `https://github.com/getzep/graphiti.git` | Apache-2.0, about **29.7k stars**. citeturn17view2 | `pip install graphiti-core`; use the official quickstart with the lightest supported local graph backend, then add synthetic episodes and inspect generated nodes/edges | Temporal validity, provenance ideas, hybrid edge/node retrieval concepts | Episode ingestion for children, automatic KG as evidence authority, permanent graph DB dependency |
| **CAHLR/pyBKT**  `https://github.com/CAHLR/pyBKT`  Clone: `https://github.com/CAHLR/pyBKT.git` | MIT, about **273 stars**, 379 commits in current crawl. citeturn17view0turn17view1 | `pip install pyBKT`; run the official quickstart or provided Cognitive Tutor example, fit and cross-validate a basic model | BKT equations, fitting/cross-validation machinery, parameter diagnostics, roster/state concept | Do not insert pyBKT into the live loop until Bright has enough pooled, correctly tagged observations |
| **pykt-team/pykt-toolkit**  `https://github.com/pykt-team/pykt-toolkit`  Clone: `https://github.com/pykt-team/pykt-toolkit.git` | MIT, about **423 stars** on the current organization listing; 768 commits in the repo crawl. citeturn16search4turn16search0 | `pip install -U pykt-toolkit`; run DKT against one bundled/standard dataset using the authors’ documented evaluation flow | Benchmark discipline, train/validation/test hygiene, comparison metrics | PyTorch KT stack, neural student state, or pretrained assumptions in production |
| **asg017/sqlite-vec**  `https://github.com/asg017/sqlite-vec`  Clone: `https://github.com/asg017/sqlite-vec.git` | Dual MIT/Apache-2.0, about **8.0k stars**. Latest visible published release is v0.1.9, March 31, 2026. Project warns it is pre-v1 and may make breaking changes. citeturn18view4turn16search3 | `pip install sqlite-vec`; run the minimal Python vector-query example locally | **This is the best-fit extra repo.** Keep vectors inside the SQLite operational envelope rather than introducing Qdrant/Milvus/Neo4j for Store A | Do not add it until dense retrieval passes an actual Bright benchmark; do not treat embeddings as canonical data |

### The better-fit project is sqlite-vec, not another agent-memory framework

`sqlite-vec` is unusually aligned with Bright. It is a small SQLite vector-search extension written in C with no external database service, supports Raspberry Pi-class environments, has Python bindings, and is dual MIT/Apache licensed. citeturn16search3turn18view4

That does **not** mean “install it now.”

It means that once semantic retrieval earns its place, the natural architecture is:

**Markdown truth → SQLite FTS5 lexical index + SQLite vector index → hybrid rank → Hermes reads source markdown**

not:

**Markdown → ingestion platform → hosted embeddings → separate vector DB → separate graph DB → memory service → Hermes**

The former can plausibly be repaired by someone carrying one database file and the curriculum directory. The latter is hostile to village-school operations.

There is one caution: `sqlite-vec` explicitly remains pre-v1, and issues have exposed platform/package rough edges. Treat it as a component to qualify on the exact ARM/Linux hardware Bright expects to ship, not as a guaranteed drop-in. citeturn16search3turn16search9

## Target architecture across Bright’s horizons

### H0: what to build this month

**Do not add vectors, GraphRAG, BKT, Mem0, Letta or Graphiti.**

The month’s architecture should be:

```text
                  HERMES, ONE TEACHER
                         |
            +------------+------------+
            |            |            |
       curriculum     student       room state
        retrieval      recall       + board
            |            |
     markdown truth   SQL truth
            |            |
      FTS5/BM25       observations
     disposable idx       |
            |          derived
       asset:// refs   skill state
```

This preserves the locked doctrine. The indexes help Hermes inspect the world. They do not become the world.

#### Store A this month

Keep:

- `content/library/index.md`
- `how-to-teach.md`
- unit `map.md`, `keys.md`, `practice.md`
- assets and `asset://`
- `unit_catalog()`
- `read_library`
- `search_library`

Change the **backend quality**, not the agent workflow.

Index markdown at heading/section granularity into SQLite FTS5. Give authored structural fields different ranking significance: objective IDs and headings should outrank incidental body mentions. SQLite FTS5 directly supports weighted BM25 columns, phrases, prefixes, NEAR queries and boolean composition. citeturn23search0

The important architectural rule is:

> **The FTS row is a pointer into markdown, never a second curriculum copy that an author edits.**

Edit markdown, update the corresponding disposable index records quickly, done.

Do not semantically index raw images/audio yet. Add or strengthen authored descriptions where an asset’s intended pedagogical use is not obvious from the surrounding unit.

#### Store B this month

Wire persisted recall into the actual Hermes turn.

The high-value path is:

```text
student_id
  → exact observations for currently relevant objectives
  → compact objective state
  → selected older evidence / summaries
  → Hermes context
```

Never:

```text
"Who does this sound like?"
  → semantic search over all students
  → maybe Student X
```

For long-term student state, define a strict invariant:

> **No retrieval operation is allowed to rank across students first and filter afterward. Exact identity scope comes before relevance ranking.**

This is your primary defense against cross-student memory leakage.

Use the existing `skills` state as a derived cache, with semantics that can be explained from observations. For H0 I would derive, per objective:

`attempts`, `successes`, `failures`, `last_seen`, `recent_valid_results`, `elicitation coverage`, `estimate`, `confidence`.

The exact smoothing function matters far less than not overstating a sample of four attempts.

`session_summaries` should remain useful, but **derived**. A summary may influence what Hermes examines next. It should never be able to fabricate a skill or objective that cannot be traced to valid observations.

`memories_fts` can remain, but only for curated evidence-derived summaries and only behind mandatory `student_id` scoping. I would not put raw ASR, raw child utterances or general conversation into it.

#### Fix the evidence semantics before the estimator

Add enough categorical evidence metadata to distinguish at least:

- productive response,
- receptive selection/pointing,
- recognition/matching,
- prompted versus independent response,
- assessment versus teaching/practice exposure.

Whether these become columns or normalized categorical fields is an implementation decision. The crucial requirement is that the objective rubric defines what counts.

A teacher who asks “point at yellow” and records evidence for “name yellow orally” has not made a Bayesian-estimation error. It has made a **measurement-validity error**. BKT would merely put a decimal point on it.

### What Hermes should receive on a turn

Do not dump the database into context.

An H0 starting budget I recommend, as an engineering target rather than a literature constant, is **roughly 1,800–2,600 retrieval/state tokens per teacher turn**, with hard truncation and tool-based deep reads available afterward.

| Context component | Starting budget | Content |
|---|---:|---|
| **Student evidence snapshot** | 300–550 tokens | Relevant objective states, counts/confidence, last meaningful evidence, unresolved evidence gaps |
| **Current room/session state** | 200–350 | Current students/identity status, board state summary, active unit/objective, most recent activity outcome |
| **Curriculum retrieval** | 700–1,200 | 2–5 relevant markdown sections, paths/headings retained |
| **Relevant professional guidance** | 250–400 | `how-to-teach.md` snippets only when task needs them |
| **Headroom / retrieval metadata** | 200–300 | source paths, objective IDs, asset references |

This is a **working set**, not memory.

Hermes can then behave like a coding agent: search, inspect a map, read a relevant file more deeply, inspect the board, teach, observe and record evidence.

A compact learner injection should look conceptually like:

> `student_id=S017`  
> `objective=colours.name-yellow`  
> valid evidence: 4 attempts, 2 independent correct naming, 1 prompted correct naming, 1 failure; last seen 9 days ago  
> receptive identification: strong, 3/3  
> productive naming confidence: limited/moderate  
> evidence gap: no independent naming in a novel image context

It should **not** contain:

> Last Tuesday the student said “uh yellow maybe banana…” and then the teacher replied…

The first represents semantic pedagogical evidence. The second reintroduces chat logs as memory through the back door.

### H1: many subjects, still one child

Do **not** trigger dense retrieval on a magic file count.

Trigger it on a failed retrieval benchmark.

At this stage, create a Bright-specific test set of perhaps 100–200 teacher retrieval tasks spanning:

- exact objective lookup,
- synonym/paraphrase lookup,
- Vietnamese-to-English conceptual lookup where appropriate,
- cross-unit prerequisite lookup,
- asset selection,
- rubric lookup,
- professional-practice questions,
- questions whose answer requires two curriculum sections.

Then measure Recall@5 / MRR plus, more importantly, **teacher-task success**.

BM25 is a robust baseline across heterogeneous retrieval tasks, while multilingual work shows dense signals can help when fused with lexical ranking. citeturn22academia24turn23academia25

My H1 upgrade gate would be:

> Add local embeddings only if lexical retrieval demonstrably misses important semantic/cross-language queries often enough to matter.

An engineering trigger could be:

- lexical Recall@5 below 90–95% on the Bright gold set, **and**
- at least half the misses are genuine semantic mismatch rather than bad document authoring, **and**
- hybrid retrieval recovers at least half of those misses without materially increasing false-positive curriculum retrieval.

Those thresholds are product gates, not claims from a paper.

The H1 retrieval stack becomes:

```text
query
 ├─ FTS5/BM25 ----------------┐
 └─ local dense embedding ----┤
                              ├─ reciprocal/fused ranking
                              ↓
                    markdown section pointers
                              ↓
                    Hermes reads originals
```

Use the same SQLite operational boundary if possible. `sqlite-vec` is the first project I would test for the dense index because it avoids operating a separate vector service and is designed to run where SQLite runs, including Raspberry Pi-class devices. citeturn16search3turn18view4

Dense embeddings are **not anonymized text**. Research has demonstrated that dense text representations can leak substantial original information, including recovery of names in sensitive text. citeturn23academia24 Therefore even a local embedding index containing child evidence should be treated as sensitive student data. This is another reason not to vectorize Store B casually.

### When GraphRAG enters H1

Not because there are “many subjects.”

It enters only when the **shape of important queries changes**.

If authors/teachers routinely need global questions involving relationships distributed across many units, then benchmark:

1. hybrid BM25+dense,
2. LightRAG,
3. HippoRAG,
4. optionally Microsoft GraphRAG.

LightRAG is the first graph system I would evaluate for an evolving curriculum because incremental updating is part of its design. citeturn21academia13 HippoRAG is the more interesting research candidate if Bright demonstrates genuine multi-hop prerequisite/relation retrieval failures. citeturn21academia12turn21academia15

But **none of these should replace markdown as truth**.

### H1 student model

Continue counts+recency until the data say otherwise.

Once multiple learners have accumulated enough well-tagged observations, clone pyBKT and retrospectively ask:

> Does BKT better predict held-out valid responses or better select useful next evidence opportunities than the simple baseline?

Do not ask whether BKT produces prettier mastery probabilities.

A BKT model earns deployment only if it improves a Bright-relevant outcome, preferably:

- future valid-response log loss/calibration,
- mastery-state calibration,
- fewer unnecessary repeated checks,
- faster detection of genuine weakness,
- better delayed-retention predictions.

The pyBKT tooling includes model fitting, evaluation and cross-validation, which makes it a good offline experiment dependency without making it a classroom runtime dependency. citeturn16search2turn22search1

### H2: twenty to forty children plus camera identity

**The storage model should barely change.**

That is a feature.

Camera identity must answer exactly one question:

> Which existing `student_id`, if any, is this evidence associated with?

It must not answer:

> What does this child know?

And it must not make a fuzzy semantic guess that leads to memory mutation.

The write path should conceptually be:

```text
classroom observation
       |
identity confidence gate
       |
       +-- uncertain --> ephemeral classroom event only
       |                 NO student memory write
       |
       +-- certain ----> student_id
                           |
                     valid objective?
                           |
                     valid evidence?
                           |
                     observation write
```

This follows Bright’s doctrine that uncertain identity means no student-memory write.

For class teaching, maintain two different views:

**Per-student evidence** remains strictly isolated.

**Class state** is a derived, non-authoritative aggregate used for pacing, for example:

> 21/28 identified learners have recent evidence for objective O; 9 appear to need another productive naming check; 6 identities presently unresolved.

Do not copy everybody’s textual summaries into one giant class memory. Derive aggregates from keyed states.

The shift from one child to forty children therefore requires stronger **identity isolation, transaction discipline and retrieval batching**, not GraphRAG.

## Kill criteria and the short experiment

These criteria are intentionally hard. Fashionable infrastructure should have to earn its watts.

### Kill-criteria table

| Candidate | Kill it when… | Pass gate before reconsideration | Bright today |
|---|---|---|---|
| **Microsoft GraphRAG for Store A** | Most valuable queries are scoped lookups, exact objectives/assets/rubrics; ordinary retrieval already succeeds; curriculum edits are frequent relative to graph re-indexing; graph extraction introduces unverifiable edges | At least ~20% of high-value gold queries are genuine global/multi-hop queries **and** GraphRAG materially beats hybrid retrieval on them, while indexing remains operationally acceptable on target hardware | **KILL** |
| **LightRAG for Store A** | Hybrid FTS+dense solves the gold set nearly as well; graph/entity extraction errors require author review; incremental index is still too costly for edit-and-drop-assets workflow | ≥10 percentage-point improvement on the hard-query subset, or clear qualitative wins unavailable to hybrid retrieval, with fast incremental edits | **KILL now, benchmark H1** |
| **HippoRAG for Store A** | Curriculum tasks are mostly single-document retrieval rather than associative/multi-hop navigation | Repeated multi-hop failures where PPR/KG retrieval beats hybrid RAG in Bright’s own corpus | **KILL now** |
| **Any generated KG for Store C** | Edge precision is not effectively author-grade; LLM can invent objective IDs or relations; corrections cannot flow directly from markdown | Every proposed edge has source provenance and canonical promotion requires author approval | **AUTO-WRITE: NEVER** |
| **Elo for Store B** | Item/task IDs are unstable, most prompts are unique, or there is insufficient repeated learner-item interaction to estimate item difficulty | Stable reusable items/tasks plus enough population data for item-difficulty estimates to remain stable out-of-sample | **KILL now** |
| **BKT for Store B** | You are fitting per-child/per-objective parameters from 3–8 attempts; skill definitions mix receptive/productive behaviors; fitted guess/slip/learn parameters are unstable or hit degenerate boundaries | Pooled cohort dataset with stable objective tagging, bootstrap/CV parameter stability, and a meaningful held-out improvement over counts+recency | **KILL fitting now; preserve as H1 candidate** |
| **DKT / pyKT production** | Dataset remains sparse; gains are tiny; model is poorly calibrated; training/runtime adds GPU/ops complexity | Large clean interaction corpus, no leakage, significant out-of-classroom held-out gain over BKT/simple baseline, acceptable CPU inference | **KILL for foreseeable production** |
| **Mem0 for Store B** | Raw messages/ASR/transcripts enter memory extraction; agent-generated “facts” are allowed to become learner state; memory cannot be traced to objective evidence; student isolation relies on soft prompt conventions | Only validated structured evidence enters it, strict student isolation proven, and it beats SQL on a concrete need | Under those constraints it adds little value, so **NEVER as authority** |
| **Letta** | Hermes remains Bright’s one brain | Would require abandoning the locked one-brain doctrine | **NEVER** |
| **Graphiti for Store B** | Student evidence already has exact entities, objective IDs and timestamps; graph needs LLM extraction of episodes | A non-student domain emerges where temporal entity resolution is genuinely required | **NEVER for student memory** |
| **Dense vector retrieval for Store A** | BM25 solves the real query set; vectors add false positives, model/download footprint or unacceptable indexing time | Material recall gain on synonym/multilingual queries with a fully local shippable embedding model | **LATER** |
| **sqlite-vec** | Target ARM/Linux packaging is unreliable, extension complicates deployment, or hybrid retrieval gains are negligible | Hardware qualification + benchmark win | **Good H1 candidate** |

### A concrete BKT admission test

Because the current evidence regime is so sparse, I would establish a conservative Bright-specific admission gate rather than pretending there is a universal “minimum N” in BKT literature.

Do not fit an objective-specific BKT model until you have, as a **starting experimental threshold**, roughly **200 valid pooled responses from at least 30 learners**, with more than one observation per learner and consistent task semantics. That is not a theorem. It is a deliberately conservative engineering gate that can be revised after simulation and bootstrap analysis.

Then fit across bootstrap samples. Reject the model if:

- prior/guess/slip/learn estimates vary wildly between folds,
- estimates repeatedly collapse near parameter boundaries,
- calibration is poor,
- held-out predictive log loss does not beat the simple model,
- the model changes decisions mainly because receptive and productive evidence were conflated.

pyBKT provides the necessary fitting and cross-validation machinery to run that investigation offline. citeturn16search2turn22search1

Even if BKT wins, keep `observations` as truth and BKT state as a rebuildable derivative.

### A one-to-two-day experiment

Do **not integrate any of these into Bright production**.

The best three-repo experiment is:

#### Clone nano-graphrag

Why this one instead of Microsoft GraphRAG first: you want to understand the mechanism, not benchmark enterprise machinery.

```text
git clone https://github.com/gusye1234/nano-graphrag.git
```

Run its official Dickens demo. The project deliberately provides a compact implementation and an official sample using *A Christmas Carol*. citeturn15view1

Then replace Dickens with a **copy** of a synthetic curriculum-sized corpus, not production Bright data. Ask:

- exact lookup questions,
- local relationship questions,
- global theme questions.

Write one page:

**Steal:** local/global query distinction, graph inspection, anything useful about chunking.

**Do not merge:** LLM extraction pipeline, community state, dependency surface.

#### Clone pyBKT

```text
git clone https://github.com/CAHLR/pyBKT.git
```

Run the official sample/tutorial dataset and reproduce one model fit plus cross-validation. pyBKT is MIT licensed and explicitly provides fitting/prediction/CV functions. citeturn17view0turn16search2

Then create **synthetic Bright-shaped data** with 3, 5 and 8 attempts/student under known ground-truth parameters.

Ask:

- how unstable is fitting when only one learner supplies data?
- how does pooled fitting behave?
- after globally fitting parameters, how quickly can short learner sequences update mastery?
- how sensitive is the estimate to one mislabeled “point” response entered as “name”?

That last experiment may teach you more than a week of architectural discussion.

Write one page:

**Steal:** parameterized mastery update and calibration tools.

**Do not merge:** live dependency until Bright has pooled evidence and validation.

#### Clone sqlite-vec

```text
git clone https://github.com/asg017/sqlite-vec.git
```

Install the Python package and verify it on the **actual cheap hardware class** or closest available ARM/Linux box. `sqlite-vec` is designed to run inside SQLite and advertises Raspberry Pi support, but remains pre-v1, so hardware qualification matters. citeturn16search3turn18view4

Index a small synthetic curriculum and compare:

- FTS5 only,
- dense only,
- simple hybrid.

Include Vietnamese/English paraphrases in the test because multilingual retrieval is one credible reason vectors may eventually earn their footprint; Mr. TyDi provides evidence that dense signals can improve lexical retrieval in hybrid systems even when dense-only retrieval is weaker. citeturn23academia25

Write one page:

**Steal:** local vectors inside SQLite.

**Do not merge:** anything, unless the benchmark produces a meaningful retrieval gain.

I would **not spend the two-day spike installing Mem0, Letta or Graphiti first**. Their architectural mismatch is already clear enough from their documented operating models. Mem0 extracts conversational/agent facts into memory; Letta is an agent runtime; Graphiti extracts temporal graphs from episodes. citeturn15view2turn15view3turn16search1 The unanswered empirical questions for Bright are GraphRAG value, BKT behavior under sparse evidence and local hybrid retrieval cost.

## Risks and final architecture decision

### Privacy and PII

The rule “do not send raw transcripts” must extend to **derived representations**.

Text embeddings are not safe anonymization. Embedding-inversion work has shown that substantial original text can be reconstructed from dense embeddings, including personally identifying information in sensitive datasets. citeturn23academia24turn23search2

Therefore:

- child evidence embeddings, if ever created, are sensitive data;
- real names should not be part of curriculum/vector queries sent to hosted models;
- hosted MiMo should see opaque `student_id` plus pedagogically necessary evidence, not identity;
- camera embeddings/templates should be local identity infrastructure, isolated from the teaching-model context;
- deleting source PII must include derived representations and caches, not merely rows visible through an application query.

A 2026 preprint additionally reports recoverability of soft-deleted vectors in several HNSW indexes, reinforcing the principle that “deleted from logical search” and “physically erased” are not equivalent. Treat that result as recent research rather than mature consensus, but its operational warning is sound. citeturn23academia26

### Cross-student leakage

This is the highest-consequence Store B engineering failure.

Never use:

> semantic query → top memories across database → inspect student IDs afterward.

Use:

> certain `student_id` → database scope → objective/task filters → relevance/recency ranking.

Add adversarial tests where two children have near-identical objective histories but opposite outcomes. A query for Student A must return zero Student B rows even when B’s evidence text is a much better semantic match.

For 20–40 children, use separate keyed learner snapshots and anonymous class aggregates. Do not concatenate individual summaries into one searchable “class memory.”

### Index drift

Every noncanonical representation must be rebuildable.

That includes:

- Store A FTS index,
- future embeddings,
- generated retrieval metadata,
- BKT/Elo/mastery estimates,
- session summaries,
- Store C compiled relation table.

Each derived object should carry enough source/version information to know when it is stale.

**Markdown and observations survive an index failure.**

That property is enormously valuable offline.

### Hallucinated curriculum edges

Bright has already observed the most relevant failure mode: invented objective IDs.

That means auto-KG extraction should be held to a stricter standard than ordinary RAG retrieval.

For Store C:

```text
keys.md / curriculum markdown
          |
          ↓
     canonical relations
          |
          +--> optional SQLite compiled relations

LLM extraction
          |
          ↓
  proposed_relation_candidates
          |
      HUMAN/AUTHOR REVIEW
          |
          ↓
      markdown edit
```

Never let the downward path bypass the markdown authoring layer.

A graph claiming `banana is-a colour` is not merely a retrieval error. Once persisted into a KG it can contaminate retrieval, assessment and future generated material repeatedly.

### Cheap hardware and watt budget

The easiest way to hit the hardware target is to avoid permanent services.

SQLite FTS5 gives local ranked text retrieval inside infrastructure Bright already has. citeturn23search0 `sqlite-vec` offers a plausible future route to local dense retrieval without another database daemon and is specifically designed to run across environments including Raspberry Pi. citeturn16search3turn18view4

In contrast, Graphiti introduces a graph-storage layer plus LLM/embedding inference; GraphRAG-style systems incur LLM-based graph extraction/indexing; DKT adds PyTorch model training and lifecycle. citeturn16search1turn21academia14turn21search0

On donated hardware, every daemon is a tax. Every independently versioned index is a repair burden. Every GPU-only optimization is a deployment constraint.

Tiny ops should be treated as a first-class pedagogical requirement because a theoretically better retrieval score is worthless if the classroom cannot restart after a power cut.

### Licensing

The principal evaluation projects are unusually favorable from a shipping perspective:

- Microsoft GraphRAG: MIT. citeturn17view4
- LightRAG: MIT. citeturn18view0
- nano-graphrag: MIT. citeturn18view1
- HippoRAG: MIT. citeturn17view3
- Mem0: Apache-2.0. citeturn18view2
- Letta: Apache-2.0. citeturn18view3
- Graphiti: Apache-2.0. citeturn17view2
- pyBKT: MIT. citeturn17view0
- pyKT Toolkit: MIT. citeturn16search0
- sqlite-vec: MIT/Apache-2.0 dual licensing. citeturn18view4

That removes one class of obstacle, but **dependency licenses and model-weight licenses still require separate review** before a zero-cost hardware image ships. A permissively licensed retrieval library does not automatically make its default embedding model, LLM checkpoint or optional database dependency equally shippable.

### Final decision

The architecture I would sign off as principal engineer is:

```text
BRIGHT
│
├── HERMES: the sole teaching agent
│
├── STORE A: CURRICULUM
│   ├── canonical: markdown + asset:// media
│   ├── H0 retrieval: catalog + FTS5/BM25 + deep file reads
│   ├── H1 optional: local dense index + hybrid ranking
│   └── H1/H2 graph RAG: only if Bright gold tests prove a multi-hop/global need
│
├── STORE B: STUDENT EVIDENCE
│   ├── canonical: SQLite observations
│   │     student_id + objective_id + result
│   │     + provenance + activity/session + assessment semantics
│   ├── derived: skills/objective state
│   │     counts + recency + coverage + conservative confidence
│   ├── derived: session summaries
│   ├── H1 optional: globally fitted BKT
│   └── NEVER: transcript-derived memory authority
│
├── STORE C: CONCEPT RELATIONS
│   ├── canonical: authored markdown
│   ├── optional: compiled SQLite relation index
│   └── LLM extraction: suggestions only, never canonical writes
│
└── CLASSROOM CORE
    ├── I/O
    ├── clock
    ├── SQLite
    ├── safety
    ├── identity binding
    └── restart/failure containment
```

The decision matrix is therefore unequivocal:

**Build now:** SQLite FTS5 curriculum retrieval, durable evidence recall into Hermes, stricter evidence semantics, deterministic counts/recency state, per-student query isolation, authored concept relations.

**Evaluate next:** sqlite-vec for hybrid local retrieval, pyBKT on pooled/synthetic sparse data, nano-graphrag to understand when graph retrieval actually adds value.

**Reconsider later:** LightRAG or HippoRAG for a genuinely large, cross-subject curriculum whose measured queries require associative/global reasoning; BKT after data volume and skill semantics stabilize; Elo after stable repeated item difficulty becomes estimable.

**Never under the locked doctrine:** Letta as runtime, Mem0 as learner-memory authority, Graphiti as student evidence store, DKT as an H0/H1 production dependency, auto-extracted concept edges silently entering canonical curriculum, raw child chat/transcripts as memory, or a unified GraphRAG over curriculum + children + concepts.

The core design principle is simple:

> **Hermes should remember students through evidence, and understand curriculum by reading it.**
>
> Store A should feel like a repo. Store B should feel like an auditable learner model. Store C should feel like authored domain knowledge. None of them should feel like a chat-history database.

That separation is what lets Bright scale from two units to many subjects, and from one learner to forty children, without turning Classroom Core into a lesson engine or introducing a second artificial teacher.