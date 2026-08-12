---
title: Every Mistake At Once
level: A1
duration_min: 20
---

A deliberately broken lesson. Every activity below contains at least one fault
that `lesson-lint` must catch; `selftest.py` asserts that it does. Do not fix
anything in this file — it is the test.

## no_id_lesson_note

The lesson frontmatter above has no `id:` and no `class:`.

```yaml
scene: text
props:
  text: "Hello"
duration_s: 8
say:
  - "Hello everyone. @sparkly"
```

## broken_choice

Missing `wrong` and `silence`; `correct` is not one of the options; two options
share an id; the picture does not exist; `near` with no `fuzzy`.

```yaml
scene: choice
props:
  prompt: "Which one?"
  options:
    - { id: apple,  text: apple, asset: "asset://market/durian.svg" }
    - { id: apple,  text: apple }
    - { id: banana, text: banana }
duration_s: 20
say:
  - "Which one is the apple? @question"
expect:
  kind: choice
  correct: mango
on:
  correct: { goto: nowhere_at_all, say: ["Yes! @happy"] }
  near:    { goto: silent_board }
```

## silent_board

No narration at all, and a raw file path where an asset reference belongs.

```yaml
scene: image
props:
  asset: "market/apple.svg"
duration_s: 10
goto: never_ends
```

## never_ends

No duration, nothing to answer, no next step: the board freezes. The second line
also points at a recorded audio file that does not exist, which would be silence
in class rather than a computer voice.

```yaml
scene: text
props:
  text: "..."
say:
  - "Now what? @think"
  - { text: "This line was recorded.", audio: "asset://narration/missing-line.opus" }
```

## bad_scene

An invented scene kind. Because the scene is unknown, nothing else about this
activity can be checked — one broken line hides the rest, which is why lint
reports it as an error and stops there.

```yaml
scene: quiz_show
props:
  text: "?"
duration_s: 3
say:
  - "What kind of board is this? @neutral"
goto: never_ends
```

## orphan

Nothing points here and nothing falls through to it, so the class never sees it.
Its narration is also far longer than the time allowed.

```yaml
scene: text
props:
  text: "unreachable"
duration_s: 3
say:
  - "This narration is much too long for three seconds, and it keeps going on and on well past the point where the board has already moved on to the next activity, which means the class hears half a sentence and then silence. @sad"
goto: never_ends
```
