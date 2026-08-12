# Writing a lesson

This folder holds the lessons the classroom system teaches. You write a lesson in
a text file; a tool turns it into the file the classroom actually plays.

**You do not need to write any code.** If you can write a document with headings
and lists, you can write a lesson.

```
content/
├── lessons/          the lessons you write        (.md — this is your work)
│   └── example/      format-example.md — every field of the format, once each.
│                     A shape to copy from, not a lesson to teach.
├── media/            the pictures lessons use
└── README.md         this guide
```

---

## The two files

| File | Who writes it | What it is |
|---|---|---|
| `lesson.md` | **you** | the lesson, in readable text: what is said, what is shown, what happens when a child answers |
| `lesson_run.json` | the computer | the same lesson, rewritten for the machine. Never edit it by hand — it is replaced every time you compile |

You only ever edit the `.md`. Everything else is generated.

---

## Three commands

Run these from the top folder of the project.

```bash
# 1 — check your lesson. Do this constantly while writing.
python3 tools/lesson-lint/lesson_lint.py content/lessons/example/format-example.md

# 2 — turn it into the file the classroom plays
python3 tools/lesson-compile/lesson_compile.py content/lessons/example/format-example.md

# 3 — watch it play through, with no classroom and no AI, in one second
python3 tools/lesson-play/lesson_play.py content/lessons/example/format-example.run.json
```

The first one is the important one. It answers a single question: **can this
lesson be taught from beginning to end without anybody stepping in?** It tells
you what is missing, on which line, what the class would experience, and the
exact words to add.

The third one plays your lesson five times over — as a class that gets
everything right, one that gets everything wrong, one that says nothing at all,
and so on — and tells you if any of them gets stuck.

---

## What a lesson looks like

A lesson is one text file with two parts: **the settings** at the top, then **one
section per activity**.

````markdown
---
id: en-a1-market-01
class: 7A
title: At the Market
level: A1
duration_min: 20
vocabulary: [apple, banana, rice]
---

Anything written here is notes for other teachers. The computer ignores it.
Use it for the things a colleague would need to know: what usually goes wrong,
why an activity is shaped the way it is.

## welcome

```yaml
scene: text
props:
  text: "At the Market"
  size: xl
duration_s: 10
say:
  - "Hello everyone! Today we go to the market. @happy/Happy"
```
````

Each activity is a `##` heading — the words after `##` are the activity's **name**
— followed by a block between ```` ```yaml ```` and ```` ``` ````. Everything
inside that block is the activity. Everything outside it is notes.

Activities run in the order they appear in the file, unless you send the lesson
somewhere else (see **Branches** below).

### Settings at the top

| Setting | Needed? | What it does |
|---|---|---|
| `id` | **yes** | the lesson's name for the computer. Lowercase, no spaces, e.g. `en-a1-market-01` |
| `title` | **yes** | the lesson's name for people |
| `class` | recommended | which class this run is for, e.g. `7A` |
| `level` | no | `A1`, `A2`, … for your own reference |
| `duration_min` | no | how long you intend the lesson to be. The checker compares it with reality and tells you if you have overrun |
| `focus` | no | the skills this lesson practises, e.g. `[food_vocab, polite_request]`. Used to record what each child is getting better at |
| `review` | no | skills carried over from earlier lessons |
| `students_to_check` | no | children the system should make a point of calling on |
| `objectives`, `target_phrases`, `vocabulary` | no | for humans reading the file |
| `fallback_language` | no | `vi` — the language used on the last rung of the ladder |

---

## Inside one activity

```yaml
scene: choice              # what kind of board this is
props:                     # what is on the board
  prompt: "Which one do you drink?"
  options:
    - { id: water, text: water, asset: "asset://market/water.svg" }
    - { id: rice,  text: rice,  asset: "asset://market/rice.svg" }
duration_s: 25             # how long before the lesson moves on by itself
say:                       # what the avatar says, in order
  - "I am thirsty. Which one do you drink? @question"
expect:                    # how an answer is judged
  kind: choice
  correct: water
  fuzzy: [rice]
on:                        # where to go for each kind of answer
  correct: { goto: next_activity, say: ["Water! Yes. @happy/Happy"] }
  near:    { goto: recast_drink,  say: ["Almost. @curious"] }
  wrong:   { goto: help_drink,    say: ["Hmm, you eat that one. @curious"] }
  silence: { goto: help_drink,    say: ["Let me help. @think"] }
  timeout: { goto: help_drink,    say: ["Let us look together. @think"] }
```

| Line | Meaning |
|---|---|
| `scene` | which kind of board — see the table below |
| `props` | the contents of that board |
| `duration_s` | seconds before the lesson moves on by itself. Leave it out and the board waits for an answer |
| `say` | the lines the avatar speaks, in order |
| `expect` | what counts as an answer, and which one is right |
| `on` | where the lesson goes next, for each kind of answer |
| `goto: some_activity` | shorthand for "when this is finished, go to `some_activity`" |

If an activity has none of `duration_s`, `expect` or `goto`, **the board freezes**
and the teacher has to press Skip. The checker treats that as an error.

---

## The kinds of board

| `scene` | What the class sees | Must have in `props` |
|---|---|---|
| `text` | large words on the board | `text` (and optionally `size`: `sm` `md` `lg` `xl`) |
| `image` | one picture with a caption | `asset`, optionally `caption` |
| `vocabulary` | a grid of word cards with pictures | `items`, `interaction` (`none` or `point`), optionally `highlightId` |
| `choice` | a question with two or three answers to tap | `prompt`, `options` |
| `matching` | two columns to drag between | `left`, `right`, `solved` |
| `sentence_builder` | word tiles to build a sentence | `tokens`, `placed`, optionally `target` |
| `pronunciation` | one word, sound by sound | `word`, `phonemes` |
| `roleplay` | a scene to act out in pairs | `environment`, `aiRole`, `studentRole`, `targetPhrases` |
| `explore` | a word opening onto the world | `topic`, `nodes`, optionally `focusId` |
| `video` | a video, same as `image` plus `autoplay` | `asset` |
| `idle` | the empty board between lessons — never write this one | — |

`matching`, `sentence_builder`, `pronunciation`, `roleplay` and `explore` are
shown on the board as readable summaries for now — the full drag-and-drop is not
built yet. They are safe to use for teacher-led activities; do not build a
question around dragging and expect the children to do it themselves today.

Every item on a board needs an **`id`** — a short name with no spaces. That id is
how an answer is recognised.

---

## Pictures

Pictures live in `content/media/` and are referred to as `asset://`:

```
content/media/market/apple.svg      →     asset://market/apple.svg
```

Never write a file path like `content/media/market/apple.svg` in a lesson — the
board cannot read the disk, only `asset://` names. The checker catches this.

If you refer to a picture that does not exist, the checker tells you exactly
where to put the file. You do not have to list your pictures anywhere: the
compiler collects them for you.

---

## What the avatar says

```yaml
say:
  - "Hello everyone! @happy/Happy"
  - "Which one is the apple? @question"
  - "Let me think about that. @think:0.6"
  - "Just a plain line with no expression."
```

The `@word` at the end of a line is the avatar's expression. There are **nine**,
and no others:

```
happy   sad   angry   think   surprised   awkward   question   curious   neutral
```

- `@happy` — the expression, with its usual movement
- `@happy/Happy` — the expression plus a named movement (the same thing, written out)
- `@think:0.6` — a weaker version of the expression, between 0 and 1

Keep lines **short**. One idea per line. The avatar pauses between lines, and
short lines are easier for a beginner to follow. The checker warns you when the
lines take longer to say than the time you have allowed.

### Recorded lines (optional)

By default the computer speaks every line. If a line has been recorded by a
person — a model sentence you want the class to hear pronounced properly — point
at the recording instead:

```yaml
say:
  - "Hello everyone! @happy/Happy"
  - { text: "I would like an apple, please.", audio: "asset://narration/market-01-3.opus" }
```

Write this only when the sound file exists. A line with `audio:` is **never**
spoken by the computer voice, so a missing file means silence in class — the
checker reports it as an error. Recording is normally done at the end, once the
words have stopped changing.

### Vietnamese

Vietnamese is the **last** rung of the ladder, never the first. Try, in order:
simpler English → a picture → a concrete example → a Vietnamese word → a
Vietnamese explanation. Each rung is a separate recovery activity, so the lesson
only goes as far down the ladder as it needs to.

When you do use Vietnamese, write it with full diacritics — `quả táo`, `nước`,
`Con muốn một quả táo ạ.` — and always come back to English in the same activity:

```yaml
say:
  - "Apple. Quả táo. @neutral"
  - "Táo is apple. Now say it in English: apple. @curious"
```

---

## Answers

```yaml
expect:
  kind: speech
  correct:
    - "I would like an apple please"
  fuzzy:
    - "I want an apple please"
    - "I would like a apple please"
```

| `kind` | The child answers by | `correct` is |
|---|---|---|
| `choice` | tapping one of the options | the option's `id` |
| `point` | pointing at a card on a `vocabulary` board | the item's `id` |
| `drag` | dragging one thing onto another | the target's `id`, or `"from>to"` for the exact pair |
| `speech` | speaking | the sentence, written out. Punctuation and capitals do not matter |
| `none` | nothing — the activity is not graded | — |

**`correct` vs `fuzzy`.** `correct` must match: the child said the sentence, or
said it inside a longer one. `fuzzy` is for the almost-right answers, and they
grade as `near`. This distinction is the whole point:

- `I want an apple, please` → put in `fuzzy`. The child produced a correct polite
  request with the wrong verb. Marking it wrong teaches them that trying is
  dangerous; a `near` branch recasts it instead.
- `I would like an apple` (no *please*) → `fuzzy`, and the recast adds the *please*.
- `apple` → wrong. That is not the sentence.

Never put an almost-right answer in `correct`, or the lesson stops teaching the
difference.

---

## Branches — the part that matters

A branch says where the lesson goes after an answer. There are six:

| `on:` | When it happens |
|---|---|
| `correct` | the answer matched `correct` |
| `near` | the answer matched `fuzzy` |
| `wrong` | anything else |
| `silence` | nobody answered — on an activity with **no** `duration_s` |
| `timeout` | nobody answered — on an activity **with** `duration_s` |
| `always` | after this activity, whatever happened (this is what `goto:` writes for you) |

**The rule the checker enforces: every activity that asks a question must have a
`wrong` branch and a `silence` branch.** If you cannot write what happens when a
child gets it wrong, the question is not ready to be asked.

Because a child who says nothing needs a different answer from a child who says
the wrong thing, write both `silence` and `timeout` and point them at the same
recovery. Which one fires depends only on whether you set `duration_s`.

### A good branch set

```yaml
on:
  correct:
    goto: next_question
    say: ["Yes! That is the apple. @happy/Happy"]
  wrong:
    goto: help_apple                     # a step that makes it EASIER
    say: ["Nearly. Let us look together. @curious"]
  silence:
    goto: help_apple
    say: ["That is alright, I will help you. @think"]
  timeout:
    goto: help_apple
    say: ["Let us look together. @think"]
```

And the recovery step it points at — fewer things on the board, one of them
highlighted, simpler words, then straight on:

```yaml
scene: vocabulary
props:
  items:
    - { id: apple,  text: apple,  asset: "asset://market/apple.svg" }
    - { id: banana, text: banana, asset: "asset://market/banana.svg" }
  interaction: none
  highlightId: apple
duration_s: 12
say:
  - "This one is the apple. It is red. @neutral"
  - "Apple. Quả táo. Now in English: apple. @curious"
goto: choose_drink
```

### Three ways to get branches wrong

**Sending a wrong answer back to the same question.** The child could not answer
it the first time; asking again changes nothing except how they feel. Send them
to a step that lowers the difficulty. The checker warns about this.

**A recovery step that says nothing.** The board jumps somewhere else with no
explanation, and children read that as punishment. Always give a branch a `say`.

**Asking three times.** Two attempts, then help them and move on. A lesson that
will not let go of one question loses the other twenty-nine children.

---

## What the checker will reject

Everything in this list stops the lesson from being taught, so the checker
reports it as an error:

| It will reject | Because in class |
|---|---|
| a question with no `wrong` branch | a child answers wrongly and the lesson moves on with no help |
| a question with no `silence` branch | nobody answers and the lesson carries on as if they had |
| `goto:` pointing at a name that does not exist | the lesson silently skips your recovery |
| a picture that is not in `content/media/` | a broken image on the board |
| an activity with no `say:` lines | the board changes in silence |
| an activity nothing can reach | you wrote it and the class never sees it |
| an activity with no `duration_s`, no question and no `goto` | the board freezes until the teacher presses Skip |
| a `correct` answer that is not one of the options | the class can never get it right |
| two options sharing an `id` | only the first one can ever be chosen |
| an expression that is not one of the nine | the avatar does not react |
| a board kind that does not exist | a red error card in front of the class |
| a recorded line whose sound file is missing | that line is silent |

And these are warnings — the lesson still runs, but check them:

| It will warn | Because |
|---|---|
| the narration takes longer than `duration_s` | the board moves on while the avatar is still talking |
| a `near` branch with no `fuzzy:` answers | that recovery can never happen |
| `fuzzy:` answers with no `near` branch | an almost-right answer is treated exactly like a wrong one |
| a `wrong` branch pointing back at the same activity | the child is asked the same question forever |
| a branch that says nothing | the lesson jumps with no explanation |
| the lesson runs much longer or shorter than `duration_min` | the bell, or an empty ten minutes |

---

## Starting a new lesson

1. Copy `content/lessons/example/format-example.md` into a new folder, e.g.
   `content/lessons/animals/en-a1-animals-01.md`.
2. Change the settings at the top — a new `id` above all.
3. Delete the activities you do not want; keep the shapes you do.
4. Run the checker after every few activities. It is much easier to fix one thing
   than twenty.
5. When it says *"this lesson can be taught end to end"*, compile it and play it
   through.

### Where the files go

```
content/lessons/<theme>/<id>.md          your lesson
content/lessons/<theme>/<id>.run.json    what the compiler makes, next to it
content/media/<theme>/<name>.svg         the pictures
```

To play a lesson in the classroom, point the classroom service at the compiled
file:

```bash
CORE_LESSON_RUN=/full/path/to/<id>.run.json  ./scripts/dev.sh
```

---

## If something looks wrong

**"my branches are being ignored"** — check the indentation under `on:`. Each
outcome must be indented under it, and everything under one outcome must line up.
YAML cares about spaces, and never about tabs. Do not use tab characters.

**"the checker says a picture is missing but I can see it"** — the name after
`asset://` is the path *inside* `content/media/`, so a file at
`content/media/market/apple.svg` is `asset://market/apple.svg`.

**"quotes"** — put quotes around any line containing `:`, `#`, or starting with a
number. Quotes are never wrong; leaving them out sometimes is.

**Anything else** — the checker's message says which line and what to write. If a
message is not clear enough to act on, that is a bug in the checker, not in you;
say so and it will be fixed.
