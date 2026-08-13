#!/usr/bin/env bash
# Operator-only acceptance lane for Bright's one real composed classroom turn.
#
# Start the one-turn ideal stack first, then choose one mode:
#
#   ./scripts/ideal-hosted.sh acceptance-start
#   ./scripts/ideal-composed-acceptance.sh --mode manual-physical-mic
#   ./scripts/ideal-composed-acceptance.sh --mode fake-audio-file \
#       --fake-audio-file /absolute/path/known-answer.wav
#
# The synthetic-file mode still uses MediaRecorder -> real ASR -> Core. Manual
# mode is the actual acceptance run: an adult speaks into the selected physical
# microphone. Neither mode starts fake services or sends protocol frames.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PLAYWRIGHT="$ROOT/.tools/node_modules/playwright-core/index.mjs"
CHROME_DEFAULT="$HOME/.cache/ms-playwright/chromium-1228/chrome-linux64/chrome"

[[ -f "$PLAYWRIGHT" ]] || { echo "playwright-core is missing at $PLAYWRIGHT" >&2; exit 2; }
[[ -x "${BRIGHT_CHROME:-$CHROME_DEFAULT}" ]] || {
  echo "Chromium is missing; set BRIGHT_CHROME to its executable path." >&2
  exit 2
}

export PLAYWRIGHT_CORE="file://$PLAYWRIGHT"
export CHROME_PATH="${BRIGHT_CHROME:-$CHROME_DEFAULT}"

args=("$@")
mode="manual-physical-mic"
has_fixture=0
for ((i=0; i<${#args[@]}; i++)); do
  [[ "${args[$i]}" == "--mode" ]] && mode="${args[$((i+1))]:-}"
  [[ "${args[$i]}" == "--fake-audio-file" ]] && has_fixture=1
done
if [[ "$mode" == "fake-audio-file" && "$has_fixture" == 0 ]]; then
  generated="$ROOT/.runtime/ideal-hosted/fixtures/market-water-request.wav"
  voice_only="${generated%.wav}.voice.wav"
  mkdir -p "$(dirname "$generated")"
  curl -fsS --max-time 30 \
    -H 'content-type: application/json' \
    -d '{"input":"At the market today, I would like to buy a bottle of water, please.","voice":"en","model":"piper","speed":1.1}' \
    "http://127.0.0.1:${SPEECH_PORT:-8001}/audio/speech" >"$voice_only"
  # Chromium restarts the file-backed input when mic preflight releases it.
  # Give both preflight and the real take a quiet calibration window; otherwise
  # the UI correctly learns the synthetic voice itself as the room noise floor.
  python3 - "$voice_only" "$generated" <<'PY'
import sys
import wave

source, target = sys.argv[1:]
with wave.open(source, "rb") as reader:
    params = reader.getparams()
    frames = reader.readframes(reader.getnframes())
silence_frames = int(params.framerate * 1.2)
silence = b"\0" * silence_frames * params.nchannels * params.sampwidth
with wave.open(target, "wb") as writer:
    writer.setparams(params)
    writer.writeframes(silence + frames)
PY
  rm -f "$voice_only"
  [[ -s "$generated" ]] || { echo "failed to generate the synthetic adult fixture" >&2; exit 2; }
  args+=(--fake-audio-file "$generated")
fi

node "$ROOT/tests/node/ideal_composed_acceptance.mjs" "${args[@]}"

# The live-profile contract includes zero durable classroom messages. Check
# the actual acceptance home after the real request, not merely the profile
# object used by unit tests. Schema/cache databases may exist; the transcript
# table must remain empty.
python3 - "$ROOT/.runtime/ideal-hosted/acceptance-hermes-home" <<'PY'
import sqlite3
import sys
from pathlib import Path

marker = Path(sys.argv[1])
if not marker.is_file():
    raise SystemExit("acceptance Hermes home marker is missing")
home = Path(marker.read_text(encoding="utf-8").strip())
db_path = home / "state.db"
if not db_path.is_file():
    print("Bright acceptance privacy gate: no durable state database")
    raise SystemExit(0)
with sqlite3.connect(db_path) as db:
    table = db.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='messages'"
    ).fetchone()
    count = db.execute("SELECT COUNT(*) FROM messages").fetchone()[0] if table else 0
if count:
    raise SystemExit(f"privacy gate failed: Hermes persisted {count} classroom messages")
print("Bright acceptance privacy gate: messages=0")
PY
