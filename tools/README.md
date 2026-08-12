# The lesson toolchain

Three small tools that make lesson authoring cheap and safe. They are the rails;
the lessons are the track. **Teachers should read [`content/README.md`](../content/README.md)
instead — this file is for the people maintaining the tools.**

```
lesson.md  ──lesson-lint──►  can this be taught?
     │
     └─────lesson-compile──►  lesson_run.json  ──lesson-play──►  would it stall?
                                    │
                                    └──►  classroom-core  (CORE_LESSON_RUN)
```

| Tool | Question it answers | Exit code |
|---|---|---|
| `lesson-lint/lesson_lint.py` | can this lesson produce a complete, playable run? | 0 fine · 1 problems · 2 unreadable |
| `lesson-compile/lesson_compile.py` | `lesson.md` → `lesson_run.json` (PROTOCOL.md §4) | 0 written · 1 lint failed · 3 schema failed |
| `lesson-play/lesson_play.py` | does it reach the end for every kind of class? | 0 no stalls · 1 stalls |

Requirements: Python 3.11+, `pyyaml`, `pydantic`. No network, no model, ever.

```bash
python3 tools/lesson-lint/lesson_lint.py    content/lessons/example/format-example.md
python3 tools/lesson-compile/lesson_compile.py content/lessons/example/format-example.md
python3 tools/lesson-play/lesson_play.py    content/lessons/example/format-example.run.json
python3 tools/lesson-lint/selftest.py       # checks the tools themselves
```

## Design rules

**The compile is deterministic and offline.** A frontier model may help a person
write the `.md` (the internet exists at authoring time — execution-plan §1), but
nothing between the `.md` and the run is generated. If the compiler were allowed
to invent content, lint could not promise anything about what a class sees.

**One parser, two tools.** `lesson-lint/parse.py` is shared by all three, so the
thing that is validated is exactly the thing that is compiled. `lesson-compile`
runs `lesson-lint` first and refuses to write a run with errors in it.

**The output is for a teacher.** Every lint message says what is wrong, which
line, *what the class would experience*, and the text to type. No stack traces,
no schema paths, no jargon. If a message cannot be acted on by someone who does
not code, it is a bug.

**Rules earn their place by describing a classroom failure.** "Missing required
field" is not a rule; "nobody answers and the lesson moves on as if they had" is.

## Layout

```
tools/
├── lesson-lint/
│   ├── parse.py                 the lesson.md format — shared by all three tools
│   ├── lesson_lint.py           the rules and the human-readable report
│   ├── selftest.py              proves every rule still fires, and the example still works
│   └── fixtures/broken-lesson.md   one instance of every fault, deliberately
├── lesson-compile/lesson_compile.py
└── lesson-play/lesson_play.py   imports the real runner from services/classroom-core
```

## Two things to know before changing anything

**`on:` is the boolean `true` in YAML 1.1.** A bare `on:` key parses as `True`,
which silently deleted every branch in every lesson the first time this was run.
`parse._unbool_keys` maps it back. Do not remove it, and do not "fix" it by
telling authors to write `on` in quotes — they will not.

**Which no-answer outcome fires depends on timing** (PROTOCOL §9.4): with
`durationS` set it is `timeout`, without it is `silence`. PROTOCOL §4 requires a
`silence` branch on every graded activity regardless, so lessons carry one branch
that cannot fire under the current timing. Lint requires the §4 pair and *warns*
about the live one; `lesson-play` labels the unreachable one rather than
reporting it as a gap. If §4 and §9.4 are ever reconciled, all three places
change together.

## Adding a rule

1. Add the check to `check_activity` or `check_flow` in `lesson_lint.py`. Write
   the message as three parts: `what`, `why` (what the class experiences), `fix`.
2. Add an instance of the fault to `fixtures/broken-lesson.md`.
3. Add the `(activity, message fragment)` pair to `EXPECTED_FAULTS` in
   `selftest.py`.
4. Run `python3 tools/lesson-lint/selftest.py`.

An error must mean *the lesson cannot be taught*. If a class could still run with
it, it is a warning.
