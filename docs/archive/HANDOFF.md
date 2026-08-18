# HANDOFF — paste this into a new agent chat

**Date:** 2026-08-18  
**Repo:** `/mnt/d/3.Project/Education/Bright`  
**Branch to work on:** `teacher-agent` (uncommitted cook; same SHA as local `main`)  
**Do not merge `main` until the owner says so.**

You are cooking Bright: an **autonomous Hermes teacher**, not a chatbot, not a
cassette/`lesson_run.json` graph, not a second brain inside AIRI. The owner is
the CTO. They write in Vietnamese. Answer them in Vietnamese when they do.
Use conda `base`. Do not wait to be told the next obvious step after a lock.

---

## 0. Read these first (in this order)

Stop after each file if it contradicts a later one — **earlier wins only when
it is the north star**. Later living docs win on *execution order*.

| # | File | Why |
|---|---|---|
| 1 | `docs/NORTH-STAR.md` | Bible. Bar = *switch it on and it teaches*. AI is the teacher; adult only boots the room. NS-1…NS-5. |
| 2 | `docs/decisions/teacher-agent-not-cassette.md` | 2026-08-16 lock. Hermes = teacher. Core = OS. Fail → notify + restart AI. No tape. |
| 3 | `docs/decisions/layer-1-memory-is-enough.md` | 2026-08-17 lock. **Stop Store B** (no FTS5 / BKT / GraphRAG / Mem0 / Letta / raw chat memory). |
| 4 | `docs/STATE.md` | Living layer order 0→7. |
| 5 | `docs/STATE.md` | What is actually wired. |
| 6 | **This file** | Last owner correction + honest workflow + next cook. |

Then only if the task touches that area:

| If you touch… | Also read |
|---|---|
| Runtime / ports / Hermes sidecar | `docs/decisions/option-b-classroom-runtime.md` |
| Why not OpenClaw as runtime | `docs/decisions/hermes-over-openclaw.md` (borrow heartbeat *pattern* only) |
| Stage / two windows | `docs/design/runtime-topology.md` |
| Tools / bus / ownership | `docs/design/architecture.md` |
| AIRI attach | `docs/design/reusing-airi-and-friends.md` + `packages/airi-bridge/` |
| Protocol seq / speech frames | `packages/contracts/PROTOCOL.md` |
| Library on disk | `content/library/` + `content/README.md` |
| Bilingual TTS/ASR research (do **not** start as this cook) | `docs/research/prompts/PROMPT-bilingual-speech.md` |

### Do **not** treat as current doctrine

These are historical or half-wrong. Skim only if you need archaeology.

| File | Why stale |
|---|---|
| `docs/decisions/classroom-is-the-room.md` | Right that `/classroom` is the room. **Wrong** that Start + Hold-to-talk is the product. Owner rejected buttons 2026-08-18. |
| `docs/archive/cook-until-done.md` | Layer 3 voice paste. Already cooked. Says “do not start AIRI” — AIRI body is on Stage now. |
| `docs/archive/teacher-agent-plan.md` | Layer 1 A–H + “next = voice”. Voice wiring is done. |
| `docs/archive/option-b-implementation-status.md` | 2026-08-13 cassette handoff. |
| `docs/archive/state-of-the-project.md`, `tracker.md`, `phase-1-plan.md` | 2026-08-11. |
| `docs/research/notes/2026-08-16-teacher-loop-roadmap.md` | Same-day superseded by teacher-agent-not-cassette. |
| `plans/**` | Session scraps + superseded cassette proof. **Not living.** See `plans/README.md`. |
| `architecture.md` DEGRADED/OFFLINE cassette modes | Stale vs NS-1. |
| `content/lessons/market-food/*.run.json` | Historical tape. Not the teacher. Live curriculum is `content/library/`. |

---

## 1. Last owner correction (2026-08-18, not fully coded)

The long chat ended here. **This overrides** `classroom-is-the-room.md` interaction.

Owner: the current interact is hard to understand. They want an
**autonomous teacher agent**, sometimes **like a human, no buttons**.
That is why they mentioned OpenClaw heartbeat + Hermes — *self-check,
wake, work* — not a kiosk app.

What they do **not** want:

- `/learn` chat as the product
- Start class / Hold to talk as the teaching contract
- An adult deciding the next teaching move
- A second agent inside AIRI `stage-web` / `core-agent`

What they **do** want (north-star aligned):

```text
Adult boots the appliance (teacher-up / kiosk Chromium)
  → Stage connects + Hermes healthy + speech up
  → Core heartbeat opens the class itself  ([sat_down])
  → she greets, writes the board, teaches
  → when she is not speaking, the ROOM listens (VAD), no Hold button
  → silence too long → same heartbeat: prompt, move on, or HEARTBEAT_OK
  → she closes the period
  → /control is observability + emergency only
```

Browser autoplay / mic permission may need **one** adult gesture at kiosk
boot. That is not a per-utterance product button.

OpenClaw is **not** in the runtime (already decided). Copy only the
heartbeat *shape*: periodic main-session agent turn, skip if busy,
`HEARTBEAT_OK` if nothing to do, wake-now on presence. The 5 s PROTOCOL
`heartbeat` / `heartbeat.ack` is only a WebSocket ping. Do not confuse them.

---

## 2. Who owns what

```text
content/library/          curriculum (md maps, keys, how-to-teach)
content/media/            asset://… images + clips
Hermes sidecar :8642      teacher (coding-agent analog)
Bright MCP                hands (8 live tools)
classroom-core :8004      OS — I/O, clock, DB, reject, restart
Stage /classroom          board + speaker + body
AIRI airi-bridge          body + lipsync only
speech :8001              Piper TTS + faster-whisper ASR
/learn                    leftover Layer-2 mouth (debug). Not the demo.
/control                  adult console. Never a teaching move.
```

Live tools (do not add a ninth without a lock):

`read_library` `search_library` `write_board` `read_board` `show_image`
`play_clip` `say` `record_evidence`

`present` / `open_response` exist in older docs; they are **not** the live
list. `write_board` / `show_image` replaced `present` on the wire.

Memory (locked): SQL `observations` with mode `name|point|ask` →
`SKILL_CARD` + `PAST`. RAM `BEATS` is the last few teaching beats.
Raw child words are **only** `STUDENT_SAID` this turn (NS-5). No raw
child speech in SQL.

---

## 3. Git / branches

```text
teacher-agent                   HEAD 623f024   WORK HERE. Almost all Layer 1–4
                                              cook is UNCOMMITTED on this branch.
main                            623f024       same commit as teacher-agent
                                              local main is 3 commits AHEAD of
                                              origin/main (623f024 = those 3).
layer2-text-station             623f024       same SHA. Name is leftover.
wip/20260814-1to1-text-unproven 27044e8       PARKED. Do not resume.
origin/main                     3 behind local main
```

There is **no commit** for library teacher, voice, AIRI room, RoomDock, or
heartbeat. `git status` on `teacher-agent` is the real status.

Do not create a new branch unless the owner asks. Do not commit unless asked.

---

## 4. Layer status (honest)

| Layer | Claim | Truth |
|---|---|---|
| 0 OS | bus, session, DB, leases | Yes. Cassette (`runner.py`, `class_session.py`, `lesson_run.json`) still in tree — **not** the teacher. |
| 1 Teacher text | Hermes + library teaches 1:1 | **CLOSED 2026-08-17.** Live chats `minh-show` / `minh-c3`. |
| 2 Thin station | `/learn` mouth | **CLOSED.** Ugly on purpose. Do not polish. |
| 3 Voice | Stage TTS of `say`; ASR → `/teacher/turn` | **Wiring closed 2026-08-18.** Piper en/vi (script-pick, not real bilingual). Whisper `small.en` hallucinates short clips. |
| 4 Body + room | AIRI + photoreal board + autonomy | **NOW.** Body + wall photo + board on Stage: yes. **Autonomy: no.** RoomDock Start/mic is a misread. |
| 5 Class 20–40 | fairness, camera → `student_id` | Not started. Camera later binds id only; does not invent memory. |
| 6 Local Gemma | same tools, swap Hermes profile | Not started. Hosted MiMo now (`LLM_DISABLE_THINKING=true`). Max **1 concurrent** (429 if overlap). |
| 7 Giveaway | Hiyori licence, locale-as-config | Not started. Hiyori is Live2D sample — licence risk; demo first. |

---

## 5. Current runtime workflow (what actually happens)

```text
./scripts/teacher-up.sh
  speech :8001 · core :8004 · hermes :8642 · vite :3000
  → nobody teaches yet

GET /classroom
  Stage WS, capability.report audio_output → stage lease
  photoreal wall + Hiyori + empty board
  RoomDock shows "Start class"
  pulse_teacher → action=asleep   (NO session ⇒ will not wake)

Human clicks Start
  POST /teacher/session {open:false}     # fast
  POST /teacher/turn {text:"[sat_down]"} # Hermes, often 20–40s hosted
  she may say + show_image → Piper on Stage

Human Hold-to-talk (or types /learn)
  Whisper → POST /teacher/turn {text:…}
  Hermes tools → say / board
  loop

If a session exists and silence ≥ 45s
  pulse_teacher may send [heartbeat]
  HEARTBEAT_OK ⇒ no say, no evidence
  (quality unproven; never starts class by itself)
```

`/learn` still auto-boots a session on page load (`open:true`). That is why
old dual-page Playwright used `/classroom` as speaker and `/learn` as mouth.

### Key endpoints

| Method | Path | Role |
|---|---|---|
| GET | `/teacher/status` | `phase`, `hermesUp`, `speechUp`, `stageAudioOwner`, `readyToStart`, `sessionOpen`, `turnBusy`, `lastSay`, `lastFault` |
| POST | `/teacher/session` | create OS session; `open:true` runs `[sat_down]` **synchronously** (slow) |
| POST | `/teacher/turn` | student text or system token `[sat_down]` / `[heartbeat]` |
| POST | `/teacher/heartbeat` | `pulse_teacher` (force optional) |
| WS | `/ws` | Stage events. Unknown `EventType` must be refused **before** `next_seq` |

---

## 6. Next cook (if owner says go)

**Make the room autonomous. Remove Start/Hold as the contract.**

1. Presence = Stage audio lease + Hermes up + speech up → Core opens session and fires `[sat_down]`. No Start pill.
2. While she is not speaking, room mic is open (energy VAD / endpoint). No Hold. Ignore clips &lt; ~600 ms (Whisper hallucinates).
3. Heartbeat is the pacer (already sketched in `teacher_os.pulse_teacher`). Tune so she actually looks up after silence. Never overlap a live turn (hosted 429).
4. One unlock gesture at first pointer/kiosk boot if the browser requires it — adult, once.
5. Keep `/learn` as a debug mouth. Do not grow it.
6. RoomDock can die or shrink to a fading “I heard …” chip + fault banner.

Do **not** in this cook:

- Deepen Store B / GraphRAG / Mem0 / Letta / new DB
- Research new TTS/ASR (Piper + Whisper stay until owner’s research lands)
- Remount `references/airi/apps/stage-web` as a second teacher
- Camera / 20–40 / Gemma
- Hardcode unit pedagogy (`banana.svg`, `food-recognise-apple` in Core/Hermes). `test_no_unit_pedagogy.py` guards this.
- Merge to `main`

---

## 7. How to boot and prove

```bash
# conda base
./scripts/teacher-up.sh
# station leftover:  http://127.0.0.1:3000/learn
# room:              http://127.0.0.1:3000/classroom
# adult:             curl -s http://127.0.0.1:8004/teacher/status

# unit
cd services/classroom-core && python -m pytest \
  tests/test_teacher_os.py tests/test_teacher_heartbeat.py \
  tests/test_teacher_voice.py tests/test_no_unit_pedagogy.py \
  tests/test_library.py tests/test_bus.py -q
cd services/agent && python -m pytest tests/test_hermes.py -q

# live Chromium (owner often will not click; you must)
export PLAYWRIGHT_CORE=file://$PWD/.tools/node_modules/playwright-core/index.mjs
export CHROME_PATH=$HOME/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome
# existing: tests/node/teacher_e2e_playwright.mjs   (/classroom + /learn mouth)
# existing: tests/node/teacher_room_playwright.mjs  (Start + mic — will go stale
#                                                    when buttons die)
```

Restart **Core only** after Python changes (`teacher-up.sh start` also kills
Whisper load). Vite HMR covers UI. Hosted model: **one turn at a time**.

---

## 8. Landmines from this chat (do not re-learn)

- **`board.present` is not an EventType.** Publishing it allocated `seq`, then
  died; Stage saw a gap and **dropped `speech.turn`**. Bus now refuses unknown
  types before `next_seq`. TeacherOS `_push_stage` must publish `scene.update`.
- **No `CapabilityLeaseRegistry` without `lesson_run`.** Fixed: leases always
  exist. Stage must `capability.report` `{audio_output:true}` or Piper never
  starts (`speakingDriver` stays disabled).
- **Seq is per-connection.** Dual `/classroom` + `/learn` is two sockets.
  `/learn` must not be a second loudspeaker (no `speakingDriver` there).
- **Vite duplicate `speak` import** = PARSE_ERROR. Check `wiring.ts`.
- **Hiyori 33 MB zip** → Chrome “Network error” on Windows. Runtime is the
  unpacked `models/live2d/hiyori_pro_zh/runtime/…model3.json` (~4.8 MB).
- **Mouth:** `speakingDriver` scales open 0→1. Avatar `TARGET_VISIBLE` 0.60,
  less legs. Wall photo: `content/media/stage/classroom-wall.jpg` (modern
  full board, not the dilapidated room).
- **Piper** `en` vs `vi` by majority Latin vs Vietnamese letters. Mixed lines
  often pick `en`.
- **Whisper `small.en`** on &lt;1 s clips invents `BANANO` / `Happy!`.
- **`agy --print` must be last** if you call Gemini. Nested heredoc in bash
  broke a teacher-loop apply script once.
- **One-period-sentence reject** was too tight; `_check_teacher_line` was loosened.
- **Do not block off-unit images by keyword.** Owner rejected that as a bot.
- **Core must not invent Vietnamese fallback lines** or `UNIT_COMPLETE` dumps.
- Live2D must **not remount** when `scene.update` arrives (`AvatarLayer` stays
  mounted in `Stage.tsx`).

---

## 9. Map of the live code (not the cassette)

```text
services/classroom-core/teacher_os.py     TeacherOS + pulse_teacher + status
services/classroom-core/library.py        read/search library, unit_catalog
services/classroom-core/app.py            /teacher/* + heartbeat loop in lifespan
services/classroom-core/bus.py            refuse unknown EventType before seq
services/classroom-core/mcp_server.py     MCP tool surface
services/agent/bright_agent/hermes.py     render_teacher_turn, EVENT=heartbeat|class_start
infra/hermes/patches/0002-teacher-multi-tool.patch   8 iters, tool_choice required, exit on say
infra/hermes/patches/0001-*.patch         live ephemeral / store:false
scripts/teacher-up.sh / teacher-agent-l1.sh
apps/classroom-ui/src/stage/Stage.tsx     wall + board slot + AIRI + RoomDock
apps/classroom-ui/src/stage/RoomDock.tsx  Start + Hold  ← product-wrong; next cook removes
apps/classroom-ui/src/routes/learn/       leftover mouth
apps/classroom-ui/src/speech/speakingDriver.ts
packages/airi-bridge/                     the attach (not references/airi/apps/stage-web)
content/library/                          maps + keys
content/media/market|colours|stage/
```

Cassette still present (ignore as teacher): `runner.py`, `class_session.py`,
`tools/lesson-compile`, `content/lessons/**/*.run.json`, many `tests/test_i*.py`
and `tests/test_ideal_*`.

---

## 10. Cleanup done in this handoff pass

Deleted unused session scraps (not living doctrine):

- `plans/20260817-agent-storage-h0-plan.md`
- `plans/20260817-agent-storage-h0/`
- `plans/20260817-teacher-voice-pipes/`
- root `image.png` (accidental screenshot)

Left in place, marked dead:

- `plans/20260813-full-lesson-ideal-proof/` — **git-tracked** superseded
  cassette proof. See `plans/README.md`. Do not cook from it.

Living cook docs stay under `docs/archive/`, not `plans/`.

---

## 11. Owner non-goals (they keep repeating)

- Do not start TTS/ASR model research as the cook (use Piper/Whisper).
- Do not merge GraphRAG / Mem0 / Letta / HippoRAG into Core.
- Do not write a new DB.
- Camera later only binds `student_id`.
- Do not remount AIRI stage-web as a second brain.
- Do not grow `/learn`.
- Do not hardcode Market Food / colours rails in Core or the Hermes adapter.
- Competition demo: do not refuse a better body over licence fear *this week*;
  licence is Layer 7. Still do not ship a second teacher.

---

If the owner says “tiếp / cook / don’t wait” after this paste: execute §6.
If they say “review / hiểu chưa”: restate north star + this workflow, do not
add more chrome.
