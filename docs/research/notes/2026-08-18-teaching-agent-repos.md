# Two teaching-agent repos, read in full

**Date:** 2026-08-18
**Repos:** `references/teaching-agent` (LiaScript/teaching-agent) · `references/Multi-Agent-Study-Assistant` (A-R007)
**Status:** evidence. Nothing here is doctrine until a `decisions/` file adopts it.
**Feeds:** [PROMPT-classroom-assessment.md](../prompts/PROMPT-classroom-assessment.md), [tool-surface.md](../../design/tool-surface.md)

---

## Verdict first

Neither repo is a system to adopt. **One markdown syntax and three process
patterns are worth taking; everything else is either a prompt library or a
cautionary example.**

| | teaching-agent | Multi-Agent-Study-Assistant |
|---|---|---|
| What it actually is | a **prompt-spec framework**, not a runtime. 23k lines of markdown, **one** Python file (317 lines) that concatenates templates | a runnable Streamlit demo, 1,319 lines of Python, six cloud LLM agents |
| Runs offline? | n/a — it runs inside someone else's coding CLI | **no.** OpenAI/Groq, OpenAI embeddings, DuckDuckGo search |
| Grades a learner response? | only in the external LiaScript viewer — exact/array match, client-side JS | **no grading code at all** |
| Models mastery? | no | no — despite the README |
| Licence | **Boost Software License 1.0** (permissive, MIT-like) | **none.** No `LICENSE` file. README says "available for educational purposes", which is not a grant |

> **Owner correction, 2026-08-18:** these are *reference only* — nothing is
> copied verbatim, so licence is not a concern here. The licence column stays as
> a fact, not a warning. It would only matter if we ever vendored code, and we
> are not going to.

**The rule that does matter: read for ideas, never for shape.** A reference repo
is allowed to answer *"has anyone solved X, and how?"* It is never allowed to
reshape the north star. Both of these were built for a different room — one
learner, one device, a keyboard, the internet — and adopting their structure
would quietly import that room into ours. Take a syntax, take a process pattern,
take a warning. Do not take an architecture.

---

## What is genuinely worth taking

### 1. LiaScript's quiz syntax — the answer to "how does a teacher author an item in plain markdown"

This is the single most valuable artifact across both repos, and it is exactly
the question NS-6 raises (`content/library/` must be authorable by a teacher with
no build step).

```markdown
Single choice          - [( )] Wrong
                       - [(X)] Correct

Multiple choice        - [[ ]] Wrong
                       - [[X]] Correct

Typed answer (cloze)   [[Beethoven]]

Open, ungraded         ?[Briefly explain why…]
```

Plus surveys (no correct answer): single/multi-line text, choice vectors, choice
matrices. A course header block sets metadata and the TTS voice; `##` starts a
slide; `{{n}}` / `--{{n}}--` separate what is *shown* from what is *spoken*.

Why it matters to us: a teacher can write a working item by typing a bulleted
list with `(X)` in it. No JSON, no YAML indentation trap, no compiler. That is
the bar our own item format has to beat or match.

**Not found in the repo:** matching, ordering, drag-and-drop, flashcards, spaced
repetition. The syntax covers less than we will need.

### 2. Mechanical vs pedagogical validation

Their content checklist tags each check as `[mechanical]` (safe for an automated
loop to fix) or `[pedagogical]` (**always escalate to a human**).

That line is directly reusable and it belongs in our content pipeline. A model
may fix a broken `asset://` id. A model may not decide that a scaffolding step is
good enough.

### 3. Bounded loop, escalate rather than spin

*"Repeat until the condition holds, or N iterations, whichever comes first. On
the cap, stop and report to the human."* We already do this in one place (the
Hermes patch caps a turn at 8 iterations). It should be the house rule everywhere
a small model is in a loop on cheap hardware.

### 4. Persona / prompt / domain-data separated into versioned YAML

Repo 2 keeps system prompts, task templates, and domain enumerations in one
teacher-editable YAML rather than hardcoded in Python. Structurally the same
instinct as NS-6. Worth copying the *shape*, not the file.

---

## What to avoid, and why it matters to us specifically

### Repo 2's "adaptive difficulty" is the exact failure our north star forbids

Their README advertises *"Adaptive Difficulty: Questions matched to your
knowledge level"* and *"Personalized Learning Style."* In the code, both are a
**single string chosen once from a dropdown and interpolated into one prompt**.
Nothing measures anything. Nothing updates. Their own architecture doc lists
adaptive difficulty under *future work*.

This is the cleanest available illustration of the thing NS forbids: **prompt-only
personalisation presented as adaptation.** It reads as a feature and produces
false confidence in an unmeasured "level". Our rule — every claim about a learner
traceable to a recorded observation — exists to prevent precisely this, and here
is a shipped product doing it.

Keep this repo as the example. It is more useful as a warning than as a source.

### LiaScript's *runtime* assumes one device per child

Its quizzes assume a browser, a keyboard, a mouse, and a private self-paced
learner clicking checkboxes. That is the opposite of our room. **Take the syntax;
do not take the interaction model.** How thirty children answer on one shared
screen is still unsolved and is the core question in
[the assessment research prompt](../prompts/PROMPT-classroom-assessment.md).

### Neither repo has a difficulty or spacing algorithm to learn from

Both punt it. We will design it ourselves, constrained by "no invented mastery
score" — most likely teacher-set difficulty tiers rather than model-inferred
ones.

### Repo 2's RAG stack does not survive our constraints

ChromaDB with **OpenAI cloud embeddings**, retrieval with no score threshold
(chunks are concatenated regardless of match quality), and a DuckDuckGo web
search agent. Every part assumes always-on internet and paid APIs. The chunking
defaults (1000 chars, 200 overlap) are a reasonable starting point if we ever
need local retrieval; nothing else transfers.

One detail worth noting as a bug pattern: their architecture doc claims the RAG
agent has the vector store *as a tool*. The code retrieves manually in Python
before the agent runs and never passes the knowledge base — so the documented
tool wiring is dead code. Docs describing a capability the code does not have is
a failure mode we have had ourselves.

---

## What this changes for Bright

Nothing is locked. Three things move from "unknown" to "known":

1. **A markdown item syntax that teachers can actually write exists**, is proven
   in the field, and is permissively licensed. Our format should be that or
   isomorphic to it.
2. **Nobody in this sample has solved answer capture for a shared screen.** It is
   genuinely open, not something we failed to look up.
3. **Neither repo is a dependency.** One is a prompt library; the other has no
   licence. Our own implementation stands.


---

## Addendum, 2026-08-18 — a licence "correction" that is not one

The classroom-assessment research states that our Boost 1.0 note is stale and
that LiaScript is BSD-3-Clause.

Both are right; they are **different repositories**.

| | |
|---|---|
| `LiaScript/teaching-agent` — the prompt-spec framework surveyed above | **Boost Software License 1.0**, verified in the clone on disk |
| `LiaScript/LiaScript` — the actual DSL implementation, which we have not cloned | **BSD-3-Clause**, per the research |

Nothing to fix here. Recorded so the line above is not "corrected" into being
wrong. If we ever vendor the DSL implementation itself, that is the BSD-3 one and
its licence must be pinned at the exact commit.
