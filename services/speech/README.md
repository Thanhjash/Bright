# Bright speech service

Local OpenAI-compatible speech boundary:

- `POST /audio/speech` synthesizes WAV with a resident Piper voice;
- `POST /audio/transcriptions` transcribes with the resident faster-whisper
  model;
- `GET /health` reports TTS voices, STT availability, active model, and models
  available for a safe local swap;
- `POST /admin/model` swaps only to an already-downloaded allowlisted model.

The service binds loopback. Missing speech models are a degraded capability,
not permission to stop Core or the authored lesson. `scripts/dev.sh` therefore
starts Core and UI even when speech is unavailable and prints the missing
capability explicitly.

## Product checks

The secret-free composed smoke uses a valid fake WAV service so it can verify
Core/UI/protocol composition on any development host:

```bash
./scripts/product-smoke.sh
```

To compose against this real service instead:

```bash
./scripts/product-smoke.sh --speech-url http://127.0.0.1:8001
```

That proves endpoint health and composition, not recognition quality. Run the
room harness for the safety gate:

```bash
python3 tests/room/room_test.py --service http://127.0.0.1:8001
```

Release requires zero wrong utterances graded as correct. Synthetic clean
audio is not evidence for noisy child speech.
