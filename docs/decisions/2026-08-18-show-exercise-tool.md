# Decision: a ninth MCP tool — `show_exercise(kind, content)`

**Date:** 2026-08-18
**Status:** LOCKED
**Governed by:** [NORTH-STAR.md](../NORTH-STAR.md) NS-3 (semantics, never the DOM), NS-6 (general first)
**Related:** [tool-surface.md](../design/tool-surface.md) §8 (migration checklist),
[STATE.md](../STATE.md) §*The eight live tools* ("do not add a ninth without a decision doc")

---

## The decision in one sentence

> `show_exercise` reaches three boards that already exist and are already
> routed — `choice`, `vocabulary`, `roleplay` — and reaches nothing else.
> Core validates structure only; it never judges whether an answer is
> pedagogically right, and it never emits which child chose what.

Before this change, `TeacherOS._push_stage()` could only put `text` or a
single `image` on the board. Seven exercise boards under
`apps/classroom-ui/src/stage/BoardLayer/` were fully written and routed by
`SceneRouter.tsx`, and structurally unreachable from any tool. `show_exercise`
reaches three of them; `show_image(left, right)` is separately fixed (same
change set) to route a pair through the `vocabulary` scene instead of
inventing a fourth path.

---

## Why exactly these three, and not the other four

`docs/design/tool-surface.md` proposed an eleven-tool surface and left the
practice/assessment side open pending research. That research
([2026-08-18-evidence-and-practice.md](2026-08-18-evidence-and-practice.md))
has since landed. Of the seven exercise scenes on the wire, three are usable
today with no further design work; four are not, for reasons specific to
each — not a general "we'll get to it":

| Rejected `kind` | Why not now |
|---|---|
| `matching` | Grading is pairwise (`solved: Array<[string,string]>`) and needs a drag-drop interaction contract Core does not yet validate. Adding it here would smuggle an ungraded interaction model in through a tool meant to be structure-only. |
| `sentence_builder` | Token placement order is itself the answer key. Validating "is this a legal partial sentence" is a grammar problem, not a shape problem — it does not fit the "Core validates structure only" rule this tool is built around. |
| `pronunciation` | NS (`tool-surface.md` §7): "no pronunciation percentages before calibration." The scene's own props (`phonemes: [{symbol, status}]`) are a per-phoneme verdict — exactly the graded-board problem this tool exists to avoid, before ASR confidence is calibrated for it. |
| `explore` | This is the EXPLORE mode from the north star (`penguin → Antarctica → ice → ocean → climate`) and deserves its own tool (`tool-surface.md` §4.1, `show_video`/`highlight`), not a fourth `kind` bolted onto a schema built for closed-set exercises. Folding it in here would blur "an exercise with a correct answer" and "an open-ended world to look at." |

`choice`, `vocabulary`, and `roleplay` share a property none of the four
above have: their scene props are fully determined by the tool's input, and
their correctness (if any) is a set-membership check Core can do without
knowing anything about English. That is the actual boundary, not "the first
three we got to."

**Scope is locked at exactly `{"choice", "vocabulary", "roleplay"}`.** A
future kind needs its own decision doc, not an edit to the enum.

---

## Core validates structure only

Per the twelve invariants (`docs/design/teaching-loop.md` §4, #6 and #7), the
board never grades and evidence is Core's separate, private channel. So
`show_exercise` validation is entirely shape-level:

- `choice`: prompt length, 2–4 options, unique ids, at least one of
  text/asset per option, every `asset` resolved through the existing
  `_as_asset`/`_media_file` helpers, `correct_id` must equal one option's id.
  Core never asks whether `correct_id` is the *pedagogically* correct choice
  — that is the agent's judgement, and `tests/test_no_unit_pedagogy.py`
  forbids curriculum truth from living in Core.
- `vocabulary`: 2–8 items, same id/text/asset rules, `highlight_id` must
  match an item id. `interaction` is force-set to `"none"` regardless of
  what the agent sends, because rejecting it would burn one of the turn's 8
  tool iterations for a non-mistake.
- `roleplay`: environment/ai_role/student_role length bounds, 1–5 target
  phrases with a length bound each.
- Every free-text field runs through the same non-evaluative / no-HTML /
  no-URL check `write_board` already uses (`_check_teacher_line`, now
  factored into `_check_free_text` so it is reused rather than
  reimplemented per field). These strings land on the same projected board;
  the ban on `✓` / "correct" / "well done" does not stop applying because the
  tool name changed.

## Core never emits `chosenId`

`ChoiceProps.revealed` has an optional `chosenId`, and `ChoiceBoard.tsx`
renders it as a red cross with `aria-label="not correct"` on whatever the
child picked — a grade on the shared board, which invariant 6 forbids and
which `content/library/skills/judge-a-response/SKILL.md` states outright:
never correct one child in front of the others. The component predates this
doctrine; the tool that drives it does not repeat the mistake.

`chosenId` is not in the `show_exercise` schema, so it cannot reach the wire
through this path at all. The agent may set `content.reveal = true`; Core
then publishes `revealed: {"correctId": ...}` and nothing else. The mint tick
on the correct option stays — showing what is *true* is the board holding the
language; painting what *this child* got wrong is not.
`test_show_exercise_never_emits_chosen_id` in
`services/classroom-core/tests/test_teacher_os.py` asserts the key is
**absent** from the published scene, not merely `None`.

## `show_image(left, right)` — the same migration, no new component

`show_image`'s two-asset path built `last_present = {"layout": "two_cards",
...}` and returned `ok: true`, but `_push_stage` only ever read
`last_images` into a single-asset `image` scene — `ImageProps` has no pair
shape on the wire, so the second asset was silently dropped before this
change. It now routes through the already-wired `vocabulary` scene:
`{"items": [{"id":"left","asset":…},{"id":"right","asset":…}],
"interaction":"none"}`. No contract change, no new component.

`_push_stage` now has three possible sources instead of two, in priority
order: an exercise (`last_exercise`), then images, then plain writing —
mirroring the existing `last_writing`/`last_images`/`last_clip` pattern with
a fourth field, `last_exercise = {"kind", "content", "revealed"}`.

## Every layer that had to move together

Checked against `docs/design/tool-surface.md` §8:

1. `services/classroom-core/mcp_server.py` — `TOOLS` gains `show_exercise`;
   `record_evidence` gains required `student_id`.
2. `services/classroom-core/teacher_os.py` — `execute()` gains the
   `show_exercise` branch and validation helpers; `_push_stage` gains the
   exercise/images/writing priority order; `read_board` and
   `_session_recall` report the exercise and `student_id`.
3. `services/agent/bright_agent/hermes.py` — `TEACHER_TOOLS` gains
   `show_exercise`; `render_teacher_turn` gains `STUDENT_ID=` and
   `EXERCISE=` lines.
4. `infra/hermes/config.yaml` — both `tools.include` and the tool list
   inside `system_prompt` (nothing scans that string).
5. `infra/hermes/patches/0002-teacher-multi-tool.patch` — the keep-filter's
   hardcoded tool-name tuple gains `show_exercise`; patch version bumped to
   `0.20.0+bright.4` per the file's own convention, `manifest.json` updated
   to match.
6. `packages/contracts/PROTOCOL.md` §9.12 — documents that Core never sends
   `chosenId`.
7. This file.

## `record_evidence` gains `student_id` (same change set)

This travels with `show_exercise` because both touch `teacher_os.py`'s
`execute()` and both are part of tightening the evidence contract. Per
`tool-surface.md` §6, `record_evidence` was always meant to gain a subject;
it is now **required**, and Core refuses — writing no row at all — when it is
missing, a case-insensitive class-wide placeholder (`class`, `everyone`,
`choral`, `all`), or (while exactly one learner exists) anything other than
`TeacherOS.learner_id`. The rendered turn now carries `STUDENT_ID=` next to
`TURN_ID=`, and `content/library/how-to-teach.md`'s Evidence section carries
the natural-language mirror: a choral or unattributable response gets no
`record_evidence` call at all.

The confidence number `_name_skill_stats` computed (`min(1.0, (total // 2) /
4)`, saturating after four attempts regardless of correctness) is deleted —
verified dead on the live path, since `SKILL_CARD` comes from
`format_skill_memory` reading raw observations, not the `skills` table.
`format_skill_memory` now reports coverage instead: `supported` /
`contradicted` / `no_decision` counts per (skill, elicitation mode), mapping
`correct → supported`, `wrong → contradicted`, `uncertain|near →
no_decision`. `Database.update_skill` itself is kept —
`services/classroom-core/scheduler.py` still calls it from a real LLM
estimate in `summarize_session`, which is a legitimate caller this change
does not touch.
