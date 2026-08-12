#!/usr/bin/env bash
set -euo pipefail

# Deterministic developer/CI gate for the autonomous-classroom vertical slice.
# Live provider, physical audio and consented room evidence are separate release
# gates and are intentionally not faked by this command.

repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_dir"

python3 tools/lesson-lint/selftest.py
python3 tools/lesson-lint/lesson_lint.py \
  content/lessons/market-food/market-food-01.md --strict --no-color
python3 tools/lesson-compile/lesson_compile.py \
  content/lessons/market-food/market-food-01.md
python3 tools/lesson-play/lesson_play.py \
  content/lessons/market-food/market-food-01.run.json --json >/dev/null
python3 -m pytest -q tests/test_autonomous_lesson_contract.py tests/test_v3_capture_endpoint.py

if [[ -x services/agent/.venv/bin/pytest ]]; then
  (cd services/agent && .venv/bin/pytest -q -m 'not live')
fi

if [[ -x services/classroom-core/.venv/bin/pytest ]]; then
  services/classroom-core/.venv/bin/pytest -q \
    services/classroom-core/tests/test_runner.py \
    services/classroom-core/tests/test_option_b_mcp.py
fi

pnpm --filter @bright/airi-bridge typecheck
pnpm --filter @bright/airi-bridge test
pnpm --filter @bright/airi-bridge build
pnpm --filter @bright/classroom-ui typecheck
pnpm --filter @bright/classroom-ui build

echo "autonomous product deterministic gate passed"
