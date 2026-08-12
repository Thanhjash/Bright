# Option B Core wire smoke runbook

This is a bounded process/socket check for the production Core wire path. It proves
that production Core can start a lesson and finish its authored path with no
Hermes, network, API key, Piper model, Whisper model, or real learner data.
It is not a composed browser/audio test and is not release proof.

## Required command

From the repository root:

```bash
./scripts/product-smoke.sh
```

The command starts isolated processes on fresh loopback ports:

- the real `classroom-core` with `CORE_DEV=0`, `BRIGHT_AGENT=off`, and a short
  deterministic lesson;
- the real Vite classroom UI, checked only as HTTP routes and configured to
  those isolated Core and speech endpoints;
- a fake speech HTTP service that returns valid silence WAV. This exercises
  the HTTP/audio boundary without claiming to test Piper or Whisper quality;
- two independent Python protocol-v2 WebSocket clients acting as Stage and
  Control. The Stage client fabricates playback ACKs; AIRI is not executed.

The virtual Stage performs exact playback ACKs and answers the authored
question. The virtual Control performs production `lesson.start`. Before the
lesson, each client attempts one operation belonging to the other role; Core
must reject both. The command fails unless the lesson reaches `DONE`, both
roles see monotonic `seq` and `stateVersion`, `/dev/*` is absent, and both UI
routes are served.

Success returns exit code `0`. Product failure returns `1`. A host policy that
forbids loopback sockets returns `2` with status `environment-blocked`; this is
not converted into a false pass.

Each run writes `result.json` plus Core/UI/speech logs under a unique directory
in `tests/.artifacts/product-smoke/`. Credentials and environment values are
never copied into the report.

## Real speech target

Start the local speech service, then replace the fake endpoint:

```bash
./scripts/product-smoke.sh --speech-url http://127.0.0.1:8001
```

This checks service health and composition. It still does not establish ASR
quality; `tests/room/room_test.py` owns the zero-false-accept room gate.

## Deterministic agent-seam rehearsal

The scripted agent is a lookup table, not a model. It is useful to prove the
agent seam without a network or secret:

```bash
./scripts/product-smoke.sh --agent scripted
```

The mandatory release path remains the default `--agent off` run because an
agent outage must not stop a class.

## Pinned Hermes smoke

Hermes must already be configured with the matching Core MCP endpoint and
token. Load the product-smoke lesson into that stack and target all three
running services:

```bash
./scripts/product-smoke.sh \
  --core-url http://127.0.0.1:8004 \
  --ui-url http://127.0.0.1:3000 \
  --speech-url http://127.0.0.1:8001
```

Target mode intentionally does not read or report the sidecar's secrets. A
target Core must expose the `product-smoke-option-b` fixture and have dev
endpoints disabled; otherwise the command fails. Run this after the no-Hermes
gate, never instead of it.

## Failure triage

Read `result.json` first. It records startup time, lesson-start ACK, first
authored speech, answer-to-wrap, completion time, event counts, capability
health, and tails from failed managed processes. Common classifications:

- `environment-blocked`: rerun on CI/appliance where loopback binding is
  permitted;
- `/dev/state returned HTTP 200`: Core is not in production mode;
- `invalid_playback_ack`: Stage correlation or speech lifecycle is broken;
- no `DONE`: inspect the final event list and `core.log`;
- UI route failure: rebuild/install `apps/classroom-ui` and retry.

This smoke is useful but not sufficient for release. A real-browser Stage +
Control run, AIRI playback, real Piper/Whisper, PTT/barge-in, child/noisy-room
audio, thermal soak, and hosted/local model latency retain separate gates.
