# Teacher agent — status (2026-08-17)

Hermes is the teacher. Core is the OS. Library markdown is the syllabus.

```text
intended: Stage presence → Core heartbeat → Hermes teaches
now:      human Start/mic or /learn → /teacher/turn → Hermes
          (buttons are a misread; next cook removes them)
```

Handoff: [HANDOFF.md](HANDOFF.md).

Live tools: `read_library` `search_library` `write_board` `read_board` `show_image` `play_clip` `say` `record_evidence`.

Memory: SQL `observations` (mode name|point|ask) → `SKILL_CARD` + `PAST`. RAM `BEATS` is the last few teaching beats, not a chat log. Raw child speech is only `STUDENT_SAID` this turn.

Cassette (`runner.py`, `class_session.py`, `DirectAgent` menus) still in the tree. It is **not** the NS-1 fallback. Dead AI → notify + restart.

Hermes pin: `0.20.0+bright.3` = patch `0001` + `0002-teacher-multi-tool` (8 turns, `say` terminal). Overlay still applied at start until a new wheel is built. Boot: `./scripts/teacher-up.sh`. Adult: `GET /teacher/status`.

**Layer 1 closed 2026-08-17.** Adapt = card + keys, not a memory product.
Locked: [layer-1-memory-is-enough.md](../decisions/layer-1-memory-is-enough.md).
Layer 2 `/learn` exit is met — do not polish it. Do not start FTS5 / BKT /
chat-memory. **Layer 3 live 2026-08-18.** Hermes `say` + `play_clip` reach Stage.

Hole: `board.present` is not an EventType. `next_seq()` ran, the frame died,
Stage saw a seq gap and dropped `speech.turn`. Bus now refuses unknown types
before allocating seq. Live `teacher_voice_live.mjs`: Piper + `market.wav` +
“Chào con! Welcome! Look — this is the market.”

Click `/classroom` once. One session at a time (hosted max 1).

**Layer 4 mouth proven 2026-08-18.** Live2D Hiyori on Stage; `mouthOpen`
peaked 0.68 while Piper played. Emotions still Idle (Hiyori has no
expression groups). Do not pull AIRI’s streaming server.

**Layer 4 room 2026-08-18.** `/classroom` is a photo of a real chalkboard
wall + Hermes `show_image` on the slate + Hiyori in front + Piper.
Chromium e2e: wall photo, market on the board, Hiyori, mouth 0.7, Piper
on Stage only. Piper picks `en`/`vi` by script (existing voices).
Camera / student_id still Layer 5.
