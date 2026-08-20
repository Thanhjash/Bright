# Where the data is

Three stores, three kinds of truth, and no fourth
([decision](../decisions/2026-08-18-three-stores.md)). This file says where each
one physically lives, what writes it, and how any of it reaches the teacher.

If you remember one thing: **the curriculum is markdown on disk and the child's
record is SQLite. Neither one is a chat log.**

```
content/library/          A — what to teach          markdown, read like a repo
data/bright.db            B — what a child did       SQLite, an auditable mark book
data/faces.db             C — whose face is whose    SQLite, embeddings only
```

---

## A — the curriculum. Markdown. No database.

```
content/
  library/
    index.md                        the deployment declares itself: three languages,
                                    the unit table, the timetable
    how-to-teach.md                 who she is in the room
    skills/index.md                 the 11 procedures and when to open each
    skills/<name>/SKILL.md          one procedure. YAML front-matter: name,
                                    description, when, version
    units/gs3-u1-hello/
      map.md        the syllabus — objectives, locked language, the three periods,
                    the school-language arrival and rescue lines, pacing
      keys.md       what counts as correct / near / wrong / uncertain
      practice.md   other ways to run an activity when the room is not cooperating
      exercises.md  literal `show_exercise` payloads, per period
  media/
    gs3/{pages,panels,audio}        the textbook. gitignored — third-party
    colours/ market/ stage/         samples and the room's own artwork
```

**There is exactly one unit today**, and that is the honest limit of the whole
system, not a detail. Until 2026-08-21 it was also a hard limit in code:
`_open_on_presence` refused to open a class at all unless exactly one unit was
authored, because Core must never pick a favourite lesson (NS-7). The front door
is what unblocks a second unit — a human chooses, so Core does not have to.

Things worth knowing before you edit any of it:

| | |
|---|---|
| Units are found by **scanning `units/*/`** (`library.py:103`), not by reading the index | the index↔disk agreement is enforced by a test, never at runtime |
| Objective ids are parsed by **one regex** (`library.py:99`) — `- id: \`greet-and-name\` — …` | `record_evidence` refuses an id that is not in the unit, fail-closed |
| `asset://x/y.png` → `content/media/x/y.png` (`teacher_os.py:314`) | served by `GET /assets/{path}`; the `asset://` prefix is part of the id, and stripping it once cost a whole lesson its board |
| Skills are **portable**, units are **the deployment** | a test (`test_library.py`) fails the build if a skill file names a language or a subject. Unit files may — that is where the Vietnamese arrival lines live |
| Reads are sandboxed to `.md` under `LIBRARY_ROOT`, capped at 8000 chars | `library.py:20-39` |

## B — the child's record. SQLite at `data/bright.db`.

Created by the `MIGRATIONS` list in `services/classroom-core/db.py`, applied on
every boot.

| table | one row is | written by |
|---|---|---|
| `sessions` | **one period.** `lesson_id` is the unit id | opened at session start; `ended_at` set when she calls `say(closing=true)` |
| `observations` | one piece of evidence | `record_evidence` — objective id, outcome, mode, and the real turn id |
| `memories_fts` | the searchable text of the above | mirrored on every observation; this is what `recall_student` queries |
| `lesson_plans` | her own plan for a session | the `plan` tool. Core never branches on its contents |
| `students` | a learner | `upsert_student`, at session start — and, since enrolment exists, at the moment consent is given |
| `skills`, `session_checkpoints`, `session_participants` | — | **nothing. Dead tables** left by the deleted cassette runtime |

Two facts that surprise people:

- **`PERIODS_HELD` is a `COUNT(*)`** of *ended* sessions for this learner and
  unit (`db.py:394`). Core counts; it never looks up what the number means. The
  front door renders from the same number, which is why a card and the class it
  opens cannot disagree.
- **Board state is not persisted at all.** The writing, images, clip and
  exercise live on the in-memory `TeacherOS` and are gone on restart. An
  interrupted period resumes with its plan and its evidence, not its board.

## C — faces. A separate SQLite at `data/faces.db`.

Beside the classroom database, never inside it.

```sql
subjects(subject_id PK, display_name, consent_reference NOT NULL, created_at, updated_at)
face_embeddings(embedding_id PK, subject_id → subjects ON DELETE CASCADE,
                model_id, dimension, embedding BLOB, created_at)
```

- **Embeddings only. No photograph is ever written to disk.** The frame exists
  in memory for one call.
- `consent_reference` is `NOT NULL` in the schema and `consent_confirmed:
  Literal[True]` is in the request *type*, so a request without consent is
  rejected by validation before any logic runs.
- `model_id` carries a hash of the recogniser weights, so embeddings made by a
  retired model can never silently cross-match against a new one.
- `ON DELETE CASCADE` means deleting a child deletes their biometrics.

**The id is Core's.** `students.id` and `subjects.subject_id` are the same
string, and nothing in SQL enforces that — so enrolment goes through
`POST /teacher/enroll` on Core, which mints the id and hands vision the same
one. A browser minting its own would produce two unrelated children with one
face, silently.

---

## How any of it reaches the teacher

She is stateless between turns (`store: false`), so everything she knows arrives
on the turn. `_session_recall` (`teacher_os.py:1342`) assembles it and
`hermes.py:249` renders it as `KEY=value` lines.

| block | from |
|---|---|
| `ASSETS=`, `OBJECTIVES=` | **library** — scraped off the unit's markdown |
| `PERIODS_HELD=`, `SKILL_CARD=`, `PAST=`, `PLAN=` | **DB** — `sessions`, `observations`, `lesson_plans` |
| `THIS_PERIOD=`, `BOARD=`, `USED_SO_FAR=`, `ANSWERED_IN=`, `NO_REPLY=`, `LAST_SAY=` | **runtime** — this period, in memory |
| `READ_NOW=` | Core naming **at most two** library paths per turn (`hermes.py:435`) |

`READ_NOW` is the interesting one, and the reason for a bug that lasted weeks.
It names paths; she then calls `read_library` herself. Two per turn, because
naming four on the opening turn spent the whole tool budget on reading and the
class heard silence. The consequence: **a file that is never named is a file she
never reads.** `index.md` — the only file that says which language is which —
was never in that list, `how-to-teach.md:19` told her to go read it anyway, and
across a whole measured period she opened 13 files and that was not one of them.
That is why 110 consecutive TTS calls came out English. The fix was to put the
words where she already reads: in the unit map.

The twelve tools split cleanly along the three stores:

| reads the library | reads the DB | changes the room | neither |
|---|---|---|---|
| `read_library`, `search_library` | `recall_student` | `write_board`, `show_image`, `show_exercise`, `play_clip`, `say` | `read_board` |
| — | `plan`, `record_evidence` (writes) | — | `call_the_adult` |

`record_evidence` reads the library *and* writes the DB, and that is deliberate:
it validates the objective id against the unit before it writes, fail-closed.

## What we deliberately do not build

From [three-stores](../decisions/2026-08-18-three-stores.md), each with the gate
that would reopen it: GraphRAG, LightRAG, HippoRAG, an auto-generated knowledge
graph, Mem0, Letta, Graphiti, Elo, BKT, DKT. FTS5 over the *library* is deferred
until it fails a retrieval benchmark, not until it reaches a file count.

The uncomfortable version, still true: the case for running an agent harness is
that there is a large library and the teacher finds her own way through it.
Today that library is one unit. **No storage architecture fixes that.**
