# `content/` — the curriculum library

This is what the teacher reads. She opens the index, then the profession, then
the unit she is teaching — the way a coding agent opens a repo's map before a
file. **You do not need to write any code.** If you can write a document with
headings and lists, you can improve the teacher.

```
content/
├── library/          the live curriculum  ← your work goes here
│   ├── index.md      declares the languages, the units, and where the skills are
│   ├── how-to-teach.md   who she is in the room, and how she treats a child
│   ├── skills/       HOW to teach — one folder per procedure
│   └── units/        WHAT to teach — one folder per unit
├── media/            pictures and recordings, addressed as asset://
└── lessons/          historical. The compiled `.run.json` cassette. Not the teacher
```

## The line that matters most

> **Skills are the profession. Units are the curriculum.**

A skill — how to open a period, how to get the class saying something together,
how to judge what an answer shows — reads the same whether the subject is English
or maths. **A skill that names a vocabulary word is a bug.**

A unit map says what today is for, what language is locked, and which pictures
and recordings exist. **A unit map that explains how to scaffold is a bug.**

Everything the teacher knows that a person wrote sits in one of four layers, and
none of them is code:

| Layer | Answers | Where |
|---|---|---|
| Conduct | who she is, how she treats a child | `library/how-to-teach.md` |
| Skills | *how* to do one professional thing | `library/skills/<name>/SKILL.md` |
| Unit map | *what* this period is for | `library/units/<unit>/map.md` |
| Keys | what counts as a correct response | `library/units/<unit>/keys.md` |

## A unit is a map, not a script

This is the whole design. The teacher is an agent, not a tape player.

**Write:** what a child can do at the end · the objectives she may record
evidence against · the locked vocabulary · which picture and which recording
serve which purpose · the shape of each period · when the unit is finished.

**Do not write:** a numbered list of steps with clock times · the exact sentences
she must say · "at minute 22, move on". If you write a script, you have replaced
a teacher with a recording, and the lesson dies the moment a child says something
you did not predict.

Example lines *are* welcome — she reads them as models of good teacher language,
not as lines to recite.

## Adding a unit

1. `mkdir content/library/units/<unit-id>` with `map.md`, `keys.md`, `practice.md`.
2. Add one row to `library/index.md`. **A unit not in the index does not exist** —
   she is forbidden to invent one.
3. Write objectives as `- id: \`some-id\` — what the child can do`. Only these ids
   may be recorded as evidence; anything else is refused.
4. Put pictures and audio in `content/media/<folder>/` and refer to them as
   `asset://<folder>/<file>`. **Never a file path** — the board cannot read the
   disk, and an id that does not resolve is refused before it reaches the screen.

Then run the library tests:

```bash
cd services/classroom-core && python -m pytest tests/test_library.py -q
```

They check that the index and the folders agree, that every `asset://` resolves,
that skills stay free of curriculum, and that nothing in a unit smells like a
compiled graph.

## Third-party material

`content/media/gs3/` is Global Success Grade 3 — Vietnam Education Publishing
House and Macmillan. It is **gitignored on purpose**: correct to prototype
against, not ours to redistribute. Import it with:

```bash
./scripts/import-textbook-assets.sh
```

Anything shipped on a donated appliance must be team-authored or openly licensed.
