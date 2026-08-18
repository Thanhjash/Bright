# Decision: three stores, three kinds of truth — and no fourth

**Date:** 2026-08-18
**Status:** LOCKED
**Extends:** [layer-1-memory-is-enough.md](layer-1-memory-is-enough.md) (2026-08-17)
**Source:** *Storage, Memory, and Retrieval for Bright* — commissioned deep research, 2026-08-17. **The source file was overwritten on 2026-08-18 and is lost** ([why](../research/external/README.md)). Its conclusions, its kill-list gates and the two corrections against the code are all preserved in this document.
**Authority:** [NORTH-STAR.md](../NORTH-STAR.md) NS-5

---

## The decision in one line

> **Hermes remembers students through evidence, and understands curriculum by reading it.**

Three stores, deliberately different, never merged:

| Store | Canonical truth | Retrieval today | Never |
|---|---|---|---|
| **A — Curriculum** | markdown + `asset://` media in `content/library/` | catalog + `search_library` + deep `read_library` | a second copy an author edits; an auto-extracted graph |
| **B — Student evidence** | SQLite `observations` rows | exact `student_id` scope → objective → recency | transcript-derived memory; a model's impression becoming a fact |
| **C — Concept relations** | authored markdown (`keys.md`, unit maps) | direct read | LLM-generated edges written without an author |

Store A works like a repo: the index is disposable, the files are truth.
Store B works like an auditable mark book. Store C works like authored domain
knowledge. **None of them is a chat-history database.**

---

## What the research changed, and what it only confirmed

The deep research was commissioned to ask whether Bright needs GraphRAG, a
memory platform, or knowledge tracing. Its verdict matches the 2026-08-17 lock
almost exactly. That is a useful result — it means the lock was right — but it
means the research's value is *kill-gates and privacy warnings*, not a new
direction.

Two claims in the research are **out of date against the code** and must not be
acted on:

| Research claim | Reality in the tree (2026-08-18) |
|---|---|
| "Bright already has durable evidence but Hermes mainly sees the current-session RAM snapshot. Wiring persisted recall into the turn is the most important immediate change." | **Already done.** `teacher_os._session_recall()` calls `db.list_observations(student_id=…)` — every observation for that learner, across all sessions — and `format_skill_memory()` compacts it into `SKILL_CARD` + `PAST`. Do not rebuild this. |
| "`memories_fts` can remain for curated evidence-derived summaries." | It exists in `db.py` but **nothing in the teacher loop calls it**. It is dead code, not a feature. Either delete it or leave it unused — do not treat it as a shipped capability. |

---

## What we adopt now (H0)

### 1. Better evidence ontology beats a better estimator

This is the single most valuable line in the research, and it is the one thing
we have *not* done.

Today `record_evidence` carries `mode ∈ {name, point, ask}`. That distinguishes
receptive from productive, which is the important half. It does **not**
distinguish:

- **prompted** vs **independent** response
- **assessment** vs **teaching exposure**
- **novel context** vs the same picture asked again

A teacher who asks "point at yellow" and records it as "names yellow" has not
made a statistical error. It has made a **measurement-validity error**, and no
estimator can repair it.

Add the categorical context. Do not add an estimator.

### 2. Stop overstating a sample of four

`teacher_os._name_skill_stats()` computes:

```python
confidence = min(1.0, (total // 2) / 4)
```

Four attempts therefore yields confidence `1.0`. That is exactly the failure the
research warns about. Confidence must express **evidence coverage**, not
certainty — and it must stay visibly short of 1.0 at this sample size.

### 3. Identity scope before ranking — and prove it

The invariant:

> **No retrieval may rank across students and filter afterward. Exact
> `student_id` scope comes first, relevance second.**

The code already obeys this. There is **no test that would catch a regression**.
Add an adversarial one: two learners with near-identical objective histories and
opposite outcomes; a query for A must return zero rows of B even when B is the
better textual match. This is also the cleanest child-data-safety evidence we
can show a judge.

### 4. Every derived thing must be rebuildable

Skills, session summaries, any future index: deletable and reconstructible from
`observations` + markdown. Markdown and observations survive an index failure.
On donated hardware that property is worth more than retrieval score.

---

## What we do NOT build (kill list)

Each of these is killed **now**, with the gate that would reopen it.

| Candidate | Verdict | Gate to reconsider |
|---|---|---|
| Microsoft GraphRAG | **KILL** | ≥20% of gold queries are genuinely global/multi-hop **and** GraphRAG beats hybrid on them |
| LightRAG | KILL now | ≥10pp gain on the hard-query subset over hybrid, with fast incremental edits |
| HippoRAG | KILL now | repeated measured multi-hop prerequisite failures |
| Auto-generated KG as Store C | **NEVER** | author review of every edge, promoted through markdown only |
| Mem0 as student-memory authority | **NEVER** | violates NS-5: it treats agent-generated facts as first-class memories |
| Letta | **NEVER** | Bright has one brain. A second stateful-agent runtime contradicts it |
| Graphiti as Store B | **NEVER** | student evidence already has exact ids and timestamps; extraction adds uncertainty where none exists |
| Elo | KILL now | stable reusable item ids + enough population data for difficulty to be estimable |
| BKT (fitting) | KILL now | ~200 valid pooled responses from ≥30 learners, consistent task semantics, out-of-sample stability |
| DKT / pyKT in production | **NEVER foreseeable** | large clean corpus, no leakage, real gain over BKT on CPU |
| Dense vectors for Store A | LATER | see the retrieval gate below |
| SQLite FTS5 for Store A | **LATER, not now** | see below |

### Why FTS5 is deferred even though it is cheap

The research recommends FTS5 for Store A "this month". We are deferring it, and
the research's own rule is why:

> Trigger dense/indexed retrieval on **a failed retrieval benchmark**, not on a
> file count.

`content/library/` is 8 files and 1,777 words. `search_library()` is a naive
token-count scan of every markdown file. At this size it does not fail. Where it
*will* fail is ranking quality — raw token counts favour long files, and hits
are returned at file granularity, so the agent then reads a whole file into
context.

**The gate:** build the retrieval gold set (50–100 real teacher lookups) when
the library passes roughly 40–50 files or two subjects, whichever comes first.
If lexical Recall@5 drops below ~90%, index headings into FTS5 with weighted
columns. `sqlite-vec` is the only dense candidate worth qualifying after that,
and only on the real target hardware — it is pre-v1.

Building the index before the library exists optimises the wrong layer.

---

## Privacy consequences that are now binding

- **Embeddings are not anonymisation.** Dense representations of child evidence
  are sensitive data. If we ever embed Store B, it inherits every rule that
  applies to the rows.
- Hosted models see an opaque `student_id` plus pedagogically necessary
  evidence. Never a real name, never prior raw utterances.
- Deleting a learner must delete derived representations and caches, not only
  the rows a query can see.
- Camera identity (Layer 5) answers exactly one question: *which existing
  `student_id` is this?* Uncertain identity means **no student-memory write**.

---

## The uncomfortable finding this analysis surfaced

The whole case for running an agent harness is: *there is a large library, and
the teacher finds her own way through it.* Today that library is 8 markdown
files, 2 units, 5 vocabulary words, and 18 media files.

**No storage architecture fixes that.** Store A's retrieval quality is not the
bottleneck — Store A's *contents* are. Curriculum depth is the highest-value
work available, and it needs no new dependency, no new schema, and no code.

See [STATE.md](../STATE.md) for where that sits in the order of work.
