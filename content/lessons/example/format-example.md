---
id: en-a1-format-example
class: demo
title: At the Market (format example)
level: A1
duration_min: 7
fallback_language: vi
objectives:
  - show every field of the lesson format at least once
target_phrases:
  - "I would like an apple, please."
vocabulary: [apple, banana, rice, water, bread, egg]
focus: [food_vocab]
review: [greetings]
students_to_check: [s04]
---

# FORMAT EXAMPLE — not curriculum

**This file exists to exercise the format, not to teach a class.** It is the
reference an author copies from and the fixture the toolchain is tested against.
Real lessons are written by a teacher; see `content/README.md` for how.

Between them, the activities below use **every scene kind that can be authored,
every kind of answer, every kind of branch, and both timing modes**, so if
`lesson-lint` and `lesson-compile` handle this file they handle anything.

| Shown here | Where |
|---|---|
| `text`, `image`, `vocabulary`, `choice` scenes | `welcome`, `look_market`, `vocab_grid`, `choose_drink` |
| `matching`, `sentence_builder`, `pronunciation`, `roleplay`, `explore` | `match_pairs` … `explore_rice` |
| answers by `point`, `choice`, `drag`, `speech` | `point_apple`, `choose_drink`, `match_pairs`, `build_sentence` |
| branches `correct` `near` `wrong` `silence` `timeout` `always` | every graded activity |
| `goto:` shorthand for a plain next step | `look_market`, all the recovery steps |
| avatar cues `@happy`, `@curious:0.6`, `@think/Think` | `welcome`, `help_apple` |
| timed activity (`duration_s`) vs. one that waits for an answer | `point_apple` vs. `choose_drink` |
| a recovery step that lowers the difficulty instead of repeating | `help_apple`, `help_drink` |

Two scene kinds are deliberately **not** used: `idle` (the board between
lessons, never authored) and `video` (identical to `image` plus `autoplay`, and
this repository has no video file to point at).

---

## welcome — HOOK

A plain timed activity: it speaks, waits `duration_s`, then falls through to the
next section in the file. No branches needed.

```yaml
scene: text
props:
  text: "At the Market"
  size: xl
duration_s: 10
say:
  - "Hello everyone! Today we go to the market. @happy/Happy"
  - "Are you ready? @curious:0.6"
```

## look_market — HOOK

`goto:` is the shorthand for "when this finishes, go here". It compiles to an
`always` branch. Use it whenever the next step is not simply the next section.

```yaml
scene: image
props:
  asset: "asset://market/market.svg"
  caption: "the market"
duration_s: 15
say:
  - "Look. This is a market. We can buy food here. @curious"
goto: vocab_grid
```

## vocab_grid — INPUT

`interaction: none` means the board shows the words but taps do nothing. Use it
while you are presenting, before anyone is asked to answer.

```yaml
scene: vocabulary
props:
  items:
    - { id: apple,  text: apple,  asset: "asset://market/apple.svg" }
    - { id: banana, text: banana, asset: "asset://market/banana.svg" }
    - { id: rice,   text: rice,   asset: "asset://market/rice.svg" }
    - { id: water,  text: water,  asset: "asset://market/water.svg" }
    - { id: bread,  text: bread,  asset: "asset://market/bread.svg" }
    - { id: egg,    text: egg,    asset: "asset://market/egg.svg" }
  interaction: none
duration_s: 40
say:
  - "Six words. Apple. Banana. Rice. @neutral"
  - "Water. Bread. Egg."
  - "Now say them with me. @happy"
```

## point_apple — GUIDED PRACTICE

Answering by pointing at the board. `interaction: point` turns the taps on;
`expect.kind: point` grades them by item id.

Because `duration_s` is set, a class that never answers produces **`timeout`**
(PROTOCOL §9.4). The `silence` branch is written anyway: it is required, and it
becomes the live one the moment the duration is removed.

```yaml
scene: vocabulary
props:
  items:
    - { id: apple,  text: apple,  asset: "asset://market/apple.svg" }
    - { id: banana, text: banana, asset: "asset://market/banana.svg" }
    - { id: rice,   text: rice,   asset: "asset://market/rice.svg" }
    - { id: water,  text: water,  asset: "asset://market/water.svg" }
  interaction: point
duration_s: 20
say:
  - "Come and point to the apple. @question"
expect:
  kind: point
  correct: apple
on:
  correct:
    goto: choose_drink
    say:
      - "Yes! That is the apple. @happy/Happy"
  wrong:
    goto: help_apple
    say:
      - "Nearly. Let us look together. @curious"
  silence:
    goto: help_apple
    say:
      - "That is alright. I will help you. @think"
  timeout:
    goto: help_apple
    say:
      - "Let us look together. @think"
```

## help_apple — RECOVERY

A recovery step makes the question **easier** — fewer pictures, one of them
highlighted, simpler words — and then moves on. It never repeats the same demand.

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
  - "This one is the apple. It is red. @think/Think"
  - "Apple. Quả táo. Now in English: apple. @curious"
goto: choose_drink
```

## choose_drink — RETRIEVAL

No `duration_s` here, so this board waits for an answer and a class that says
nothing produces **`silence`** after `CORE_SILENCE_TIMEOUT_S`. Compare with
`point_apple` above — that is the whole difference between the two timing modes.

`fuzzy:` lists the almost-right answers. They grade as `near`, which is what the
`near` branch is for: a recast, not a correction.

```yaml
scene: choice
props:
  prompt: "Which one do you drink?"
  options:
    - { id: water,  text: water,  asset: "asset://market/water.svg" }
    - { id: rice,   text: rice,   asset: "asset://market/rice.svg" }
    - { id: bread,  text: bread,  asset: "asset://market/bread.svg" }
say:
  - "I am thirsty. Which one do you drink? @question"
expect:
  kind: choice
  correct: water
  fuzzy: [rice]
on:
  correct:
    goto: match_pairs
    say:
      - "Water! Yes. @happy/Happy"
  near:
    goto: recast_drink
    say:
      - "Almost — you can drink rice soup, but I want a bottle. @curious"
  wrong:
    goto: help_drink
    say:
      - "Hmm, you eat that one. @curious"
  silence:
    goto: help_drink
    say:
      - "Let me help. @think"
  timeout:
    goto: help_drink
    say:
      - "Let us look together. @think"
```

## recast_drink — RECOVERY

```yaml
scene: text
props:
  text: "water"
  size: xl
duration_s: 8
say:
  - "We drink water. Water. @neutral"
goto: match_pairs
```

## help_drink — RECOVERY

```yaml
scene: vocabulary
props:
  items:
    - { id: water, text: water, asset: "asset://market/water.svg" }
    - { id: rice,  text: rice,  asset: "asset://market/rice.svg" }
  interaction: none
  highlightId: water
duration_s: 12
say:
  - "You drink water. You eat rice. @neutral"
  - "Drink — water. Nước. @curious"
goto: match_pairs
```

## match_pairs — PRACTICE

Answering by dragging. A drag answer can be written two ways: just the id of the
place it was dropped (`an_apple`), or the pair `picture>place`. The pair form is
used here because it is the stricter of the two.

```yaml
scene: matching
props:
  left:
    - { id: apple,  asset: "asset://market/apple.svg" }
    - { id: banana, asset: "asset://market/banana.svg" }
  right:
    - { id: an_apple,  text: "an apple" }
    - { id: a_banana,  text: "a banana" }
  solved: []
duration_s: 30
say:
  - "Match the picture to the words. @question"
expect:
  kind: drag
  correct: "apple>an_apple"
  fuzzy: ["apple>a_banana"]
on:
  correct:
    goto: build_sentence
    say:
      - "Correct — an apple. @happy/Happy"
  near:
    goto: help_match
    say:
      - "Careful, that is the banana. @curious"
  wrong:
    goto: help_match
    say:
      - "Not quite. Look again. @curious"
  silence:
    goto: help_match
    say:
      - "I will show you. @think"
  timeout:
    goto: help_match
    say:
      - "Let us do it together. @think"
```

## help_match — RECOVERY

```yaml
scene: text
props:
  text: "an apple  ·  a banana"
  size: lg
duration_s: 10
say:
  - "An apple. A banana. @neutral"
goto: build_sentence
```

## build_sentence — PRODUCTION

Answering by speaking. `correct:` is matched exactly or by containment;
`fuzzy:` also allows a close match, which is why the almost-right sentences go
there and never in `correct`.

```yaml
scene: sentence_builder
props:
  tokens:
    - { id: t1, text: "I" }
    - { id: t2, text: "would" }
    - { id: t3, text: "like" }
    - { id: t4, text: "an" }
    - { id: t5, text: "apple" }
    - { id: t6, text: "please" }
  placed: []
  target: "I would like an apple, please."
duration_s: 40
say:
  - "Now say the whole sentence. @question"
expect:
  kind: speech
  correct:
    - "I would like an apple please"
  fuzzy:
    - "I want an apple please"
    - "I would like a apple please"
    - "I would like an apple"
on:
  correct:
    goto: say_please
    say:
      - "Perfect English! @happy/Happy"
  near:
    goto: recast_sentence
    say:
      - "Very good, almost perfect. @happy"
  wrong:
    goto: help_sentence
    say:
      - "Good try. Listen to me once more. @curious"
  silence:
    goto: help_sentence
    say:
      - "Take your time. I will say it slowly. @think"
  timeout:
    goto: help_sentence
    say:
      - "I will say it slowly. @think"
```

## recast_sentence — RECOVERY

```yaml
scene: text
props:
  text: "I would like an apple, please."
  size: lg
duration_s: 10
say:
  - "Try it like this: I would like an apple, please. @curious"
goto: say_please
```

## help_sentence — RECOVERY

The Vietnamese rung of the ladder, and the only one in this file. It always ends
by going back to English.

```yaml
scene: text
props:
  text: "I would like an apple, please."
  size: lg
duration_s: 14
say:
  - "Con muốn một quả táo ạ. That is what we are saying. @neutral"
  - "In English: I would like an apple, please. @curious"
goto: say_please
```

## say_please — PRACTICE

A `pronunciation` board. It is not graded yet — the pronunciation service is not
built — so it is a timed choral drill with no `expect`.

```yaml
scene: pronunciation
props:
  word: please
  phonemes:
    - { symbol: "p",  status: pending }
    - { symbol: "l",  status: pending }
    - { symbol: "iː", status: pending }
    - { symbol: "z",  status: pending }
duration_s: 20
say:
  - "One word to practise: please. @neutral"
  - "Listen to the end: pleaZE. Say it: please. @curious"
```

## shop_roleplay — ROLEPLAY

`roleplay` has no `expect` on purpose: thirty children speaking at once cannot be
graded, and pretending otherwise would stall the lesson.

```yaml
scene: roleplay
props:
  environment: "a small market stall"
  aiRole: "the seller"
  studentRole: "the buyer"
  targetPhrases:
    - "I would like an apple, please."
    - "How much is it?"
    - "Thank you!"
duration_s: 60
say:
  - "Now we play the market. I am the seller, you are the buyer. @happy/Happy"
  - "Ask your partner: I would like an apple, please. @curious"
```

## explore_rice — EXPLORE

The `explore` board is where a word becomes a door (north-star §5). End on a
question, not a conclusion.

```yaml
scene: explore
props:
  topic: "Where does rice come from?"
  nodes:
    - { id: rice,   label: "rice", asset: "asset://market/rice.svg" }
    - { id: field,  label: "rice field" }
    - { id: river,  label: "the Mekong river" }
    - { id: world,  label: "the world" }
  focusId: rice
duration_s: 45
say:
  - "Rice grows in a field, and a field needs a lot of water. @curious"
  - "In the south, that water comes from the Mekong river. @neutral"
  - "Viet Nam sends rice to many countries. All that, in one small word. @surprised/Surprise"
```

## goodbye — WRAP

The last activity. Nothing follows it, so the lesson ends when its timer runs
out.

```yaml
scene: text
props:
  text: "apple · banana · rice · water · bread · egg"
  size: lg
duration_s: 15
say:
  - "Great work today! @happy/Happy"
  - "See you next time. Goodbye! @happy"
```
