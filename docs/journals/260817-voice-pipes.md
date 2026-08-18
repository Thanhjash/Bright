# 2026-08-17 — Layer 3 voice pipes wired

Teacher Core created `capability_leases` only when a cassette
`lesson_run` loaded. Teacher boot points at a missing `no-lesson.json`,
so Stage never owned audio.

**Shipped:** leases without a lesson; `teacher-agent-l1` starts Piper/
Whisper; `/teacher/status` has `speechUp` + `stageAudioOwner`; Stage
keeps a pending `say` until the lease is back; `/learn` Hold-to-talk
uses existing `stt.ts` (not a second loudspeaker). `airi-bridge`
SpeechPlayer is unchanged for Layer 4.

**Live closed 2026-08-18.** Root cause: `teacher_os` published
`board.present`, which is not an `EventType`. `next_seq()` ran, Event()
rejected the frame, Stage saw a seq gap and dropped `speech.turn`.

Fix: stop publishing it; refuse unknown types before allocating seq;
let speech frames through the snapshot gate. Playwright
`tests/node/teacher_voice_live.mjs` then got Piper + `market.wav` + a
real opening line.

Do not call AIRI body done.
