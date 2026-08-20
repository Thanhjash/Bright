# Decision: the room knows who, and she can ask what she was told

**Date:** 2026-08-20 · **Status:** adopted

## The decision in one line

Perception resolves a `student_id` before the class opens; Core auto-loads that
child's **overview** into every turn; and a twelfth tool lets her look **deeper
into that child's own record** when the overview is not enough.

## Why identity had to move first

`_open_on_presence` opened every session for the deployment's declared learner.
With one child in the room that was invisible. With two it is the failure
NORTH-STAR names as the expensive one: *"Attributing a child's failure to a
different child"*.

`services/vision` (:8002) answers exactly one question — *which existing
student_id is this, and how sure are we* — and `perception.py` is Core's view
of it. What crosses that boundary is an id and a number. **Core never sees a
face, an image or an embedding, and the teacher does not even get the number.**

Four situations collapse to one answer, and that is the point:

| the camera sees | answer |
|---|---|
| nobody enrolled matches | `None` |
| a match below threshold | `None` |
| **two** confident faces | `None` |
| exactly one confident face | that `student_id` |

`None` means the room uses the declared learner and writes no child's memory.
The two-face case is deliberate: a child sitting beside a classmate must not
become that classmate, and taking the higher score would be the misattribution
the rule forbids. An identity also expires (`VISION_IDENTITY_TTL_S`, 15 min) —
a child does not become another child mid-period, but this morning's answer
must not open a session for someone who has gone home.

## The overview was already there. The hand was not.

`_session_recall` has always injected two things for the session's learner:

```
SKILL_CARD=greet-and-name name supported=2 contradicted=1 no_decision=0; …
PAST=2026-08-19 greet-and-name name correct; 2026-08-20 answer-wellbeing name wrong; …
```

Coverage per (objective, mode), and the last eight observations. That is the
**overview**, it is computed from `observations`, and it is honest — counts of
what was witnessed, never a confidence score, never a raw child word (NS-5).

What did not exist was a way to go further. `db.recall()` — FTS5 over
`memories_fts`, bm25 re-weighted by recency, filterable by `student_id` and by
tier — has been in the codebase for days, reachable from a dev HTTP route and
from nothing she can call. A memory the teacher cannot query is a memory the
teacher does not have.

## The twelfth tool

`docs/STATE.md` says a twelfth tool needs a decision doc. This is it.

```
recall_student(query, limit?)   → past notes about THIS learner, most useful first
```

- **Scoped to the session's learner in Core, not by an argument.** She cannot
  ask about another child, because the id is not hers to supply. This is the
  same shape as `record_evidence`, which refuses a `student_id` that is not the
  learner in the room.
- **Read-only.** It cannot write, cannot grade, cannot change the board.
- **Returns what Core wrote:** session summaries and observation lines, both
  already categorical. No raw child speech is in `memories_fts` to return.
- **Empty is a normal answer**, not an error: a child on their first day has no
  past, and she must be able to teach them anyway.

### Why a tool and not more injection

Injecting more of the record on every turn was tried in a neighbouring case and
measured worse: orientation injection cost ~2,400 tokens on *every* call and
bought one round-trip back on the first turn only, because this provider
reports `cached_tokens: 0` (see the comment above `format_skill_memory`). The
overview is small and always relevant; the rest is large and rarely relevant.
That is exactly the shape that should be a lookup.

### Why not extend `search_library`

`search_library` searches the **curriculum**, which is the same for every child
in every school. This searches **one child's record**. Merging them would put a
learner's history behind the same call as a unit map and make "what may this
return" impossible to answer at a glance.

## The accretion tripwire still holds

`say` is untouched. The new tool is a look-up beside `read_library` and
`search_library`, in the LOOK UP group, and it carries no content, no
`asset://`, and nothing that can change the room.

## What this does not do

- It does not make the room multi-learner. A session still holds one
  `learner_id`; perception now chooses **which** one instead of always the
  default. A class of thirty needs a roster, and that is its own work.
- It does not enrol anyone. Enrolment is a deliberate consented act on the
  adult console, never on the projector, and never inferred during a lesson.
- It does not give her a face, a name to match, or a similarity score. She gets
  an id, and through it what was recorded.
