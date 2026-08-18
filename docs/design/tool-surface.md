# The tool surface — what her hands must be able to do

**Date:** 2026-08-18
**Governed by:** [NORTH-STAR.md](../NORTH-STAR.md) NS-3 (semantics, never the DOM), NS-6 (general first)
**Status:** **NOT LOCKED — analysis and proposal only.**

> The owner's instruction (2026-08-18) is to settle the *general* shape first —
> north star, architecture, workflow — and lock the fine detail after research.
> This document therefore argues for a shape and names the gaps. **The specific
> eleven are a proposal, not a decision.** The assessment/practice side in
> particular is deliberately left open pending
> [the classroom-assessment research](../research/prompts/PROMPT-classroom-assessment.md).
>
> What *is* settled here: the five families, the rule that she is given verbs and
> never mechanisms, and §6 (`record_evidence` needs a subject) — which follows
> from the north star's 1:1 audit and does not depend on any research outcome.

---

## 1. Start from the profession, not from the code

A tool exists because a teacher does that thing. So: what does a teacher
physically do in a room?

| She… | Why it matters | Tool family |
|---|---|---|
| looks something up | the syllabus, the answer key, how to handle this | **LOOK UP** |
| writes on the board | the word must be *seen*, not only heard | **SHOW** |
| shows a picture | meaning without translation — the whole scaffolding ladder depends on it | **SHOW** |
| plays a recording | a real voice saying the word properly. Not her own | **PLAY** |
| plays a short video | a scene, a mouth shape, a place the child will never visit | **SHOW** |
| points at the thing she is talking about | joint attention. Without it, thirty children look at thirty places | **SHOW** |
| speaks | one line at a time | **SPEAK** |
| asks, and then waits | the wait is the teaching. A question with no silence after it is a lecture | **SPEAK** |
| notices and remembers | who did what, categorically | **RECORD** |

Five families. Everything below is an argument about how many tool names those
five families should cost.

---

## 2. English specifically — the four skills

English is the first subject and the one we optimise. The optimisation must land
in content, not in the tool surface (NS-6, the generality test) — but the surface
does have to be *capable* of the four skills.

| Skill | What the room needs | Have it? |
|---|---|---|
| **Listening** | a native recording, played cleanly, repeatable; a short video with real speech; the transcript revealed *after* the attempt, not before | ⚠️ audio yes, video **no**, transcript-on-demand **no** |
| **Speaking** | she hears the child (ASR), judges against the key, models it back, and can play the reference again | ⚠️ works; no way to say *"listen again, then try"* as one gesture |
| **Reading** | the word on the board, large; the word highlighted while spoken | ⚠️ board yes, **highlight no** |
| **Writing** | out of scope on a projected shared board — a child writing needs a device per child | — deliberately not built |

Two things follow that are *not* obvious:

**Transcript timing is pedagogy, not plumbing.** Showing the words while the
audio plays turns a listening exercise into a reading exercise. The transcript
must be a separate, later act — which means `play_clip` carrying a transcript
string is the wrong shape. She should play, elicit, *then* reveal.

**Her voice and a recording are different instruments.** `say` is her; a clip is
a model to imitate. Collapsing them would be a pedagogical error, not just an API
one. They stay separate tools.

---

## 3. What exists today

```
read_library   search_library                 LOOK UP   ✅
write_board    read_board    show_image       SHOW      ⚠️ no video, no highlight
play_clip                                     PLAY      ⚠️ transcript is spoken, not revealable
say                                           SPEAK     ⚠️ no way to open a wait
record_evidence                               RECORD    ⚠️ no subject (see §6)
```

Eight tools. Enforced in three places that must move together:

- `infra/hermes/config.yaml` → `mcp_servers.bright-classroom.tools.include`
- `services/classroom-core/mcp_server.py` → the schemas
- `services/classroom-core/teacher_os.py` → `execute()`

and `say` is pinned as the **terminal** tool by the Hermes patch
(`0002-teacher-multi-tool`), which is what bounds a turn.

---

## 4. The four gaps, argued

### 4.1 `show_video` — missing, and it is the EXPLORE mode

The north star's EXPLORE mode is `penguin → Antarctica → ice → ocean → climate`
— *"we are not teaching vocabulary, we are using vocabulary to open the world."*
A still image cannot do that. For a child who has never left the district, thirty
seconds of a real place is the entire point of the product.

Video is also the only honest way to teach a mouth shape.

Cost: the Stage already renders a `video` scene kind. This is mostly a tool name
and a validation path.

### 4.2 `highlight` — missing, and it is joint attention

She says "this one is the apple" and thirty children look at whichever card they
were already looking at. A teacher points. On a projector, pointing is
highlighting a slot on the board.

This is reflex-tier work (NS-2) once issued: no model call, just a board update.

### 4.3 `reveal_transcript` — missing, and it changes what a listening task *is*

Play the clip. Ask. Wait. *Then* put the words up. Three separate acts, and
today the middle two have no tool and the last is fused into the first.

### 4.4 `ask` — missing, and it is the wait

`open_response` existed in the design and was dropped with the cassette. It
should come back, because **the wait is a teaching act with a duration**:

- the room's microphone opens (Layer 4 autonomy)
- the pulse's silence floor should measure from *the question*, not from any line
- the Stage can show that she is listening
- "she asked and nobody answered" becomes a fact the next turn can see

Without it, `say` is overloaded: a statement and a question are the same event to
the machine, and the machine therefore cannot tell whether silence is rude or
expected.

---

## 5. The proposed set — eleven

```
LOOK UP    read_library        open a skill, a unit map, a key
           search_library      find a doc or an asset:// id

SHOW       write_board         chalk: short markdown
           read_board          what is on it now
           show_image          one picture, or two side by side
           show_video          one clip, with a poster frame          ← new
           highlight           point at a slot already on the board   ← new
           reveal_transcript   put a played clip's words up           ← new

PLAY       play_clip           a recorded voice — not hers

SPEAK      say                 one line. ENDS THE TURN
           ask                 one question + open the response window ← new
                               (does not end the turn; `say` still does)

RECORD     record_evidence     one categorical fact, with a SUBJECT   ← changed
```

### Why flat, and not one `board(action=…)` tool

The OpenClaw pattern we borrowed elsewhere — one tool, an action enum — is
genuinely better for a weak model when the actions share parameters. These do
not: `show_image` needs an asset, `highlight` needs a slot id, `write_board`
needs text. An enum hides those differences from the schema, so the validator can
no longer say *"`show_image` requires `asset`"* — and a 4B model loses exactly the
guard rail it needs most.

Flat names with tight schemas let Core reject a malformed call precisely, which
is the mechanism that has been catching the model's mistakes all along.

### The collapse gate

Gemma 4 E4B scores **42.2%** on Tau2 (NS-2). Eleven tools may be too many for it,
even though eleven is trivial for a hosted model.

> **Gate:** when local Gemma runs the Layer 1–3 conformance suite, compare 8-tool
> and 11-tool tool-selection error rates on the same transcripts. If the 11-tool
> error rate is materially worse, collapse the SHOW family into
> `show(kind: image|video|text|highlight, …)` and accept the weaker schema.
>
> **Do not pre-emptively collapse, and do not narrow back to `propose_move`
> "because E4B is weak."** Tighten schemas and reject invalid arguments instead —
> that is already doctrine.

---

## 6. `record_evidence` must gain a subject

This is the one change that is not additive, and it is the most urgent thing in
this document.

```
now       record_evidence(objective_id, outcome, mode)
          → Core attaches it to the only learner that exists

must be   record_evidence(student_id, objective_id, outcome, mode, elicitation)
```

Why it cannot wait for Layer 5:

- Every unit map authored against the subject-less shape is written for a
  classroom of one.
- Every skill that says "record what they did" teaches the wrong reflex.
- It is a **contract** change — schema, memory injection, and content move
  together. Doing it with one learner to migrate is nearly free. Doing it with
  a curriculum in place is not.

While there is one learner, `student_id` is a constant. That is fine. The point
is that the *shape* is right, and that identity (when it arrives from perception)
plugs into a slot that already exists.

`elicitation` is the [three-stores](../decisions/2026-08-18-three-stores.md)
finding: *better evidence ontology beats a better estimator.* Prompted vs
independent, assessment vs exposure, novel context vs repeated prompt.

---

## 7. What she deliberately does not get

Each of these has been asked for, at some point, by somebody sensible.

| Not a tool | Why not |
|---|---|
| `render_html` / arbitrary layout | NS-3. She acts on semantics; Stage owns rendering |
| a path, a URL, a filesystem | Only `asset://` ids Core resolves. Generic Hermes `file`/`browser`/`terminal` stay off in class |
| `next_activity` / `goto` | That is the cassette. Choosing what to teach next *is* teaching |
| `set_mode` / `end_session` by fiat | Core owns the room's lifecycle. She closes a period by teaching its close |
| `score_pronunciation` | NS: no pronunciation percentages before calibration. A number nobody can defend is worse than a kind sentence |
| `write_memory` / free-text notes on a child | NS-5, and §*What she knows about a child*. Evidence, with provenance, or nothing |
| `search_students` | Retrieval must scope to one `student_id` **before** it ranks. A tool that ranks across children is the cross-student leak |
| Hermes' own `skills_list` / `skill_view` | We have `read_library`. Skills live in the library so they survive swapping the runtime |

The pattern: **she is given verbs, never mechanisms.** Every tool above is
something a teacher does in a room. Nothing on the list is something only a
computer does.

---

## 8. Migration checklist

Adding or changing a tool touches five places, and missing one fails silently:

1. `packages/contracts/PROTOCOL.md` — the wire, **first**
2. `services/classroom-core/mcp_server.py` — schema (every tool requires `turn_id`)
3. `services/classroom-core/teacher_os.py` — `execute()` branch + validation
4. `infra/hermes/config.yaml` — `tools.include` allowlist
5. `infra/hermes/patches/0002-teacher-multi-tool.patch` — the terminal-tool match
   list, if the new name must be permitted in a multi-call turn

Plus: a Stage scene kind for anything new that draws, and a line in
`content/library/skills/` teaching her *when* to use it. **A tool nobody was
taught to use is dead weight in the prompt.**
