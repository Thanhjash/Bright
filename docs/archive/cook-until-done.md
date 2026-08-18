# Cook-until-done prompt

**STALE 2026-08-18.** Layer 3 voice wiring already shipped. AIRI body is
on Stage. Do **not** paste this. Use [HANDOFF.md](HANDOFF.md).

<details><summary>Original Layer 3 paste (archive)</summary>

Paste this to an agent. Do not stop to ask. Use conda `base`.

```
You are cooking Bright Layer 3: voice pipes for the Hermes teacher.

Layer 1 is CLOSED (text 1:1, 8 tools, mark book). Layer 2 /learn is a thin
mouth and stays ugly. Do not deepen Store B (FTS5, BKT, GraphRAG, Mem0,
raw chat memory). Do not start AIRI, 20–40, or Gemma.

Already true:
- teacher_os.say() and play_clip() already call core.publish_speech()
  → bus speech.turn.started / text.delta / turn.ended
- /classroom speakingDriver already TTS via Piper POST /audio/speech
- services/speech exists (Piper + faster-whisper); models/piper and
  models/whisper are on disk
- /learn is text-only HTTP to /teacher/session and /teacher/turn
- Cassette runner.py / class_session.py / lesson_run.json are NOT the teacher

Do next, in order, until each gate is green. Do not ask. Do not merge main
until the current gate is green.

1. First slice — Stage hears the teacher:
   Open /classroom while a teacher session runs. say() must play through
   Stage (Piper), not a second speaker inside /learn. play_clip stays
   asset audio. Half-duplex. Stage is the only loudspeaker (NS / Option B).
2. Second slice — child speaks into the same loop:
   Bright ASR (faster-whisper) fills /teacher/turn as text. Same TeacherOS.
   No raw audio and no prior transcripts to the hosted model (NS-5).
3. Live proof: one short HOOK→INPUT period with spoken say + one spoken
   child reply, evidence still categorical.

Refuse: Hermes voice tools, AIRI streaming server, cheap TTS bolted onto
/learn as a second audio owner, cassette speech.say as the teacher,
redesigning /learn, deepening SQLite.

Doctrine: docs/NORTH-STAR.md
         docs/decisions/layer-1-memory-is-enough.md
         docs/STATE.md
```

</details>
