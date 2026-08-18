# Decision: teacher skills live in the library, not in Hermes

**Date:** 2026-08-18
**Status:** LOCKED
**Implements:** [NORTH-STAR.md](../NORTH-STAR.md) NS-6 — *the profession is data, not code*
**Constrained by:** NS-4 — *the runtime is replaceable; the contract is not*

---

## The problem

Today the entire teaching profession is one file: `content/library/how-to-teach.md`
(515 words). It covers language mixing, how to open a period, what counts as
evidence, and how to close — all at once, all injected on every turn.

That works for one subject at Pre-A1. It does not survive the second subject,
and the north star says there will be many. We need a way for the teacher to
know *how to do professional things* that:

- scales to dozens of procedures without filling the context window
- is authorable by a teacher, not an engineer
- ships with the curriculum
- survives swapping the runtime (NS-4)

That is exactly what agent **skills** are.

---

## What Hermes already has (and why we still say no)

Hermes ships a real, well-designed skills system — verified in the vendored
source at the pinned commit:

| Mechanism | Where |
|---|---|
| `SKILL.md` per skill, YAML frontmatter + markdown body | `agent/skill_utils.py:174` |
| Two-tier **progressive disclosure**: an index of `name + description` (truncated to 60 chars) in the system prompt, bodies loaded only on demand | `agent/prompt_builder.py:1664-1817`, `agent/skill_utils.py:849` |
| `skills_list` (tier 1, metadata) and `skill_view` (tier 2, full body) as ordinary model-callable tools | `tools/skills_tool.py:789`, `:1057` |
| Per-profile allow/deny, platform gating, tool-availability gating | `agent/skill_utils.py:436-471`, `:681-695` |
| Support files (`references/`, `templates/`, `assets/`) loaded individually | `agent/skill_utils.py:46-51` |

**And Bright's live classroom profile switches all of it off**, deliberately:

- `infra/hermes/config.yaml` sets `platform_toolsets.api_server: [bright-classroom]`
  — only the 8 classroom MCP tools exist; `skills_list` / `skill_view` are not
  reachable.
- Patch `0001-bright-live-ephemeral` pins the **entire** system prompt to
  `gateway.api_server.extra.bright_live.system_prompt`, bypassing the assembly
  that would inject a skills index at all.

So the choice is real: re-open Hermes' skills surface, or build the same shape
inside the library.

### Why the library wins

**1. NS-4 decides it.** If the profession lives in `~/.hermes/skills/`, then
swapping Hermes for another harness — or for local Gemma behind a different
runtime — loses the teacher's professional knowledge. The north star names five
assets that are *not* replaceable, and `content/` is one of them. Hermes is not.

**2. One authoring surface.** A teacher improving Bright should edit one tree:
`content/library/`. Splitting "what to teach" and "how to teach" across a
curriculum folder and a runtime's home directory guarantees they drift, and
guarantees the person who knows teaching cannot find half of it.

**3. It ships.** The library is the thing that goes on the USB stick with the
media. Hermes' home directory is machine state.

**4. It re-opens nothing.** The live profile is deliberately stateless,
tool-restricted, and single-purpose. Adding two more Hermes tools to a
classroom-facing surface is a security and complexity cost for capability we can
get from a tool we already have.

**5. We already have the reader.** `read_library` + `search_library` are exactly
`skill_view` + `skills_list` with a different name and a scoped root.

**What we do take from Hermes: the design.** `SKILL.md`, YAML frontmatter, and
strict progressive disclosure are a proven shape. We copy it rather than invent
one.

---

## The decision

```
content/library/
  index.md                     declares languages, units, and skills
  skills/
    index.md                   name + one line each — the ONLY part always in context
    open-a-period/SKILL.md
    elicit-a-word/SKILL.md
    scaffold-down/SKILL.md
    judge-a-response/SKILL.md
    recover-a-wobble/SKILL.md
    close-a-period/SKILL.md
    prepare-a-period/SKILL.md
  units/
    market-food/{map,keys,practice}.md
    colours/{map,keys,practice}.md
```

**Skill file format** — deliberately the Hermes shape:

```markdown
---
name: elicit-a-word
description: Get the child to say the word, not just recognise it.
when: they pointed correctly, or they went quiet after a question
version: 1
---

## Do

1. Model it once, clearly. …
```

`description` and `when` are the only fields that reach the model unasked. Keep
both under ~80 characters — they are paid for on **every turn**.

### The three tiers

| Tier | What the teacher sees | Cost | How |
|---|---|---|---|
| 0 | `skills/index.md` — every skill's name, description, `when` | every turn, ~200 tokens | rendered into the turn prompt by Core |
| 1 | one skill's full body | only when she opens it | `read_library skills/elicit-a-word/SKILL.md` |
| 2 | a support file inside a skill | rarely | `read_library skills/<name>/references/<file>.md` |

She decides. Core does not push a skill on her, and does not compute which one
applies — that would be Core teaching, which NS-1 forbids.

### Skills vs units — the line that must not blur

| | Skills | Units |
|---|---|---|
| Answer | **how** to teach | **what** to teach today |
| Portable | across every subject and language | no — a unit is one subject |
| Written by | someone who knows teaching | someone who knows the syllabus |
| Changes when | our understanding of the profession improves | the curriculum changes |
| Names a word like `banana`? | **never** | yes |

A skill that mentions `banana` is a bug. A unit map that explains how to
scaffold is a bug. `tests/test_no_unit_pedagogy.py` guards the Core side of this
line; the same rule applies to authored content.

---

## Consequences

- `how-to-teach.md` **splits**. Its language-mixing section stays as a
  general-conduct file; everything procedural becomes a skill.
- `content/library/index.md` gains a `skills/` pointer alongside `units/`.
- `render_teacher_turn` (`services/agent/bright_agent/hermes.py:242`) gains the
  tier-0 index. It already carries `READS=`, so "she has not opened the skill
  she needs" is already detectable.
- No new tool. No new Hermes surface. No new store.
- When we move to local Gemma (Layer 6), the profession moves with the content —
  **zero work**.

## What this does not decide

- Whether a skill may be *written* by the agent. Hermes has a curator that
  reviews agent-authored skills (`agent/curator.py:2001`). For a child-facing
  teacher, an agent editing its own professional standards is a much larger
  decision and is **not** taken here. Skills are authored by people.
- Subject-specific skill packs (phonics, numeracy). The layout above allows
  them; nothing is authored yet.
