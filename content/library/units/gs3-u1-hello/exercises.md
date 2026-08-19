# Exercises — Hello, Lesson 1

**Each block below is exactly the arguments for `show_exercise`, minus
`turn_id`.** They are flat: every field sits at the top level, because a
nested object came back empty from the model every single time. Copy one whole and send it — do not unwrap it, do not rename
anything. A block that has been retyped from memory is a wasted round-trip a
child sits through.


Concrete `show_exercise` payloads for material on pages 10–11. This is what
each activity **is** — its prompt, its options, which option is correct, which
recording goes with it. It is not a running order: the numbers below are the
book's own printed labels for these activities, used here only so you can
find the one you want. `map.md` and the skills decide what to do with any of
this and when.

Every asset and audio id used here is also listed in `map.md`'s Material
table.

## Characters — vocabulary

The four children's names against their faces.

```json
{
  "kind": "vocabulary",
  "items": [
    {
      "id": "ben",
      "text": "Ben",
      "asset": "asset://gs3/panels/char-ben.jpg"
    },
    {
      "id": "mai",
      "text": "Mai",
      "asset": "asset://gs3/panels/char-mai.jpg"
    },
    {
      "id": "minh",
      "text": "Minh",
      "asset": "asset://gs3/panels/char-minh.jpg"
    },
    {
      "id": "lucy",
      "text": "Lucy",
      "asset": "asset://gs3/panels/char-lucy.jpg"
    }
  ]
}
```

## ex.1 — Look, listen and repeat — vocabulary

The two model exchanges printed on the page, each with its speech bubbles.
Recording: `asset://gs3/audio/track-05.mp3`.

```json
{
  "kind": "vocabulary",
  "items": [
    {
      "id": "a",
      "text": "Ben & Mai",
      "asset": "asset://gs3/panels/u1l1-dialogue-a.jpg"
    },
    {
      "id": "b",
      "text": "Minh & Lucy",
      "asset": "asset://gs3/panels/u1l1-dialogue-b.jpg"
    }
  ]
}
```

## ex.2 — Listen, point and say

The same two pairings as ex.1, printed without the speech bubbles — the
picture-only version, for production with less scaffolding. It is the panel
`asset://gs3/panels/u1l1-listen-point-options.jpg`, already in the Material
table above, or ex.1's two items with the words covered. It needs no separate
exercise definition. Recording: `asset://gs3/audio/track-06.mp3`.

## ex.3 — Let's talk — roleplay

The free-practice scene: one child on a bench, one child arriving at school,
both speech bubbles blank.

```json
{
  "kind": "roleplay",
  "environment": "the path to school, by the gate",
  "ai_role": "the child on the bench",
  "student_role": "the child arriving at school",
  "target_phrases": [
    "Hello. I'm [name].",
    "Hi. I'm [name].",
    "Hello, [name]. I'm [name].",
    "Hi, [name]. I'm [name]."
  ]
}
```

Objectives in play: `greet-and-name`, `answer-a-greeting`.

## ex.4 — Listen and circle

Two listening items. Each is a choice between two character pairs — only one
pair is the one on the recording, the other substitutes a look-alike from the
wrong pairing. Recording: `asset://gs3/audio/track-07.mp3`.

### Item 1

```json
{
  "kind": "choice",
  "prompt": "Which pair is speaking?",
  "options": [
    {
      "id": "a",
      "asset": "asset://gs3/panels/u1l1-ex4-item1-a.jpg"
    },
    {
      "id": "b",
      "asset": "asset://gs3/panels/u1l1-ex4-item1-b.jpg"
    }
  ],
  "correct_id": "b"
}
```

Option b is Minh and Lucy — brown hair, no glasses, next to the orange-haired
girl. Option a substitutes a bespectacled, orange-haired boy who matches Ben,
not Minh.

### Item 2

```json
{
  "kind": "choice",
  "prompt": "Which pair is speaking?",
  "options": [
    {
      "id": "a",
      "asset": "asset://gs3/panels/u1l1-ex4-item2-a.jpg"
    },
    {
      "id": "b",
      "asset": "asset://gs3/panels/u1l1-ex4-item2-b.jpg"
    }
  ],
  "correct_id": "a"
}
```

Option a is Ben and Mai — the bespectacled boy next to the dark-haired girl.
Option b substitutes an orange-haired girl who matches Lucy, not Mai.

Both `correct_id`s were checked against the recording, not guessed from the
pictures alone: track-07 names Minh and Lucy in item 1, then Ben and Mai in
item 2, matching the character portraits' hair colour and glasses against
`char-ben.jpg` / `char-mai.jpg` / `char-minh.jpg` / `char-lucy.jpg`.

## ex.5 — Look, complete and read

Four picture-prompted fill-ins, same locked language, same four characters.
No new option set — it draws on the "Characters" vocabulary item above.

## ex.6 — Let's sing

The whole-class close. The lyrics panel and the recording are already in the
Material table (`u1l1-song-hello-lyrics.jpg`, `track-08.mp3`); it needs no
separate exercise definition.
