#!/usr/bin/env bash
# Fetch VieNeu-TTS v3 Turbo: vendored source + INT8 CPU weights.
#
# WHY THIS EXISTS. The appliance ships to a school with no internet, so every
# byte the room needs has to be pulled here, on a machine that has a network,
# and carried. And it lands in `references/`, which is gitignored -- it is
# someone else's repository, and it sits beside the other vendored sources --
# so without this script a fresh checkout cannot rebuild the speech stack.
#
# WHAT IT IS. Apache-2.0, torch-free on CPU, ONNX Runtime, bilingual VI-EN by
# design, with 20 preset voices bundled in the source (no reference clip
# needed). It is the code-switching research's candidate #1.
#
# WHAT IT IS NOT. Not adopted. The acceptance gate is 240 utterances rated by
# three bilingual humans per voice (research §12): curriculum-keyword
# pronunciation, same perceived speaker across a switch, accent breaks,
# naturalness. Machines can measure intelligibility and latency and nothing
# else. Do not write "adopted" anywhere until people have listened.
#   -> docs/research/external/README.md
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC="$ROOT/references/VieNeu-TTS"
PY="${VIENEU_PYTHON:-$ROOT/services/speech/.venv/bin/python}"

if [[ ! -x "$PY" ]]; then
  echo "no speech venv at $PY — set VIENEU_PYTHON or create it first" >&2
  exit 1
fi

if [[ -d "$SRC/.git" ]]; then
  echo "source already at $SRC"
else
  echo "cloning VieNeu-TTS…"
  git clone --depth 1 https://github.com/pnnbao97/VieNeu-TTS.git "$SRC"
fi

# Only what the torch-free ONNX CPU path imports. The package's own
# dependency list also pulls gradio and librosa for its web UI, which this
# appliance has no use for and which cost hundreds of megabytes.
#
# kaldi-native-fbank is deliberately omitted: it is the speaker-encoder
# front-end for CLONING a voice from a wav. We use the bundled presets, so
# nothing calls it.
echo "installing the torch-free deps…"
"$PY" -m pip install -q \
  "sea-g2p>=0.9.0" \
  "onnxruntime>=1.20.0" \
  "tokenizers>=0.20" \
  numpy soundfile soxr huggingface_hub

# The engine fetches its own graphs, config, tokenizer and the MOSS codec from
# Hugging Face on first construction, into the standard HF cache. Doing it here
# means the first lesson does not pay for it -- and proves the download works
# while there is still a network to fix it on.
echo "fetching weights (INT8 backbone + MOSS codec, ~165MB + codec)…"
"$PY" - <<'PYEOF'
import sys, time
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1] if "__file__" in dir() else Path.cwd()
sys.path.insert(0, str(Path("references/VieNeu-TTS/src").resolve()))
from vieneu._v3_turbo_engine.onnx_runtime_lite import OnnxV3LiteEngine
t = time.perf_counter()
OnnxV3LiteEngine(onnx_subfolder="onnx_int8", threads=0)
print(f"engine constructed in {time.perf_counter() - t:.1f}s")
PYEOF

cat <<'DONE'

fetched. Measure it before believing it:

    ./tools/speech_roundtrip.py     # intelligibility floor, spends no model credit

and remember what that cannot tell you: whether it still sounds like one
teacher across a VI<->EN switch. That needs ears.
DONE
