# 2026-08-18 — docs consolidated to one bible + one living doc

**Trigger:** owner review. "docs organize cũng ko tốt, nên xóa bớt clean để bắt
đầu lại cho đúng" — plus a restatement of the north star: the teacher is an
autonomous agent with a large library, the same shape as a coding agent in a
repo.

## What was wrong

45 markdown files. Of those, **13 were declared dead by other docs** — 6 by
`docs/README.md`, 7 more by `HANDOFF.md` §0 — while still sitting beside living
ones. Worse than the count:

- **Four files claimed to be the current status simultaneously:** `HANDOFF.md`,
  `autonomous-classroom-roadmap.md`, `teacher-agent-status.md`, `tracker.md`.
- **Three described the interaction contract**, two written the same day and
  contradicting each other. `classroom-is-the-room.md` was marked
  "HALF-SUPERSEDED" *on the day it was created*.
- **The bible had drifted.** `north-star.md` NS-3 still listed the tool set as
  `present` / `open_response`. The live surface has been eight different tools
  since Layer 1 closed. An agent reading the bible would have built to a dead
  contract.
- Numbered title prefixes (`# 01 —`, `# 03 —`, `# 06 —`) referred to an ordering
  that no longer existed, and two files both claimed `03`.

## What changed

```
docs/
  NORTH-STAR.md    the bible — corrected, rarely changes
  STATE.md         NEW. the only living execution doc
  decisions/       append-only, dated, one choice per file
  design/          how the machine fits together
  research/        evidence, not doctrine
  journals/        what happened and what it cost
  archive/         13 superseded files + a README saying what each is wrong about
```

- `1-vision/` `2-decisions/` `3-design/` `4-build/` `5-research/` → flattened.
  The numeric prefixes implied a reading order nobody followed.
- `STATE.md` absorbs `HANDOFF.md` + `autonomous-classroom-roadmap.md` +
  `teacher-agent-status.md`. All three archived.
- Two decisions written from corrections that were living only in a handoff
  paste: [`2026-08-18-room-runs-itself.md`](../decisions/2026-08-18-room-runs-itself.md)
  and [`2026-08-18-three-stores.md`](../decisions/2026-08-18-three-stores.md).
- Stale-but-valid decisions got dated **correction banners** rather than edits.
  `decisions/` is append-only; a reversal is a new file.
- All 70 files carrying a doc path were rewritten. Link check: 0 broken.

## The storage research, resolved

`research/external/Storage, Memory, and Retrieval for Bright.md` (57 KB)
was read in full and turned into a decision. Its verdict — three stores, kill
GraphRAG / Mem0 / Letta / Graphiti / BKT / DKT / Elo — **confirms the 2026-08-17
lock rather than opening a direction.** Its real value is the kill-gates and the
privacy findings.

Two of its claims are stale against the code and were flagged so nobody acts on
them:

1. *"Hermes mainly sees the current-session RAM snapshot; wiring persisted
   recall in is the most important immediate change."* — already done.
   `_session_recall()` reads every observation for the learner across all
   sessions.
2. *"`memories_fts` can remain for curated summaries"* — it exists in `db.py`
   but nothing in the teacher loop calls it. Dead code, not a capability.

FTS5 was **deferred** against the research's own recommendation, using the
research's own rule: trigger on a measured retrieval failure, not a file count.

## The finding that matters more than any of this

The case for running an agent harness is *"there is a large library and the
teacher finds her own way through it."*

`content/library/` is **8 files, 1,777 words, 2 units, 5 vocabulary words, 18
media files** — smaller than `content/README.md`.

The architecture is right. The library is the gap, and no retrieval work
substitutes for it.

## Lesson

One living document, or you get four. Every "temporary status file" written to
unblock one session became a competing authority within two days, and agents
read the wrong one. Archive on the day a doc stops being true, not later.

---

## Same day, later — the north star sharpened

Owner restated the target: *"an autonomous teacher agent, like a real human —
sees a person and greets them, knows when class is, prepares beforehand… like a
robot, but an agent."* Plus: don't bias toward 1:1, English is the first subject
but the architecture must be general first, and *don't forget skills*.

Three subagents were sent to establish facts before doctrine was written.

**What they found that changed the picture:**

1. **Autonomy is one function call away, not a project.** The pulse loop already
   runs unconditionally on every Core boot (`app.py:686-688`), every 10 s, and
   already refuses to spend a model turn unless the room is genuinely quiet. The
   Stage already announces presence by itself (`BusProvider.tsx:41-58`). The only
   thing missing is that `start_teacher_session()` has exactly one caller — the
   `Start class` button.

2. **A day-clock socket exists and is empty.** `scheduler.py:108-114` runs a
   nightly `prepare_next` cron that calls a hook defaulting to a **no-op**
   (`agent_bridge.py:43-45`). Someone built the hook and never filled it.

3. **Hermes has a real skills system — and our profile amputates it.** Genuine
   two-tier progressive disclosure (`prompt_builder.py:1664`, `skills_tool.py:789/1057`),
   `SKILL.md` + frontmatter, per-profile allow/deny. Our live classroom profile
   pins the entire system prompt and exposes only the 8 classroom MCP tools, so
   none of it is reachable. Decision: **copy the design, keep skills in the
   library** — NS-4 says the profession must survive swapping the runtime.

4. **Hermes never self-wakes.** Its "heartbeat" is cron-ticker liveness
   telemetry, not an agent trigger. Every turn needs an external caller. Our own
   Core-side pulse is the wake mechanism, and that is correct — Core owns the
   clock.

5. **The teammate's face component is good and separable.** YuNet + SFace,
   OpenCV Zoo, CPU-only, ~470 lines behind a small protocol. Embeddings only,
   never photographs; consent enforced by the schema; embeddings scoped to a
   hash of the weights file so a retired model cannot cross-match. Their
   threshold is uncalibrated and they say so — their own 59/100 self-assessment
   is the best artifact in that repo.

**The finding that cost the most to admit:** the 1:1 assumption is in the
**tool contract**, not just in variables. `record_evidence(objective_id,
outcome, mode)` has no subject — Core supplies the only learner there is. That
does not become multi-learner by adding rows to a table, and every unit authored
before it changes is written for the wrong classroom.

**Added to the bible:** §1 *Her anatomy*; §2 *The working day* (three clocks,
process-not-function, what she knows about a child, where she is up to); §3 *The
class is the unit* and *Identity is the system's job*; NS-6 *the profession is
data, not code* with the four layers of authored knowledge and the generality
test; NS-7 *the deployment declares itself*; a hard definition of what
"personalised" may and may not mean.

**Lesson:** three parallel readers produced five corrections to things this
session was about to write from memory. Doctrine written from recollection is
how the bible ended up listing tools that had not existed for a week.

---

## Same day, evening — the cassette is deleted

Owner: *"xoá sạch hardcoded cassette"* — delete it, do not gate it.

**The structural finding that justified it.** `app.py` constructed a
`LessonRunner` + `ClassSessionController` whenever `lesson_run_path` pointed at a
file that existed — and `sample_lesson_run.json` existed. Both held
`core.publish_speech` and wrote to the same bus and store as the teacher agent.
`BRIGHT_AGENT` was read only inside `bright_agent/hermes.py`; it gated the
*adapter*, never Core.

So the running system had **two teachers loaded, one process, one loudspeaker**,
and the only thing deciding whether the second one was live was whether a JSON
file happened to be on disk. Not a visible bug — two systems holding the wheel,
not yet pressing the pedal at the same time.

~9,000 lines removed across Core, tests, tools, scripts and the UI. `app.py`
1,600 → 1,053.

**What the frontend map found that the backend audit had not.** Three mic
instantiations (`/learn`, `RoomDock`, `/control` VoicePanel), **two structurally
different ways to submit student speech** (`student.speech.final` over WS with a
server-issued assignment, versus a bare `POST /teacher/turn`), and three audio
output surfaces — including a raw `<audio>` element in `/learn` that bypassed
AIRI entirely. `/learn` also opened a class **merely by being loaded in a browser
tab**.

The AIRI chain itself was clean: `AvatarLayer` mounts once and does not read
`scene`, so `scene.update` cannot remount Live2D; `mouthOpen` runs one path from
the played buffer to `ParamMouthOpenY`; no SVG fallback survives.

**Two things the delete broke that were not cassette**, both caught by the
subagent's own honesty rather than by tests:

1. `build_agent_seam` lived in `agent_bridge.py` and supplied the health probe
   that drives `ModeController`. Losing it pinned mode to OFFLINE forever.
   Restored as a sidecar latency probe.
2. My own extraction of `CapabilityLeaseRegistry` into `leases.py` was
   incomplete — it referenced `secrets`, `AssignmentRejected` and `SessionState`
   without importing any of them. **It could never have run.** The agent found
   and completed it.

The second is the more useful lesson: I extracted a class by line range and did
not import-check the result. `python -c "import leases"` would have caught it in
one second, and I did run it — but only far enough to construct the registry,
which does not touch the missing names.

**Kept against the instruction, deliberately:** `bright_agent/direct.py`. It is
unreachable from Core, but the SP-3 model-evaluation suite is built on it — the
NS-4 asset that tells us which models are usable. Deleting the cassette should
not delete the measurements.
