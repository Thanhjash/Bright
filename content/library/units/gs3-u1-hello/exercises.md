# Exercises — Hello

Every lesson of this unit, in the order the book prints them. `map.md` decides
which period you are in and therefore which section below is yours; nothing
here is a running order.

**Each block below is exactly the arguments for `show_exercise`, minus
`turn_id`.** They are flat: every field sits at the top level, because a
nested object came back empty from the model every single time. Copy one whole and send it — do not unwrap it, do not rename
anything. A block that has been retyped from memory is a wasted round-trip a
child sits through.


Concrete `show_exercise` payloads for the whole unit — pages 10–15. This is what
each activity **is** — its prompt, its options, which option is correct, which
recording goes with it. It is not a running order: the numbers below are the
book's own printed labels for these activities, used here only so you can
find the one you want. `map.md` and the skills decide what to do with any of
this and when.

Every asset and audio id used here is also listed in `map.md`'s Material
table.

**Lessons 2 and 3 carry no panels of their own** — only whole-page scans, and a
whole page is unreadable from the back of a room. So their checks are built from
words and from the character portraits, which is what the recordings test
anyway: whether the class can hear the difference.

---

# Lesson 1 — Hello, I'm …

Pages 10–11.

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

---

# Lesson 2 — How are you? Goodbye

Pages 12–13. Objectives in play: `ask-wellbeing`, `answer-wellbeing`,
`take-leave`.

## The exchange — vocabulary

The two halves of the wellbeing exchange and the two ways to leave, as cards.
Put it up while you model, so the words are in front of them during the choral
rounds. Recording: `asset://gs3/audio/track-09.mp3`.

```json
{
  "kind": "vocabulary",
  "items": [
    { "id": "ask", "text": "How are you?" },
    { "id": "answer", "text": "Fine, thank you." },
    { "id": "leave", "text": "Goodbye." },
    { "id": "leave-short", "text": "Bye." }
  ]
}
```

## ex.1 — Listen and point

The wellbeing exchange again, to listen and follow. It is `track-09`'s content
re-heard without the words up — use the vocabulary block above and take the
cards down, or put up a character portrait and let the recording carry it. It
needs no separate exercise definition. Recording:
`asset://gs3/audio/track-10.mp3`.

## ex.2 — Listen and choose the answer

What comes back when Mai is asked how she is. One item, two options, both in
the unit's locked language so a wrong choice is a real confusion between the
greeting and the answer — not a guess between an English sentence and a
nonsense one. Recording: `asset://gs3/audio/track-10.mp3`.

```json
{
  "kind": "choice",
  "prompt": "How does Mai answer?",
  "options": [
    { "id": "a", "text": "Fine, thank you." },
    { "id": "b", "text": "Hello. I'm Mai." }
  ],
  "correct_id": "a"
}
```

Option b is the Lesson 1 answer to a different question. A class that picks it
has heard the words and not the question, which is what `scaffold-down` is for.

## ex.3 — Which one is it?

Four short dialogues on the recording; the class tells meeting from parting.
Run it once per dialogue, re-showing this block each time. Recording:
`asset://gs3/audio/track-11.mp3`.

```json
{
  "kind": "choice",
  "prompt": "Are they meeting, or saying goodbye?",
  "options": [
    { "id": "a", "text": "Meeting — Hello." },
    { "id": "b", "text": "Saying goodbye — Bye." }
  ],
  "correct_id": "a"
}
```

The answer changes with the dialogue: send `correct_id` as `a` for the two
meeting dialogues and `b` for the two parting ones. Nothing on the board tells
the class which item is running, so say which one it is.

## ex.4 — On the way to school — roleplay

The four-turn exchange, and this is the task cycle — the longest part of the
period. Take one role yourself and give the class the other; when the room has
one child, this is the pair.

```json
{
  "kind": "roleplay",
  "environment": "on the way to school",
  "ai_role": "a friend walking to school",
  "student_role": "a child on the way to school",
  "target_phrases": [
    "Hello. I'm [name].",
    "How are you?",
    "Fine, thank you.",
    "Goodbye.",
    "Bye."
  ]
}
```

Objectives in play: `ask-wellbeing`, `answer-wellbeing`, `take-leave`.

---

# Lesson 3 — Put it together

Pages 14–15. Objectives in play: all of them, plus `hear-h-and-b`.

## The two first sounds — vocabulary

Sound awareness, not pronunciation marking: the hand near the mouth for **h**,
lips together then open for **b**. Recording:
`asset://gs3/audio/track-12.mp3`.

```json
{
  "kind": "vocabulary",
  "items": [
    { "id": "h", "text": "h — hello" },
    { "id": "b", "text": "b — bye" }
  ]
}
```

## ex.1 — Hello or Bye?

Which of the two words the recording said. Run it once per item, re-showing
this block and sending the `correct_id` that matches what plays. Recording:
`asset://gs3/audio/track-13.mp3`.

```json
{
  "kind": "choice",
  "prompt": "Which word did you hear?",
  "options": [
    { "id": "a", "text": "Hello" },
    { "id": "b", "text": "Bye" }
  ],
  "correct_id": "a"
}
```

## ex.2 — The chant

The whole exchange with the rhythm, so it is automatic before free practice.
The recording is already in the Material table
(`asset://gs3/audio/track-14.mp3`); it needs no separate exercise definition.
Put the exchange on the board with `write_board` and chant it with them.

## ex.3 — A visitor comes — roleplay

The full exchange with a real reason to use it, and the unit's exit is judged
here: three appropriate turns in a pair, understandable, and perfect
pronunciation is **not** required.

```json
{
  "kind": "roleplay",
  "environment": "the school gate, a visitor arrives",
  "ai_role": "a visitor to the school",
  "student_role": "a child meeting the visitor",
  "target_phrases": [
    "Hello. I'm [name].",
    "Hello, [name]. I'm [name].",
    "How are you?",
    "Fine, thank you.",
    "Goodbye."
  ]
}
```

Objectives in play: all of them.

## ex.4 — Review

Oral, and a few volunteer pairs if they want to. It draws on the roleplay above
and the Lesson 1 character cards; it needs no separate exercise definition.
