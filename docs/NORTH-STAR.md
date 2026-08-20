# NORTH STAR (Bible)

> This is the root document. Every other technical decision must answer: *what
> does it serve here?* If another document contradicts this file, this file wins.
>
> **The bible does not track execution.** What is actually wired, and what to do
> next, lives in exactly one place: [STATE.md](STATE.md).

**Updated:** 2026-08-19
**Status:** direction locked — a real teacher agent (library + typed tools), not a lesson graph

**Standing doctrine:**

| | |
|---|---|
| [Option B runtime](decisions/option-b-classroom-runtime.md) | Hermes sidecar, Bright MCP as the only action boundary, Stage owns audio. Hosted model now; local Gemma later behind the same profile |
| [Teacher, not cassette](decisions/teacher-agent-not-cassette.md) | Hermes **is** the teacher. Core is the classroom OS — not a second teacher, not a tape player |
| [The room runs itself](decisions/2026-08-18-room-runs-itself.md) | The adult boots the appliance. No product buttons. The pulse opens the class |
| [Three stores](decisions/2026-08-18-three-stores.md) | Markdown is curriculum truth; SQL observations are student truth; authored markdown is relation truth. Nothing else |

---

## 1. Product thesis

We are **not** building:

- an English-learning chatbot with an avatar
- a personal English practice app (Duolingo / ELSA clone)
- a toy robot

We are building:

> **A teacher.**
>
> Not a teaching *tool* — a colleague-shaped thing that holds a period on its
> own. She knows the room, notices when someone arrives and greets them,
> knows when the lesson is, prepares before it, teaches it, judges what she
> saw, closes it, and gets ready for the next one. She runs fully offline on
> cheap hardware, remembers each learner by evidence, drives one shared
> board, and adapts to what the class actually does rather than to what a
> script predicted.

The shape of the thing is a **coding agent working in a repository**, and that
analogy is load-bearing rather than decorative:

| A coding agent | Bright's teacher |
|---|---|
| a large repo it did not write | a curriculum library: syllabus maps, keys, images, clips |
| reads a map, then opens the file it needs | `index.md` → unit `map.md` → `keys.md`, only when needed |
| a small set of typed tools that really act | 10 tools: read/search library, board, image, exercise, clip, **her own plan**, say, evidence |
| skills — reusable procedures it looks up | how to open a period, how to elicit, how to scaffold down |
| talks to a human directly | talks to a child directly |
| a harness that keeps running between tasks | a working day: prepare, teach, mark, prepare again |

If Bright only needed a fixed script plus a model that reads the next line
aloud, we would not run an agent harness at all. **We run one because teaching
is a profession, not a playlist.**

### Her anatomy

Everything she is made of, and the one rule that governs each part:

| Part | What it is | The rule |
|---|---|---|
| **Brain** | Hermes, running a small model — hosted now, local Gemma later | replaceable. The contract around it is not (NS-4) |
| **Hands** | 11 typed tools over MCP: read/search the library, board, image, exercise, clip, plan, evidence, call the adult, say | Core executes them and may refuse — and what Core hands her must be what Core accepts. She never touches a filesystem, a URL or the DOM (NS-3) |
| **Library** | the curriculum: unit maps, keys, practice, media | markdown is the truth. An index is disposable |
| **Skills** | how to do professional things — open, elicit, scaffold, judge, close, prepare | data, not code. Portable across every subject (NS-6) |
| **Playbook** | the active unit's map — what this period is for | a map she reads, never a graph she walks |
| **Memory** | what she knows about a learner, from recorded evidence | categorical facts, never a transcript (NS-5) |
| **Database** | Core's SQLite: observations, skills, sessions, the room's state | the source of truth. The context window is not |
| **Clock** | reflex ticks, the teaching pulse, and the day's timetable | Core owns time. She acts on it; she does not keep it |
| **Body** | Live2D on the Stage, lip-synced to her own speech | a body. Never a second brain |
| **Room** | one projected board, one speaker, one microphone | Stage is the only loudspeaker |

Two absences are as important as the parts:

- **There is no second agent.** Not inside the avatar, not inside perception, not
  as a "planner" behind the teacher. One brain (NS-1).
- **There is no lesson tape.** If the brain dies, the room stays, the adult is
  told, and the brain restarts. Nothing impersonates her.

English here is not a "chat feature." English is **an interactive environment**: listening, seeing, speaking, pointing, touching, playing, roleplaying, and exploring the world.

### The setting: an Intel competition; exact programme attribution must be verified

This is built as an Intel-focused competition entry. Earlier project notes described
it as an **Intel × United Nations** programme, but the official Intel festival page
reviewed on 2026-08-12 does not by itself establish UN co-ownership. Use the exact
organizer wording from the entry rulebook in every public claim. The Intel/local and
child-centred/global constraints below remain product requirements regardless of the
final event name, and they reorder two things:

**1. Running locally on Intel hardware is part of the argument, not a later phase.**

Phase 1 deliberately used a hosted model to take plumbing off the critical path, and that was right for building. (MiMo, then Gemini 3.7 Flash — both bridges, neither the destination.) But an entry to an *Intel* programme that calls a cloud API has thrown away its own strongest claim. **OpenVINO + Gemma 4 on an Intel edge device is the showcase**, and SP-1/SP-2 are promoted from background plumbing to part of the submission.

The architecture is ready for it: Bright calls the Hermes sidecar rather than a
provider endpoint. Hosted → local changes the pinned Hermes classroom profile
(`provider`, `model`, and `base_url`) plus deployment resources, not Core, MCP,
protocol, UI, or curriculum. What is missing is measured local-Gemma conformance.

**2. The UN framing makes "global" a criterion, not an ambition.**

Two things follow immediately, and both get more expensive the longer they wait:

- **The fallback language is currently hardcoded to Vietnamese** — the scaffolding ladder, the TTS voice, and an English-only STT model. It has to become configuration.
- **The avatar's licence.** Hiyori is Live2D Inc. sample material with commercial use restricted. Selling has a revenue threshold to hide behind; **donating at scale is distribution, and that threshold does not help.** Presenting a humanitarian product at a UN programme with a character we may not distribute is a real exposure. See [STATE.md](STATE.md) §9 and [PROMPT-avatar-decision.md](research/prompts/PROMPT-avatar-decision.md).

**3. A competition also judges what it can see.** Working software is necessary and not sufficient: the demo has to run reliably in a room full of strangers, and the claims have to be evidenced. That is why measurements live in the docs instead of adjectives.

---

### Why it exists

This is meant to be **given away**, not sold. The goal is that a child in a village with no teacher, no internet and no textbook can still learn — and through English, reach everything else. The population this is aimed at is on the order of **40 million children** in remote and under-resourced areas.

That intent is not decoration. It constrains engineering directly:

| Because it is donated, and global | The system must |
|---|---|
| No licence revenue, ever | Cost per classroom is the binding constraint, not margin. Every megabyte and every watt is somebody's budget |
| Deployed where nobody can support it | Survive with no IT, no network, no updates for months, and a power cut mid-lesson |
| Not only Vietnam | Treat the fallback language as **configuration**, never a hardcoded assumption. Vietnamese is the first, not the only |
| Given to institutions | Every dependency must be legally shippable at zero cost. "Free for now" is a liability, not a saving |
| A scale of 40M | One authored lesson has to serve very many children. Content **leverage** matters more than content volume |

**Vietnam is the first deployment, not the scope.** Where a decision would be cheaper by assuming Vietnam only, prefer the one that does not.

This also settles a question that kept resurfacing: *what is the bar for "done"?* Not "impressive in a demo." The bar is **switch it on and it teaches** — and it keeps doing that when everything around it fails.

### The AI is the teacher. The adult is support.

This is the target, stated plainly because it is easy to drift from:

> **The AI teaches the class.** A human is present and supports from outside the lesson — sets it up, handles the room, steps in if something goes wrong. They are not co-teaching, and the system must never *require* them to.

The distinction matters because it changes what has to be built. A tool that assists a teacher can leave gaps for the teacher to fill. An autonomous teacher cannot.

What autonomy actually demands is set out in §2. The short version: a system
that answers well when spoken to is a good chatbot. A teacher also **starts**
things — and that is the harder half.

**What stays true:** if the design needs an adult to decide the next teaching
move, it is wrong. If Hermes is down, restart Hermes — do not play a tape.

**And the human's console is not a co-pilot seat.** It is observability plus an emergency lever. If a design ever needs the adult to make a teaching decision for the system to work, that design is wrong.

### The one thing the adult *is* responsible for: safety

"Not a co-teacher" is not "not needed". The facilitator is the **safety authority
in the room**, and that is a role the system must never try to take.

The teacher stops teaching and hands control to the adult, immediately and
without trying to resolve it herself, on any of:

| | |
|---|---|
| physical danger, injury, or fighting | |
| a child in visible distress — crying, panic, withdrawal | |
| **any disclosure suggesting abuse, neglect, or a serious wellbeing concern** | she does **not** ask a follow-up question. She says *"Thank you for telling me. Please talk to [facilitator] now,"* and stops |
| equipment failure beyond one retry | |
| class-wide disengagement that pacing changes have not fixed | |

She never enforces discipline beyond a gentle verbal redirect (*"Let's listen
together!"*). Anything physical or behavioural is the adult's, exclusively.

Two properties of this list matter as much as its contents. **It is short** — a
teacher who escalates constantly is not autonomous either. And **it is
unconditional** — there is no confidence threshold, no "probably fine", and no
attempt to handle it well. Handing over badly is recoverable. Handling it badly
is not.

Everything else in this document is about a machine that teaches. This section
is about the one situation where the right behaviour is to stop being one.

---

## 2. The working day

Bright's design has so far modelled exactly one thing: **a turn.** A child says
something, the teacher answers. That is the easy half, and a chatbot can fake it.

A real teacher's day is larger than the turn, and every part of it that we do
not model is a part an adult has to perform instead:

```
BEFORE      She knows a lesson is coming. She looks at who is in this class
            and what they actually did last time, decides what today's period
            is for, and pulls the material she will need.

ARRIVAL     Someone comes into the room. She notices — and greets them.
            Not because a button was pressed. Because a person appeared.

THE PERIOD  She opens, teaches, watches, judges what she saw, adapts,
            and paces it. When the room goes quiet, she looks up.

CLOSE       She ends it herself, on time and kindly, whether or not the
            planned material is finished.

AFTER       She writes up what she saw as evidence, and that changes what
            she prepares next time.
```

**All five boxes now exist** (2026-08-19), and none of them needs a human to
hold it open: the presence gate opens the class, the nightly job prepares it,
`say(closing)` ends it, and evidence writes update what she prepares next. What
is still missing is not a box but a **timetable** — she prepares at 03:00 and on
demand, and wakes when someone appears, but nothing yet tells her *"class is at
nine."* Progress against each box: [STATE.md](STATE.md) §the working day.

### She is a process, not a function

The nearest familiar object is **a robot** — something that is simply *there*,
running, whether or not anyone is talking to it. But a robot in the usual sense
is a body executing a program. This is an **agent**: it decides what to do next
by reading its world, and the world is a library, a room, and a set of learners.

The distinction is architectural, not poetic:

| A function | A process |
|---|---|
| exists only while answering | exists all day |
| has no time of its own | has a clock and acts on it |
| starts when called | starts things |
| forgets between calls | carries a period forward, and a learner across months |
| failure = a bad answer | failure = *she is not there*, and someone must be told |

Everything in this document that sounds ambitious — greeting whoever arrives,
waking for a timetable, preparing before class — is the same single requirement
restated: **she has to be a process.** A very good request handler is still a
chatbot with a face.

### What she knows about a child

She should know each learner the way a real teacher does after a few weeks:
what they can do, what they are shaky on, and how they tend to work. That is
three different kinds of knowledge, and conflating them is how child-facing
products become creepy or wrong.

| Tier | Example | Where it lives | Who may write it |
|---|---|---|---|
| **1. Evidence** — what was observed | "said *banana* unprompted, in a picture she had not seen before" | `observations` rows | the teacher, through `record_evidence`, at the moment it happens |
| **2. Derived state** — what we therefore believe | "productive naming of *banana*: 2 of 3, last seen 9 days ago, never yet in a novel context" | computed from tier 1, deletable and rebuildable | nobody — it is a calculation |
| **3. Working preferences** — how this child tends to work | "answers after a picture, not after a question. Goes quiet for a while after being wrong" | recorded categorically, always traceable to tier 1 | the teacher, but only as an observation with instances behind it |

Tier 3 is what you meant by *đặc tính*, and it is the valuable one — it is the
difference between a teacher who has met you and one who has not. It is also the
dangerous one, so it has a hard boundary:

> **She may record how a child has behaved. She may never assign a child a
> character.**

"Needs a picture before producing a word" is a teaching observation: it is
specific, it changes what she does next, and a real teacher would say it out
loud to a colleague. "Shy", "lazy", "gifted", "slow" are labels — they follow a
child, they are unfalsifiable, and a model that writes them into a durable store
has done something no teacher is allowed to do. There is no confidence threshold
that makes it acceptable.

The operational rule is the same as everywhere else in this document: **if you
cannot point at the observations behind it, it is not knowledge about a child —
it is the model's opinion, and it does not get stored.**

**And tier 1 can be a lie.** Measured 2026-08-19: every observation the teacher
had ever recorded was `correct` + `mode=name` — including one for a child who
had said only "Hello", and one for a child who had said "I don't understand".
Coverage then reported the unit mastered and she stopped teaching it. Evidence
is now anchored to a turn Core witnessed and to a child who actually spoke, and
each row carries the real turn id so a false one is falsifiable afterwards
instead of unfalsifiable forever. What Core may and may not refuse is
[the witness line](decisions/2026-08-19-core-is-a-witness.md) — the short
version being that Core may testify *no act occurred*, never *the act was
insufficient*.

### Where she is up to

Mid-period, she must know where she is: which unit, which objective, what is on
the board, what she has already tried, who has answered and who has not. Today
that lives partly in Core's session state and, since 2026-08-19, as **`PLAN` —
the plan she wrote for the period herself**, in SQL. It replaced `BEATS`, a RAM
log Core kept *about* her from which she had to re-infer her own intention every
turn. Core stores the plan and hands it back; Core never reads it.

RAM is not good enough for a room where the power cuts. NS-5 says classroom
state lives in the database, and the consequence is a release gate we have not
met: **after Core restarts mid-period, she resumes the period rather than
starting a new one.** A teacher who forgets the last twenty minutes because a
cable was kicked is not a teacher anyone can rely on.

Note what this state is and is not. It is *"unit `market-food`, objective
`food-recognise-banana`, the picture is on the board, invited twice, not yet
produced."* It is **not** a transcript of what was said. The distinction is
NS-5, and it is what lets her resume without a chat log.

### Three clocks, not one

| Clock | Period | Who owns it | What it does | State |
|---|---|---|---|---|
| **Reflex** | < 100 ms | Core, deterministic | a tap highlights, audio starts, a timer ticks | ✅ built |
| **Turn** | seconds | the teacher pulse | someone spoke, or the room has been quiet long enough that a teacher would look up | ✅ built, unproven in a room |
| **Day** | minutes → hours | the scheduler | prepare the period before anyone arrives | ✅ built 2026-08-19 — `prepare_next` at 03:00, or `POST /teacher/prepare`. ⚠️ still fires on a fixed hour, not on a declared timetable |

The day clock was the missing organ, and it now runs: preparation happens
before the room fills, and it is the only place an offline 4B model is allowed to
be slow. What it still lacks is the **timetable** — it knows *how* to prepare,
not *when* class is. **A teacher who cannot begin anything is not autonomous,
however good her answers are**, and beginning is now half solved: she begins when
someone appears, not yet when the clock says nine.

### What autonomy demands

| Requirement | What it means concretely | Where we are |
|---|---|---|
| **Notices presence** | a person appears → she greets them. No button, no adult | ✅ the presence gate opens the class when the Stage claims the audio lease; an interrupted period is resumed, not re-greeted |
| **Knows the time** | a timetable in the deployment says when periods are; she wakes for them | ❌ nothing in the system knows what time class is |
| **Prepares before class** | reads the roster and prior evidence, picks the period's purpose, stages material — *before* anyone arrives | ✅ 2026-08-19. She reads the unit and the class's evidence and writes the period's plan; she cannot speak or reach the projector while the room is empty, [enforced in Core, not asked for in a prompt](decisions/2026-08-19-prepare-is-ours-not-hermes.md) |
| **Runs a whole period unattended** | paces it, handles the unscripted, closes it herself | ❌ **measured 2026-08-19 and worse than "unproven"**: with nobody answering she re-models the same three phrases, invents asset ids, and reaches for `close-a-period` having run out of ideas. She now has `NO_REPLY` to notice it and [a way to call the adult](decisions/2026-08-19-she-can-call-the-adult.md), which the doctrine has demanded from the start |
| **Judges and remembers** | categorical evidence per learner, not a transcript | ✅ built (`observations` → `SKILL_CARD`) |
| **Recovers on its own** | model death, bad tool call, lost I/O → notify + restart, keep the room | ⚠️ policy locked; restart path partly built |
| **Manages a class, not a learner** | fair callouts, attributed evidence, 20–40 children | ❌ Layer 5 |

### Preparation is where 40 million children are actually served

This deserves saying plainly, because it looks like a nice-to-have and is not.

A hosted turn costs seconds and the child is waiting. Anything the teacher can
work out **before** the room fills is free. Preparation is also the only place
where an offline 4B-class model is allowed to be slow — and therefore the only
place where it is allowed to be *thorough*: read the unit properly, look at what
this particular class struggled with, choose the pictures, decide the purpose of
the period.

That is how a small local model teaches like a much larger one. Not by thinking
faster in front of a child, but by having already thought.

---

## 3. Who the real user is

This constraint decides everything below it:

| | |
|---|---|
| **Learners** | 20–40 students per class, sharing one projected screen |
| **Operator** | one teacher/facilitator, **not** an engineer |
| **Network** | assume **no internet** |
| **Hardware** | see below — two targets, decided at different times |
| **Context** | under-resourced schools, low budget, no on-site IT |
| **Reach** | Vietnam first; the design target is remote and under-resourced classrooms anywhere |

### The class is the unit. 1:1 is scaffolding, not the target

One learner in a text window is the cheapest way to prove the agent teaches. It
is a **channel**, not the product. The product is a room with 20–40 children in
it, and that is a different problem: Pika is *1 child + 1 robot + at home*; ours
is *1 teacher + 30 children + 1 shared screen + offline.*

The danger is not that we start at 1:1. It is that 1:1 assumptions **accumulate
silently** and are then expensive to remove. Audited 2026-08-18, several already
have:

| Where | The assumption |
|---|---|
| `TeacherOS.learner_id: str` | a session has exactly one learner — a scalar, not a roster |
| **`record_evidence(objective_id, outcome, mode)`** | **the tool has no subject.** Core fills in the only learner there is. In a class this is unanswerable |
| `classId="bright-one-learner"` | hardcoded |
| `SKILL_CARD` / `PAST` | one learner's card, injected as *the* memory |
| `units/*/map.md` — *"One child."* | the curriculum itself is written for one |

The second row is the serious one, because it is a **contract** problem rather
than an implementation detail. Everything else is a variable that becomes a
collection. But a tool that cannot name who it is talking about does not become
multi-learner by adding students to a table — the schema, the memory injection
and the unit maps all have to change together, and every unit authored before
that change is written for the wrong classroom.

**Therefore, the standing rule:** when a choice costs about the same either way,
take the one that survives thirty children. Specifically —

- Evidence carries a **subject**, even while there is only ever one subject.
- Memory injected on a turn is **a roster view**, even when the roster has one row.
- A unit map describes **a class doing something**, not "one child".
- Fairness — who has been called on, who has not — is a first-class concern, not
  a Layer 5 feature. A teacher who only ever talks to whoever speaks loudest has
  failed even with one child in the room.

### Identity is the system's job, not the model's

A language model cannot recognise a face, and must never be asked to guess who
it is talking to. Perception answers exactly one question:

> **Which existing `student_id` is this — and how sure are we?**

It does **not** answer "what does this child know." The teacher receives an id
and, through it, that learner's recorded evidence. She never receives a face, an
image, an embedding, or a name she is expected to match to a person.

Three rules, binding from the first line of perception code:

1. **Uncertain identity means no student-memory write.** An observation with no
   confident subject is a classroom event, not a fact about a child. Losing a
   data point is cheap. Attributing a child's failure to a different child is not.
2. **Raw video is not stored by default.** Templates and embeddings are sensitive
   student data, subject to the same deletion rules as the rows they point at —
   embeddings are not anonymisation.
3. **Identity is bound before class, not inferred during it.** Enrolment is a
   deliberate, consented act. The camera then matches; it never enrols silently,
   and it is never shown on the projector.

This is the same boundary as NS-5, applied to perception: the system holds
identity, the agent holds pedagogy, and neither is allowed to invent the other's
truth.

### Two hardware targets

```
BUILD & DEMO  (now)        a developer laptop. Windows or Linux.
                           No RAM ceiling, no cost ceiling, no SKU decision.

PRODUCTION    (later)      a cheap box, decided AFTER we measure what the
                           finished system actually needs.
```

**Do not pick production hardware before the product exists.** Published Gemma 4 throughput numbers all come from premium Core Ultra silicon (18.5 tok/s on Arc 140V iGPU); the number for budget N-series does not exist publicly ([research](research/notes/2026-08-11-edge-stack-viability.md) §1). Choosing a SKU now means guessing at a workload we have not built.

The offline constraint still holds from day one — it is an *architectural* property, not a hardware one, and retrofitting it is expensive. The 16 GB figure remains the **design intent** that keeps us honest about footprint. It is not a demo constraint.

For contrast: Pika is *1 child + 1 robot + at home*. Our problem is *1 agent + 30 children + 1 shared screen + offline*. Their architecture does not transfer.

---

## 4. The non-negotiable principles

### NS-1 — The AI is the teacher. If the AI is down, teaching pauses and the AI restarts

Autonomy means **no human co-teacher**. It does **not** mean a compiled
`lesson_run.json` impersonates the teacher when Hermes is dead. That cassette
was the 2026-08-16 correction: it inverted the product and made Hermes
optional garnish.

During class:

- **Hermes healthy** → it teaches from the curriculum library (maps, then deeper files)
- **Hermes slow or dead** → Core keeps the room (board, session, last visual),
  tells the facilitator, and restarts the sidecar. Resume from the OS snapshot.
  Do not walk an authored graph.

Classroom Core is the **classroom OS** (I/O, clock, persistence, safety, restart).
It is not a second teacher. `lesson_run.json` is not the lesson.

**The ordering principle** (the layer-by-layer sequence lives in
[STATE.md](STATE.md), which is allowed to change; this principle is not):

```
1. THE AGENT TEACHES   Hermes + library + typed tools. One learner, text first.
2. THE ROOM SERVES     board, session, DB, health/restart. Hands, never pedagogy.
3. THE CHANNELS OPEN   voice, body, a class of 20–40, a local model.
                       Same agent. New I/O. No new brain.
```

When in doubt, the next task is whatever makes **Hermes able to teach from the
library** — not whatever makes the LLM-free tape more complete, and not whatever
adds a second way for the room to think.

### NS-2 — Two control tiers, never mixed

Gemma 4 E4B scores **42.2%** on Tau2 (agentic tool-use benchmark). That is the real number from the model card. It is **not reliable enough** to sit in a reflex loop.

```
REFLEX TIER  (< 100 ms)         PEDAGOGY TIER  (seconds)
──────────────────────────      ────────────────────────────
Deterministic code              Hermes + Gemma 4 E4B
No LLM                          LLM in the loop

student points → highlight      decide what to teach next
drag & drop cards               retrieve a rubric or a new example
timer tick / audio start        recast, scaffold, or change the task
                                update belief about a student
```

**Never** route a student gesture through the LLM before something happens on
screen. Reflex is I/O. Pedagogy is the agent. Core must not smuggle pedagogy
into the reflex tier as a `goto` graph.

### NS-3 — The agent acts on semantics, never on the DOM

The agent does **not** generate HTML. It does **not** call `eval()`. It does not know CSS exists.

The live agent uses a **small typed tool set** against the library and the
room, the way a coding agent uses read/search/edit/run against a repo. There are
eleven, and adding a twelfth requires a decision doc:

```
read_library    search_library   → maps, units, keys, asset:// ids
read_board      write_board      → the chalkboard: short markdown, never HTML
show_image      show_exercise    → asset:// ids only, never a path
play_clip
plan                             → HER plan for the period; Core stores, never reads
say(wake_in_s)                   → she asks the room for her own next beat
record_evidence                  → categorical memory, never raw chat
call_the_adult                   → stop teaching, hand the room to a person
say                              → one teacher line; ends the turn
```

**A tool is one independently-refusable intent.** Anything Core can refuse — a
missing asset, a malformed exercise, a script the classroom does not read — gets
its own tool, so a refusal costs one move and never the turn. `say` is the tool
that must never fail: with flat tools a malformed `show_image` still lets her
speak and the lesson limps forward, while one merged tool means a bad sub-field
kills the speech too — in a room with no adult in it, a teacher standing silent
in front of children.

So anything riding on `say` must degrade rather than fail. `say` may carry the
line, booleans about the line (`closing`, `awaiting_answer`), and at most one
degrade-on-invalid content field: `board_text`, the chalk. **The day a field on
`say` can cause `ok: false` for any reason other than `teacher_line`, or gains
type object/array, or names an `asset://`, the merged tool is being rebuilt one
flag at a time.** [Why, with measurements.](decisions/2026-08-19-flat-tools-and-bundling.md)

Everything the agent touches is named semantically. It never sees a file path,
a URL, a DOM node, or CSS. Core resolves `asset://` ids to disk and rejects an
id that does not exist.

Core executes side effects and may reject an illegal call. It does **not**
hand the agent a multiple-choice menu of authored `goto`s and call that
teaching. `classroom_propose_move` as the only live tool is retired.

The agent does not name CSS or generate HTML. Stage owns rendering. Stage
owns speakers. AIRI is a body. The 2026-08-16 “authored narration fallback”
is deleted — if Hermes is down, restart it.

Older architecture notes that still describe a one-tool cassette are stale;
this section wins.

### NS-4 — The runtime is replaceable; the contract is not

The live runtime pins `hermes-agent 0.20.0+bright.2` to upstream commit
`03fa32c92dd445eb64c7f67434dd91b32c40701d`. Hermes is young and fast-moving;
if it stops fitting, we must be able to swap it in days, not rewrite the product.

Therefore **our actual assets** are:

1. `classroom-mcp` — the semantic tool contract
2. `classroom-core` — state machine + event bus + source of truth
3. `content/` — curriculum, lessons, media
4. `data/` — student model, skill estimates
5. `evals/` — the measurements that tell us which model is usable

Hermes, AIRI, and OpenVINO are all *swappable*. Those five are not.

### NS-5 — Chat history is not the source of truth

Classroom state lives in `classroom-core` (a schema'd DB), not in a model's context window. The model is *shown* state; it does not *own* state.

Consequence: restarting the agent mid-class does not lose Core's live lesson state.
**Implemented 2026-08-19:** the presence gate re-attaches to an open session and
tells her to look up rather than greet a class she is already teaching. Bounded
to two hours — a session left open on Tuesday is abandoned, not interrupted.

#### What she heard, and what she thinks it meant, are two different records

Bright owns unusually strong context: the unit's vocabulary, what is on the
board, the exercise she just put up, the question she just asked. That context
may inform how a response is **interpreted**. It must never rewrite the
**transcript**.

The failure this forbids is specific and quiet. A decoder biased toward the
curriculum hears a child fumble and writes down the word the lesson expected —
and then evidence of mastery exists for something the child never said. The
child is marked as knowing it, the teacher moves on, and nobody finds out.

So: keep the raw transcript as the raw transcript. Interpretation is a separate
step with a separate name, and where the two disagree, the disagreement is the
information — it is how you learn a child is struggling.

### NS-6 — The profession is data, not code

Teaching knowledge lives in **skills**: short authored documents, discovered by
name, opened when relevant. Never in Python, never in a state machine, never in
a prompt constant.

A skill is *how* to do one professional thing:

```
open-a-period        how to start with a stranger, and with someone you know
elicit-a-word        get them to say it, don't just show it
scaffold-down        the ladder: simpler → picture → example → home language
judge-a-response     what counts as evidence, and what only looks like it
recover-a-wobble     they are lost, embarrassed, or bored
close-a-period       end on time and kindly, finished or not
prepare-a-period     what to do before anyone arrives
```

The line that must not blur:

> **Skills are the profession — portable across every subject.
> Library units are the curriculum — what is being taught today.**

Both are markdown. Neither is code. Consequences that are binding:

- **Adding a subject adds files, never code.** If teaching maths needs a new
  Python branch, the design is wrong. `tests/test_no_unit_pedagogy.py` exists to
  make that failure loud.
- **Skills load progressively.** Names and one-line descriptions are cheap and
  always present; a skill's body is read only when it is relevant.
  **Measured 2026-08-19: "when the teacher decides it is relevant" did not
  work.** Across a whole period she opened the index and not one skill body,
  through two separate prompt instructions telling her to — because choosing
  which one applies is exactly the judgement a small model will not spend while
  a child is waiting. Core now *names* one in `READ_NOW`, selected by a
  **witnessed event** (a period opening, an answer arriving), the same way it
  already names `keys.md`. Core reads not a word of what is inside, so this is
  path resolution and not pedagogy. Without it NS-6 is decorative: 490 authored
  lines nothing ever reads — the same discipline as reading a file in a repo instead of pasting
  the whole repo into context. A 4B-class model cannot hold a profession in its
  system prompt, and should not have to.
- **A skill is authorable by a teacher, not an engineer.** That is the whole
  point at a scale of 40 million: the people who know how to teach must be able
  to improve the teacher without a build step.
- **Skills are versioned and reviewable.** A wrong skill is a wrong teacher in
  every classroom that syncs it.

Today the entire profession is one file, `content/library/how-to-teach.md`. It is
the seed of this system and it does not survive a second subject. The layout is
locked in [teacher skills](decisions/2026-08-18-teacher-skills.md).

#### The four layers of authored knowledge

Everything the teacher knows that was written by a person sits in exactly one of
these. Nothing sits in code.

| Layer | Answers | Scope | In context |
|---|---|---|---|
| **Conduct** | who she is, how she treats a child, which languages she mixes | every subject, every lesson, forever | always |
| **Skills** | *how* to do one professional thing — open, elicit, scaffold, judge, close, prepare | every subject | index always; body on demand |
| **Playbook** (unit map) | *what* today's period is for, and in what order | one unit | when that unit is active |
| **Keys** | what counts as a correct response, and what only looks like one | one unit | when she needs to judge |

Conduct and skills are the **profession**. Playbooks and keys are the
**curriculum**. A new subject ships playbooks and keys and — at most — a small
pack of subject-specific skills. It never ships code.

#### General first, optimised second

English is the first subject and it will be the best one. That is a sequencing
decision, not an architectural one, and the order matters:

> **Build it general, then optimise the first subject.
> Never optimise first and generalise later** — that direction does not exist in
> practice, because by then the specialisation is load-bearing.

Every optimisation for English must therefore land in a place that a maths
lesson can simply not use, rather than in a place a maths lesson has to fight:

| An English optimisation belongs in… | It must never land in… |
|---|---|
| a unit playbook, or a key | Core, the MCP tool schema, or the wire protocol |
| an English-specific skill pack | the general skills that every subject reads |
| a pronunciation asset or clip | the board, the pulse, or the evidence schema |

**The generality test**, to be applied before writing anything:

> *Read it back with "maths" or "geography" substituted for "English". Does it
> still make sense — or is it merely harmless?*

If it breaks, it is in the wrong layer. If it is merely *unused*, that is fine —
a maths teacher who never opens `pronunciation-drill` has lost nothing.

This is the whole reason Bright is an agent and not a lesson player. An agent
gets skills, playbooks, tools and a library — four places where a new subject can
land as **files**. A lesson player gets a state machine, which has exactly one
place a new subject can land: a rewrite.

### NS-7 — The deployment declares itself; software never names a language or a subject

The word "Vietnamese" must not appear in a decision the software makes. Neither
must "English", "market-food", or a school's timetable.

A deployment is declared in one place and read by everything:

```
home_language     the child's mother tongue      (H'Mông, Dao, Tày, …)
school_language   the shared classroom language  (vi)
target_language   what is being taught           (en)
units             which curriculum is installed
timetable         when periods happen
roster            who is in this room
```

**Three languages, not two — corrected 2026-08-18.** The learners this is built
for speak an ethnic-minority language at home, Vietnamese as a functional second
language, and English as a third. Treating Vietnamese as "the mother tongue" is
an error we had baked in, and it has a real pedagogical consequence: the bottom
rung of the scaffolding ladder may not land, because the rung we fall back to is
not the language the child thinks in either. Say that honestly rather than
discover it in a classroom.

`content/library/index.md` already declares the two languages and says so
explicitly: *"Software must not hardcode them."* The pedagogy honours it. **The
machinery does not yet** — the TTS picks a voice by counting accented letters and
the ASR model is English-only. That is a real, currently-shipping violation, not
a future concern.

The test: to run Bright in a Lao school teaching English, or in a Vietnamese
school teaching maths, **someone should change declarations and add files.**
If they must change code, we have failed the 40-million target — not
philosophically, but logistically. There is no engineer in that village.

---

## 5. Locked stack

```
              Hosted model now / Gemma local later
                    behind Hermes profile
                            │
                            ▼
                   HERMES SIDECAR ─ teacher brain
                   narrow live profile; broader authoring later
                            │
                     Classroom MCP        ◄── our contract
                            │
                            ▼
                   CLASSROOM CORE         ◄── classroom OS
                   session · bus · I/O · restart
                   (not a teacher)
                            │
        ┌───────────────────┼───────────────────┐
        ▼                   ▼                   ▼
   Learning Stage      Perception           Speech
   (React board)       camera/face/hand     VAD·STT·TTS·Pronunciation
        │
        └── AIRI (avatar, lipsync, animation)
                            │
                            ▼
                       PROJECTOR
```

**OpenClaw is not in the runtime.** Full reasoning in [01-decision-hermes-vs-openclaw.md](decisions/hermes-over-openclaw.md). It stays in `references/` as a pattern source.

Each component, in one line:

| Component | Role |
|---|---|
| **Hosted model now; local Gemma later** | raw reasoning capability behind the Hermes provider profile |
| **Hermes** | the live cognitive sidecar; broader planning/authoring profiles stay separate from the classroom trust domain |
| **Classroom MCP** | the world the agent is allowed to act on |
| **Classroom Core** | the classroom OS — I/O, clock, DB, safety, restart. Not a teacher |
| **Learning Stage** | the interactive board, the class's shared stage |
| **AIRI** | the agent's body |
| **Curriculum + Student DB** | purpose and continuity |

---

## 6. Pedagogical philosophy

### Scaffolding — do not fall back to the home language immediately

```
explain in the target language
      ↓ still lost
simpler target language
      ↓ still lost
image / gesture
      ↓ still lost
concrete example
      ↓ still lost
school-language hint
      ↓ still lost
school-language explanation
      ↓ still lost
home-language support — where the deployment can provide it at all
```

The goal is for students to gradually **think in the target language**, not
translate in their heads. Each rung is a separate move, so the teacher only goes
as far down the ladder as the child actually needs — and then climbs back up in
the same breath.

Written this way on purpose (NS-7): the ladder is a *professional* procedure, so
it belongs in a skill and reads the same in a Lao classroom as in a Vietnamese
one. Today it is `vi`→`en`. Nothing about the ladder knows that.

### EXPLORE mode — English as a window onto the world

A student learns `penguin`. The agent does **not** stop at "penguin = chim cánh cụt."

```
penguin → Antarctica → ice → ocean → climate
```

This is the philosophical break from every English-practice app: we are not teaching vocabulary, we are using vocabulary to open the world. For students in under-resourced schools this is the real value — **getting out of the bottom of the well**.

### Lesson flow

```
HOOK → INPUT → GUIDED PRACTICE → RETRIEVAL → INTERACTION
     → PRODUCTION → ROLEPLAY → EXPLORE → EXIT CHECK
```

The agent may route dynamically between these stages by reading the unit map
and the learner’s evidence. It is **not** confined to a compiled
`lesson_run.json` graph.

### What "personalised" means here — and what it does not

This is the most abused word in education technology, so it is defined narrowly
and the definition is binding.

| It **does** mean | It does **not** mean |
|---|---|
| she reviews what you actually *said* versus what you only *pointed at* | a mastery percentage, or a probability with a decimal point |
| she does not re-drill a word you produced correctly ten minutes ago | a "learning path" generated for you by a model |
| she picks the next thing from the unit map plus your evidence | a profile the model invented from things you said |
| she opens a returning session by revisiting what you were unsure of | a recommendation engine, or a difficulty score |
| a teacher would recognise every judgement she makes | anything that cannot be traced to a recorded observation |

The rule underneath: **every personalised behaviour must be explainable from
evidence a teacher would accept.** "She asked you about `banana` again because
you pointed at it but never said it" is a good reason. "The model felt you were
weak on fruit" is not a reason at all.

This is also why we refuse knowledge-tracing models at this stage
([three stores](decisions/2026-08-18-three-stores.md)): a confident-looking
number over four observations is worse than an honest "not yet seen".

### Adaptive, customised, personalised, flexible — kept distinct

Four words that get used interchangeably and mean four different things here:

| Word | Whose it is | Where it lives |
|---|---|---|
| **Adaptive** | this moment | she changes course from what just happened in the room |
| **Personalised** | this learner | evidence in `observations`, across sessions |
| **Customised** | this deployment | declared languages, timetable, roster, installed units (NS-7) |
| **Flexible** | this profession | skills, portable to a new subject with no new code (NS-6) |

A system can have all four or any one. Bright needs all four, and confusing them
is how a project ends up building a recommendation engine when it needed a
timetable.

---

## 7. Definition of success

This system succeeds when:

1. A facilitator who cannot code plugs it in, turns it on, and the **AI** teaches
2. She **starts things herself** — greets whoever arrives, wakes for her own
   timetable, and prepares before the room fills
3. After local Gemma (Layer 6), the same teacher still works with the network
   cable pulled
4. Students are known over time by semantic evidence, not by a chat log
5. When the agent fails, the room stays up, the adult is told, and the AI restarts
6. A new subject, or a new pair of languages, ships as **files** — no code change
7. Hardware cost is within reach of an under-resourced public school

Any feature that does not serve those seven gets cut.

### What "production grade" has to mean at this scale

Adjectives are not evidence. At 40 million children, "world class" cashes out as
five measurable properties, and nothing else:

| Property | The test |
|---|---|
| **Survives the room** | power cut mid-period → boots back into the same open session, not a blank screen |
| **Survives the year** | no internet, no updates, no IT visit for months, and it still teaches |
| **Repairable by one person** | someone carrying one USB stick can restore it. Every daemon and every independently versioned index is a tax on that person |
| **Legally shippable** | every dependency, model weight and avatar asset redistributable at zero cost. "Free for now" is a liability |
| **Honest under inspection** | every claim in these docs traceable to a measurement or marked as unproven. A number with no method behind it is a defect |

---

## 8. What we will NOT do

- ❌ No agent-generated arbitrary HTML/JS
- ❌ No gesture/click inside the LLM loop
- ❌ No raw transcripts as long-term memory
- ❌ No real learner identity or prior raw transcripts sent to a hosted model
- ❌ No second physical audio owner; only the Stage may play classroom speech
- ❌ No stacking two agent runtimes ([why](decisions/hermes-over-openclaw.md))
- ❌ No internet dependency on any primary path
- ❌ No pronunciation scores like `83.716253%` before calibration
- ❌ No raw video of students stored by default
- ❌ No pedagogy in Python — a subject or a teaching move that needs new code is a design failure (NS-6)
- ❌ No language, subject or school named inside software (NS-7)
- ❌ No invented mastery number, learning path, or profile the model wrote about a child
- ❌ No adult decision on the critical teaching path — including pressing a button to begin

---

## Navigation

**Next:** [STATE.md](STATE.md) — what is wired, what to do next, how to prove it.

| Doc | Contents |
|---|---|
| [decisions/](decisions/) | Every locked choice, dated, append-only. Read one before re-litigating it |
| [teaching loop](design/teaching-loop.md) | The workflow: the day, one turn, the board, and the failure doctrine |
| [tool surface](design/tool-surface.md) | Her hands: what teaching requires, and what she deliberately never gets |
| [architecture](design/architecture.md) | Detailed architecture, tool contract, event bus |
| [runtime topology](design/runtime-topology.md) | Two screens, one backend, boot sequence, appliance |
| [reusing AIRI](design/reusing-airi-and-friends.md) | What to reuse from the three cloned repos |
| [`PROTOCOL.md`](../packages/contracts/PROTOCOL.md) | The wire contract. Lives with the code so it cannot drift |
| [research/](research/) | Evidence, not doctrine. A finding becomes doctrine only when a `decisions/` file adopts it |
| [archive/](archive/) | Superseded. Kept for provenance. Never cook from it |
