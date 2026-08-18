#!/usr/bin/env bash
# Fetch every model Bright needs into ./models/.
# Idempotent: re-running skips what is already present.
#
#   ./scripts/fetch-models.sh          # everything
#   ./scripts/fetch-models.sh tts      # just Piper voices
#   ./scripts/fetch-models.sh stt      # just Whisper
#   ./scripts/fetch-models.sh live2d   # just the avatar
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODELS="$ROOT/models"
WHAT="${1:-all}"

say() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
skip() { printf '    \033[2m(have %s)\033[0m\n' "$*"; }

# ─────────────────────────────── TTS: Piper ───────────────────────────────
# en_US-lessac-medium : clear neutral American English. Good pronunciation model
#                       for learners, which matters more here than character.
# vi_VN-vais1000-medium : Vietnamese. Required — the scaffolding ladder ends in
#                       Vietnamese explanation (north-star NS-1), and Kokoro,
#                       the higher-MOS alternative, has no Vietnamese at all.
fetch_tts() {
  say "Piper voices -> models/piper"
  mkdir -p "$MODELS/piper"
  local base="https://huggingface.co/rhasspy/piper-voices/resolve/main"
  local specs=(
    "en/en_US/lessac/medium/en_US-lessac-medium"
    "vi/vi_VN/vais1000/medium/vi_VN-vais1000-medium"
  )
  for spec in "${specs[@]}"; do
    local name; name="$(basename "$spec")"
    for ext in onnx onnx.json; do
      local dest="$MODELS/piper/${name}.${ext}"
      if [[ -s "$dest" ]]; then skip "${name}.${ext}"; continue; fi
      echo "    downloading ${name}.${ext}"
      curl -fsSL --retry 3 --max-time 900 -o "$dest" "${base}/${spec}.${ext}"
    done
  done
}

# ─────────────────────────────── STT: Whisper ─────────────────────────────
# Whisper always processes a 30-second window, so cost is per CALL regardless of
# how short the utterance is. Measured here 2026-08-11, 12 threads, int8:
#
#     tiny.en           0.66 s/call   3/3 exact
#     base.en           1.80 s/call   2/3
#     small.en          3.35 s/call   3/3     <- default
#     large-v3-turbo   11.53 s/call   3/3     <- 17x slower, no gain. Rejected.
#
# The samples were clean Piper output and cannot separate these models; real
# child speech in a noisy room will. small.en is the safe default with headroom;
# tiny.en is there for when latency matters more than robustness. Fetch both.
fetch_stt() {
  say "Whisper (int8) -> models/whisper"
  mkdir -p "$MODELS/whisper"
  python3 - <<'PY'
import os, pathlib
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
dest = pathlib.Path(os.environ.get("MODELS", "models")) / "whisper"
try:
    from faster_whisper import WhisperModel
except ImportError:
    raise SystemExit("faster-whisper not installed: pip install faster-whisper")
for name in ("small.en", "tiny.en"):
    print(f"    {name}")
    WhisperModel(name, device="cpu", compute_type="int8", download_root=str(dest))
print("    ok")
PY
}

# ────────────────────────────── Avatar: Live2D ────────────────────────────
# Haru (Cubism 4), a Live2D sample model.
#
#   LICENCE: Live2D Inc. sample material. Fine for internal development and
#   demos; commercial/public release is RESTRICTED and must be resolved before
#   shipping to schools. See docs/archive/tracker.md item P1.
#
# Note this model ships motion groups "Idle" and "Tap" only, so emotions are
# driven through its 8 expressions. The mapping lives in models/live2d/
# bright-model.json — the app reads that file, never hardcoded ids.
fetch_live2d() {
  say "Live2D Haru -> models/live2d"
  local dir="$MODELS/live2d"
  mkdir -p "$dir"
  local base="https://raw.githubusercontent.com/guansss/pixi-live2d-display/master/test/assets/haru"

  if [[ -s "$dir/haru_greeter_t03.moc3" ]]; then skip "haru model"; else
    curl -fsSL --max-time 120 -o "$dir/haru_greeter_t03.model3.json" \
      "$base/haru_greeter_t03.model3.json"
    ( cd "$dir" && python3 - "$base" <<'PY'
import json, subprocess, sys, os
base = sys.argv[1]
d = json.load(open("haru_greeter_t03.model3.json"))["FileReferences"]
files = [d.get("Moc"), d.get("Physics"), d.get("Pose"), *d.get("Textures", [])]
files += [e["File"] for e in d.get("Expressions", [])]
for grp in d.get("Motions", {}).values():
    files += [m["File"] for m in grp]
for rel in filter(None, files):
    os.makedirs(os.path.dirname(rel), exist_ok=True) if os.path.dirname(rel) else None
    subprocess.run(["curl", "-fsSL", "--max-time", "180", "-o", rel, f"{base}/{rel}"], check=True)
print(f"    {len(list(filter(None, files)))} files")
PY
    )
  fi

  if [[ -s "$dir/live2dcubismcore.min.js" ]]; then skip "cubism core"; else
    curl -fsSL --max-time 120 -o "$dir/live2dcubismcore.min.js" \
      "https://cubism.live2d.com/sdk-web/cubismcore/live2dcubismcore.min.js"
  fi

  [[ -s "$dir/bright-model.json" ]] || \
    echo "    WARNING: bright-model.json missing — emotion mapping will fall back to defaults"
}

export MODELS
case "$WHAT" in
  all)    fetch_tts; fetch_stt; fetch_live2d ;;
  tts)    fetch_tts ;;
  stt)    fetch_stt ;;
  live2d) fetch_live2d ;;
  *) echo "usage: $0 [all|tts|stt|live2d]" >&2; exit 2 ;;
esac

say "done"
du -sh "$MODELS"/* 2>/dev/null || true
