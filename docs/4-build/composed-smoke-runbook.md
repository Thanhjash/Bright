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

## Manual full-Market ideal-condition protocol

This is the next operator gate after the one- and three-turn composition lanes. It
exercises the **authored Market Food lesson from activity 0**, using the normal hosted
profile and a real adult at the answer station. It is a rehearsal of the teaching
product in an ideal quiet condition; it is not a child, acoustic-room, or assessment
validation.

### Before the run

1. Build the production UI and run the normal fail-closed preflight. Do not use
   `acceptance-start`: it swaps in a short acceptance fixture and has fixture-only
   timeout/confidence allowances.

   ```bash
   ./scripts/ideal-hosted.sh check
   ./scripts/ideal-hosted.sh start
   ```

2. Open two separate browser contexts on the same local origin: Stage at
   `http://127.0.0.1:3000/classroom` and Control at
   `http://127.0.0.1:3000/control`. Confirm the Stage audio lease, then use **Check
   microphone** on Control. The Start button must become enabled; do not bypass the
   setup or call a Core endpoint directly.

3. On Control, enter this eight-person pseudonymous roster and mark all eight present.
   These are test identities, not student names:

   ```text
   market-01, Market 01, A1
   market-02, Market 02, A2
   market-03, Market 03, A3
   market-04, Market 04, A4
   market-05, Market 05, B1
   market-06, Market 06, B2
   market-07, Market 07, B3
   market-08, Market 08, B4
   ```

4. Leave the lesson id blank when the loaded lesson is shown, or enter
   `en-prea1-market-food-01`; set a non-identifying class id such as
   `market-ideal-01`. Press **Start autonomous lesson** once. The normal start flow
   begins at authored activity 0 (`hook_market`); do not use Recovery/Skip/Back to
   enter the answer stations.

### Conduct the eight stations

Let the authored hook, input, guided practice and pair task proceed. At each selected
individual callout, the named adult walks to the one answer microphone, waits until the
Stage has finished its callout and Control shows the enabled **Ready** state, presses
Ready, and says the station phrase once. Do not speak over Stage output and do not
substitute a second person after capture is armed.

The deterministic assignment policy chooses the displayed pseudonym. Record its actual
order rather than claiming that it follows the roster order. The eight authored stations
and expected phrases are:

| Station | Authored activity | Expected spoken request |
|---:|---|---|
| 1 | `answer_station_01_apple` | I would like an apple, please. |
| 2 | `answer_station_02_banana` | I would like a banana, please. |
| 3 | `answer_station_03_bread` | I would like bread, please. |
| 4 | `answer_station_04_egg` | I would like an egg, please. |
| 5 | `answer_station_05_rice` | I would like rice, please. |
| 6 | `answer_station_06_water` | I would like water, please. |
| 7 | `answer_station_07_apple` | I would like an apple, please. |
| 8 | `answer_station_08_bread` | I would like bread, please. |

For a `near`, `wrong`, `uncertain`, `silence`, `timeout`, or service-recovery outcome,
let Bright show the authored sentence-builder recovery and continue to the next station.
That outcome is data, not a reason to use facilitator Skip. Pause/Emergency is reserved
for a real safety or equipment interruption; record it and stop calling the run
autonomous if it is used for teaching.

At the end, let `explore_transfer`, `exit_check`, and `closure` reach DONE. Stop the
stack only after recording the terminal UI state:

```bash
./scripts/ideal-hosted.sh status
./scripts/ideal-hosted.sh stop
```

### Evidence and pass record

Store the operator's scrubbed result in a dated, access-controlled evidence location
(for example `tests/.artifacts/manual-market/<run-id>/result.md`, which is ignored by
Git). The record may contain the commit, lesson id, profile, device model, start/end
times, all eight pseudonyms in their observed assignment order, each station's activity
id and **outcome category only**, whether its capture opened after the callout, whether
the agent response/playback completed, terminal `DONE`, and any Pause/Emergency use.

Do **not** retain audio, raw transcripts, cookies, credentials, actual learner names, or
speech-service request bodies in that record. Keep runtime logs access-controlled; they
are diagnostic material, not shareable proof.

A clean ideal-condition pass means: all eight authored stations were reached from
activity 0 without routine facilitator teaching decisions; every capture followed its
own completed callout; every path reached the next authored station or its authored
recovery; and the lesson reached DONE. It does **not** mean that all eight adult answers
were correct, that ASR is safe for children, or that the system has passed a room test.

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
