#!/usr/bin/env bash
# One command: speech + Core + Hermes + the room. Adult boots this and walks away.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
"$ROOT/scripts/teacher-agent-l1.sh" start
UI_LOG="${BRIGHT_TEACHER_RUNTIME_DIR:-$ROOT/.runtime/teacher-agent}/logs/ui.log"
mkdir -p "$(dirname "$UI_LOG")"
if ! curl -sf --max-time 2 http://127.0.0.1:3000/classroom >/dev/null 2>&1; then
  (
    cd "$ROOT/apps/classroom-ui"
    nohup env VITE_POLL=1 pnpm dev --host 127.0.0.1 --port 3000 >"$UI_LOG" 2>&1 </dev/null &
    echo $! >"${BRIGHT_TEACHER_RUNTIME_DIR:-$ROOT/.runtime/teacher-agent}/pids/ui.pid"
  )
  for _ in $(seq 1 40); do
    curl -sf --max-time 2 http://127.0.0.1:3000/classroom >/dev/null 2>&1 && break
    sleep 0.5
  done
fi
printf 'teacher-up ready  core=:8004 hermes=:8642 speech=:8001\n'
printf 'the room          http://127.0.0.1:3000/classroom\n'
printf 'adult console     http://127.0.0.1:3000/control\n'
printf 'adult status      curl -s http://127.0.0.1:8004/teacher/status\n'
