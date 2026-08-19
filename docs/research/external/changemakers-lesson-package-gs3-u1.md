# Teammate input — HERMES Multimodal Teaching Package, GS3 Unit 1

**Received 2026-08-19** from the Changemakers teammate (not an AI engineer —
read this as a *teaching* specification, not an engineering one). Stored here so
it does not have to be re-sent. Source folder: `Changemakers - Inputs/`.

> **Status: research, not doctrine.** Per `docs/research/README.md`, a finding
> becomes doctrine only when a `decisions/` file adopts it. Most of the teaching
> content below is already adopted, in `content/library/units/gs3-u1-hello/`.
> The engineering sections are **not** adopted, and §3 says why.

---

## 1. What is already in the library, and matches

The unit map, keys, practice and exercises were authored from the same textbook
pages and agree with this package on essentially all of the pedagogy:

| Package | Where it lives now |
|---|---|
| unit contract, primary outcome, success criterion | `map.md` → *"What a child can do at the end"* |
| locked vocabulary bank | `map.md` → *"Locked language"* |
| canonical final dialogue | `map.md` → *"The full exchange, once assembled"* |
| "do not teach *What's your name?*" | `map.md`, stated with the reason |
| asset manifest, image + audio mapping | `map.md` → *"Material"*, as `asset://` ids |
| "show a crop, not a full page" | `map.md` → *"Show a panel, not a page"* — 16 panels cropped |
| pre-task → task cycle → post-task, task cycle longest | `map.md` → *"The three periods"* |
| 4s wait, 2–3 choral rounds, 2 items / 10 min | `map.md` → *"Pacing"* |
| "do not advance on elapsed time if the class has not tried" | `map.md`, verbatim in spirit |
| choral first, individual second; invite, never force | `how-to-teach.md` |
| no public score, no ranking, no marks announced | NORTH-STAR §6, enforced in `show_exercise` |
| escalation list (danger, distress, disclosure, equipment) | NORTH-STAR §1 *"The one thing the adult is responsible for"* |
| facilitator messages in Vietnamese, teaching in English | `scripts/watch-teacher.sh`, `/teacher/status` |
| consent + Nghị định 13/2023/NĐ-CP for face/voice | NORTH-STAR §3 *"Identity is the system's job"* |

## 2. One real conflict — the wellbeing answer

| | |
|---|---|
| Package | **"I'm good, thank you."** |
| Our `map.md` | **"Fine, thank you."** — *"that is what the recordings say and what is printed on the page. Do not teach a different wording; the class will hear the contradiction."* |

Both cannot be right in a room where Track 9 is played out loud. **Unresolved —
needs the teammate to check the printed page and the recording.** Whichever wins,
it changes one row of `map.md` and one row of `keys.md`, and no code.

## 3. What is deliberately NOT adopted, and why

### 3.1 The state machine (§7.2)

```
state_order: STARTUP_CHECK → PRE_TASK → TASK_BRIEF → TASK_PRACTICE
             → CHECK_UNDERSTANDING → POST_TASK → MEMORY_WRITE → END
```

This is the cassette NS-1 deleted on 2026-08-16, and the owner restated it:
*"không có statemachine, t cần pure agent."* A fixed state order cannot do the
thing the same package asks for two lines later — *"do not advance because time
elapsed if most of the class did not attempt the target phrase"* — because
deciding that requires judgement, which is exactly what a state machine has none
of.

**How the same intent is met instead:** the phases live in `map.md` as a *map she
reads*, and the pacing rules live in `how-to-teach.md` as skills. She chooses the
next move; the order is advice, not a rail. Everything in `non_negotiable_rules`
survives — as a rule she reads, or as a Core refusal:

| Package rule | Where it is enforced now |
|---|---|
| no independent pair work without a spoken model | `map.md` pre-task, `how-to-teach.md` |
| do not advance on time alone | `map.md` → *"Time is not the measure; attempts are"* |
| ≤2 ASR retries for one learner | speech layer; ASR work is paused by decision |
| never show identity / assessment on the projector | **Core refuses it** — `show_exercise` never carries `chosenId` |
| facilitator stop overrides immediately | `/control`, ⚠️ **buttons still return `unknown_event`** |

### 3.2 The step-by-step `ai_says` script (§4–6)

Every step gives an exact line for the agent to speak. Adopting that would make
her a tape player with a model attached, and it collides with NS-6: a script is
code shaped like content — a second subject cannot reuse a single line of it.

The *content* of those steps is already in the library as objectives, assets and
practice options. What we drop is only the fixed wording and the fixed clock.

### 3.3 The proposed tool list (§7.1)

Mostly a rename of what exists. Genuinely missing, and worth considering:

| Package tool | Status |
|---|---|
| `display_image`, `crop_or_zoom_image` | ✅ `show_image` + 16 pre-cropped panels |
| `play_audio`, `pause_audio` | ✅ `play_clip` (no pause — a clip is short by design) |
| `speech_output(text, speed)` | ✅ `say`. ⚠️ **no `speed`** — slow modelling is not expressible |
| `show_dialogue(lines)` | ✅ `write_board` / `say(board_text)` |
| `listen_for_class_response` | ✅ the turn loop itself (`awaiting_answer`) |
| `timer_or_chime(seconds)` | ❌ **missing.** Pair rotation every 20–30s is asked for in three separate steps |
| `facilitator_alert(vi, severity)` | ❌ **missing.** The escalation list has no way to fire |
| `write_class_memory` | ✅ `record_evidence` (per learner) + `plan` (per period) |

Two of those are real gaps against the escalation policy in NORTH-STAR §1, which
today has doctrine but no tool. Recorded here rather than fixed silently.

### 3.4 Multigrade (Policy §2)

Not built, not planned yet. Noted so it is not discovered late: it interacts with
the 20–40-child class contract that `record_evidence` already anticipates with
`student_id`, but `TeacherOS.learner_id` does not.

---

## 4. The package, as received

<details><summary>Full text, verbatim</summary>

Unit contract: `GS3_U1_HELLO`, *Hello*, pages 10–15, Pre-A1, 20–25 learners,
3 lessons × 60 min. Primary outcome: a student can independently complete a
short polite greeting exchange — greet, name, ask wellbeing, answer, take leave.
Success criterion: three appropriate turns with understandable speech; perfect
pronunciation or grammar NOT required.

**Lesson 1 — Hello, I'm …** (pages 10–11, tracks 5–8)

| Step | Minutes | What happens |
|---|---|---|
| L1-01 | 0–3 | Welcome ritual. Wave, say Hello. Fallback: *"Hello means xin chào."* |
| L1-02 | 3–7 | Notice the meaning. Track 5, panel a (Ben & Mai). *"Hello or goodbye?"* |
| L1-03 | 7–12 | Model the first exchange. *"Hello. I'm …"* Class repeats ×2, then own name |
| L1-04 | 12–15 | Character listening check. Track 6, point to Ben/Mai, then Minh/Lucy |
| L1-05 | 15–20 | Task briefing: **Meet Three Friends**. Demonstrate both roles |
| L1-06 | 20–27 | Pair round 1, rehearsed exchange. Prompt "Switch!" every 30s |
| L1-07 | 27–37 | Rotation to two new partners. Board shows only the frame |
| L1-08 | 37–42 | Gentle individual showcase. Volunteers first. *"That's okay. Together!"* |
| L1-09 | 42–47 | Listening game: choose the picture. Track 7, one/two fingers |
| L1-10 | 47–52 | Language focus, no jargon. Never say "contraction" or "verb to be" |
| L1-11 | 52–58 | Song close. Track 8: wave → chant → swap in volunteer names |
| L1-12 | 58–60 | Exit signal + memory write. *"Goodbye, Teacher Bee!"* |

**Lesson 2 — How are you? Goodbye!** (pages 12–13, tracks 9–11): retrieval
greeting; model wellbeing (hand on heart) and leave-taking; build the four-turn
dialogue by halves of the class; task **Greeting Journey** (meeting a friend on
the path to school); four-picture listening sequence; **Human Match** oral
call-and-response replacing the written matching exercise;
**Hello-and-Goodbye Circle** with a soft chime every 20s; exit check.

**Lesson 3 — Speak, chant, perform** (pages 14–15, tracks 12–14): whole-unit
retrieval; *h* / *b* sound-and-gesture play (hand near mouth, lips together);
listen and choose; chant as scaffold; capstone **Welcome a Visitor** (a visitor
comes to the school, village, or homestay — locally relevant, no new language);
role-play with supports, then without; optional volunteer performance;
picture-response oral review; **Friendly Conversation Check** logged as
demonstrated / emerging / not_observed with never a public mark; celebrate and
bridge to Unit 2.

**Operating rules**: English first, one short Vietnamese phrase only after a
meaning check fails twice; 4s wait after a question; 2–3 choral rounds before any
individual; no interruption for minor errors during a task; vision may read
raised hands and pair formation but never emotion, identity or punishment; ASR
accepts the essential intended words and never demands a native accent.

**Copyright**: the Global Success pages and official tracks are third-party
material from Vietnam Education Publishing House and Macmillan. Private
prototype asset store only. Any public demo, distribution or scale-up needs a
licence, or team-created / openly licensed replacements.

</details>
