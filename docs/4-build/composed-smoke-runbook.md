# Real speech and browser composition smoke

This command is intentionally separate from `product-smoke`. The product wire
smoke may use a fake speech server so it can run on every developer machine.
This one never does: it targets the real local Piper/faster-whisper service and
uses Chromium's media APIs. Its microphone is intentionally Chromium's synthetic
test stream, not a child or room recording.

Start Bright normally, wait until both the UI and speech service are healthy,
then run:

```bash
./scripts/composed-smoke.sh
```

The probe requires the real service at `127.0.0.1:8001` to have an English
Piper voice and a loaded STT model, and the UI at `127.0.0.1:3000`. Chromium
opens a synthetic browser microphone (so it is safe and repeatable), records a real
`MediaRecorder` clip, sends it to the actual `/audio/transcriptions` endpoint,
then fetches actual Piper WAV from `/audio/speech` and starts it in the browser audio
pipeline. It writes a result and browser log under
`tests/.artifacts/composed-smoke/`.

Use different local ports explicitly when needed:

```bash
./scripts/composed-smoke.sh --ui-url http://127.0.0.1:3100 --speech-url http://127.0.0.1:8101
```

`SKIP` (exit `2`) means a required local dependency, browser, service, voice,
or STT model is unavailable. It is deliberately not converted into a pass.
`FAIL` means the selected real boundary responded incorrectly or the browser
composition broke.

## One-turn ideal composed acceptance

This is a different, stricter lane from `composed-smoke`. It starts the installed
profile and runs two persistent Chromium contexts (`/classroom` and `/control`) through
the visible UI:

```bash
./scripts/ideal-hosted.sh acceptance-start
./scripts/ideal-composed-acceptance.sh --mode manual-physical-mic
```

For a repeatable wiring diagnostic only, use the generated adult Piper fixture:

```bash
./scripts/ideal-composed-acceptance.sh --mode fake-audio-file
```

The fake file is a Chromium microphone input, not a fabricated protocol event. It
travels through browser `MediaRecorder`, the real Whisper endpoint, Core grading, the
hosted Hermes/MCP proposal path, real Piper, AIRI browser playback, and the Stage's own
causal WebAudio playback acknowledgement. The harness stores a scrubbed event-order
artifact at `tests/.artifacts/ideal-composed/result.json`; it records no answer text,
transcript, cookies, or credentials.

On 2026-08-13 this lane passed once in `fake-audio-file` mode: the artifact recorded
`ok: true`, real ASR and Piper HTTP 200 responses, a correct Core outcome, one agent
turn, a Stage-originated playback completion at event 368, and the later Core commit at
event 370. The fresh `bright_live` Hermes home from that run had zero stored messages
after policy moved to `gateway.api_server.extra.bright_live`.

The acceptance launcher intentionally widens only this synthetic cold-provider run to
90 seconds and lowers only its generated-fixture speech threshold to `0.65`. Normal
product defaults remain a 6-second agent budget and `0.75` correct threshold. Do not use
this command or its result to justify changing them.

## Optional Hermes readiness and MCP proposal rehearsal

With a running authenticated local sidecar, an operator may add its cheap
health check:

```bash
./scripts/composed-smoke.sh --hermes-health
```

The command refuses unset, `CHANGE-ME*`, `changeme*`, and `placeholder*`
credentials before calling Hermes. Health is cheap and does not consume the
single live teacher slot. To also require a real Hermes → Core MCP proposal in
an active target lesson, add:

```bash
./scripts/composed-smoke.sh --hermes-health --hermes-tool-round-trip
```

That calls the separately existing product smoke against the running Core/UI/
speech stack and fails unless the post-answer agent speech turn appears. Core
accepts the proposal only through the registered per-turn MCP capability. The
virtual Stage sends playback ACKs, so this is an honest gateway/MCP rehearsal,
not proof that physical audio played.

## What this is not

This does not test physical speaker-to-microphone echo, permission prompts on
the room machine, child speech recognition, learner grading, no-false-accept,
AIRI lifecycle acknowledgements, or a physical Hermes utterance. The room corpus
gate remains the release evidence for the most important of those: no incorrect
child answer may be graded correct.

The ideal fake-file pass also does **not** prove a physical room, a child, a full Market
lesson, or an autonomous 20–40 learner classroom. `manual-physical-mic` is the next
operator run, followed by the separate no-false-accept room corpus and full-session gates.
