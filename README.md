# Bright

Bright is a local-first English classroom appliance built around a deterministic
Classroom Core, an AIRI-based projected teacher, browser speech input/output, and
an optional Hermes agent sidecar.

The product keeps lesson state, grading, learner memory, and safety policy inside
Core. Hermes can adapt teaching through a narrow authenticated MCP boundary, but
an authored lesson continues when the model or network is unavailable.

## Architecture

- `services/classroom-core`: lesson state machine, grading, memory, protocol bus,
  and classroom authority.
- `services/agent`: Direct, Scripted, and Hermes agent adapters.
- `services/speech`: Piper TTS and provider-neutral ASR (currently
  faster-whisper).
- `apps/classroom-ui`: Stage/projector and Control/microphone routes.
- `packages/airi-bridge`: Live2D, ACT markers, and keyed speech playback.
- `packages/contracts`: protocol v2 documentation and TypeScript/Python mirrors.

Two documents are living: [**NORTH-STAR.md**](docs/NORTH-STAR.md) (why this
exists and the five principles) and [**STATE.md**](docs/STATE.md) (what is wired
and what is next — paste this into a new agent chat). The
[documentation map](docs/README.md) indexes everything else.

## Local development

Copy the example environment, install the service and workspace dependencies,
fetch the required models, then run:

```bash
./scripts/dev.sh
```

The Stage is served at `http://127.0.0.1:3000/classroom` and Control at
`http://127.0.0.1:3000/control`. See [classroom-core README](services/classroom-core/README.md)
and [classroom UI README](apps/classroom-ui/README.md) for detailed setup.

## Verification status

Focused Core, Hermes, AIRI, UI, speech, room-gate, a virtual-ACK wire smoke, and a
synthetic-browser-mic-to-real-local-speech probe are in place. This repository does
not yet claim classroom release readiness: a full real Stage/AIRI/browser/audio/Hermes
composition on target hardware and a consented child/noisy-room zero-false-accept
corpus remain mandatory gates. Current evidence and open risks
are maintained in [STATE.md](docs/STATE.md).

## Data and models

Secrets, learner databases, runtime artifacts, upstream reference repositories,
and model weights are intentionally excluded from Git. Raw child audio and
transcripts must remain ephemeral unless an explicitly consented evaluation
corpus records provenance and retention policy.
