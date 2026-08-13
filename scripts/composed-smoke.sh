#!/usr/bin/env bash
# Real local speech + browser media composition. Never substitutes fake speech.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="$ROOT/services/classroom-core/.venv/bin/python"
[[ -x "$PYTHON" ]] || PYTHON=python3
exec "$PYTHON" "$ROOT/scripts/composed_smoke.py" "$@"
