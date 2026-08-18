#!/usr/bin/env bash
# Teacher agent first chat: Hermes + library tools. No lesson_run graph.
#
#   ./scripts/teacher-agent-l1.sh start
#   ./scripts/teacher-agent-l1.sh drive
#   ./scripts/teacher-agent-l1.sh stop
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$HOME/miniconda3/etc/profile.d/conda.sh" ]]; then
  # shellcheck disable=SC1091
  . "$HOME/miniconda3/etc/profile.d/conda.sh"
  conda activate base
fi
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

RUNTIME_DIR="${BRIGHT_TEACHER_RUNTIME_DIR:-$ROOT/.runtime/teacher-agent}"
LOGS="$RUNTIME_DIR/logs"
PIDS="$RUNTIME_DIR/pids"
HERMES_HOME="${HERMES_HOME:-$RUNTIME_DIR/hermes-home}"
HERMES_VENV="${LAYER1_HERMES_VENV:-$ROOT/.runtime/layer1/hermes-venv}"
HERMES_PY="${HERMES_PY:-$HERMES_VENV/bin/python}"
HERMES_BIN="${HERMES_BIN:-$HERMES_VENV/bin/hermes}"
CORE_PY="${CORE_PY:-$(command -v python)}"
CORE_PORT="${TEACHER_CORE_PORT:-8004}"
HERMES_PORT="${TEACHER_HERMES_PORT:-8642}"
SPEECH_PORT="${SPEECH_PORT:-8001}"
SPEECH_PY="${SPEECH_PY:-$ROOT/services/speech/.venv/bin/python}"
PIPER_VOICE="${PIPER_VOICE:-$ROOT/models/piper/en_US-lessac-medium.onnx}"
DATA_DIR="${BRIGHT_TEACHER_DATA_DIR:-$RUNTIME_DIR/data}"

say() { printf '%s\n' "$*"; }
die() { printf 'teacher-agent: %s\n' "$*" >&2; exit 1; }

is_placeholder() {
  local value="${1:-}" lower
  lower="${value,,}"
  [[ -z "$value" || "$lower" == change-me* || "$lower" == changeme* || "$lower" == placeholder* ]]
}

generate_loopback_secret() {
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

persist_loopback() {
  mkdir -p "$RUNTIME_DIR"
  local file="$RUNTIME_DIR/loopback.env"
  if [[ -s "$file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$file"
    set +a
  fi
  if is_placeholder "${API_SERVER_KEY:-}"; then
    API_SERVER_KEY="$(generate_loopback_secret)"
  fi
  HERMES_API_KEY="$API_SERVER_KEY"
  if is_placeholder "${BRIGHT_MCP_TOKEN:-}"; then
    BRIGHT_MCP_TOKEN="$(generate_loopback_secret)"
  fi
  umask 077
  printf 'API_SERVER_KEY=%s\nHERMES_API_KEY=%s\nBRIGHT_MCP_TOKEN=%s\n' \
    "$API_SERVER_KEY" "$HERMES_API_KEY" "$BRIGHT_MCP_TOKEN" >"$file"
  chmod 600 "$file"
  export API_SERVER_KEY HERMES_API_KEY BRIGHT_MCP_TOKEN
}

load_environment() {
  persist_loopback
  HERMES_MODEL_PROVIDER="${HERMES_MODEL_PROVIDER:-custom}"
  HERMES_MODEL_BASE_URL="${HERMES_MODEL_BASE_URL:-${LLM_BASE_URL:-}}"
  HERMES_MODEL_API_KEY="${HERMES_MODEL_API_KEY:-${LLM_API_KEY:-}}"
  HERMES_MODEL_NAME="${HERMES_MODEL_NAME:-${LLM_MODEL:-}}"
  HERMES_MODEL_MIMO_DISABLE_THINKING="${HERMES_MODEL_MIMO_DISABLE_THINKING:-${LLM_DISABLE_THINKING:-true}}"
  export HERMES_MODEL_PROVIDER HERMES_MODEL_BASE_URL HERMES_MODEL_API_KEY HERMES_MODEL_NAME
  export HERMES_MODEL_MIMO_DISABLE_THINKING
  export API_SERVER_ENABLED=true API_SERVER_HOST=127.0.0.1
  export API_SERVER_PORT="$HERMES_PORT"
  export API_SERVER_MODEL_NAME=bright-classroom
  export CORE_PORT HERMES_PORT HERMES_HOME HERMES_API_KEY
  export HERMES_API_URL="http://127.0.0.1:${HERMES_PORT}"
  # The hosted reasoning model has been measured at 80s for a trivial reply.
  # A 60s read timeout cuts her off mid-thought and leaves the provider's
  # single run open, which 429s the next turn.
  export HERMES_API_TIMEOUT_S="${HERMES_API_TIMEOUT_S:-300}"
  export BRIGHT_AGENT=hermes
  export BRIGHT_TEACHER_AGENT=1
  export PYTHONPATH="$ROOT/services/classroom-core:$ROOT/services/agent:$ROOT/packages/contracts/python${PYTHONPATH:+:$PYTHONPATH}"
  export CORE_DEV=0
  # (CORE_LESSON_RUN removed 2026-08-18 — the lesson-graph player is gone.)
  export DATA_DIR
  export AGENT_TURN_TIMEOUT_S="${AGENT_TURN_TIMEOUT_S:-60}"
  export BRIGHT_DATA_POLICY="${BRIGHT_DATA_POLICY:-hosted_semantic}"
  export CORE_PROBE_INTERVAL_S="${CORE_PROBE_INTERVAL_S:-2}"
}

pid_file() { printf '%s/%s.pid' "$PIDS" "$1"; }

stop_one() {
  local file pid
  file="$(pid_file "$1")"
  [[ -s "$file" ]] || return 0
  pid="$(<"$file")"
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
    for _ in $(seq 1 30); do
      kill -0 "$pid" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$pid" 2>/dev/null && kill -9 "$pid" 2>/dev/null || true
  fi
  rm -f "$file"
}

stop_all() {
  mkdir -p "$PIDS"
  for name in hermes core speech; do stop_one "$name"; done
  say "teacher-agent stopped"
}

start_one() {
  local name="$1" log="$LOGS/$1.log"
  shift
  nohup "$@" >"$log" 2>&1 </dev/null &
  echo "$!" >"$(pid_file "$name")"
}

wait_for() {
  local name="$1" url="$2" auth="${3:-}" body=""
  for _ in $(seq 1 90); do
    if [[ -n "$auth" ]]; then
      body="$(curl -sf --max-time 3 -H "Authorization: Bearer $auth" "$url" 2>/dev/null || true)"
    else
      body="$(curl -sf --max-time 3 "$url" 2>/dev/null || true)"
    fi
    if [[ -n "$body" ]] && printf '%s' "$body" | python3 -c 'import json,sys; p=json.load(sys.stdin); raise SystemExit(0 if isinstance(p,dict) and p.get("status")=="ok" else 1)' 2>/dev/null; then
      return 0
    fi
    sleep 1
  done
  die "$name did not become ready; inspect $LOGS/$name.log"
}

start_speech_if_ready() {
  if [[ ! -s "$PIPER_VOICE" ]]; then
    say "speech skipped (no Piper voice)"
    return
  fi
  if [[ ! -x "$SPEECH_PY" ]]; then
    say "speech skipped (no speech venv at $SPEECH_PY)"
    return
  fi
  export SPEECH_PORT SPEECH_HOST="${SPEECH_HOST:-127.0.0.1}"
  # Multilingual by default. The children speak Vietnamese and the teacher
  # code-switches, so an English-only model transcribes half the room into
  # garbage. `small` is the multilingual sibling of the benchmarked `small.en`;
  # large-v3-turbo is NOT the answer here -- see the timing table in
  # services/speech/app.py (11.5s/call vs 3.35s, same accuracy on our samples).
  # Measured on this laptop, idle, one short English clip ("Hello. I am Minh."):
  #   small  3836ms  "Hello, I am Min."     correct
  #   base   1687ms  "Hello, I'm Min."      correct, 2.3x faster
  #   tiny    681ms  "Hello, I'm Ben."      WRONG -- heard a different child
  # base is the floor at which the name is still right. tiny is not a speed
  # win, it is a wrong answer delivered sooner.
  export WHISPER_MODEL="${WHISPER_MODEL:-base}"
  start_one speech "$SPEECH_PY" "$ROOT/services/speech/app.py"
}

wait_for_speech() {
  [[ -s "$(pid_file speech)" ]] || return 0
  for _ in $(seq 1 90); do
    if curl -sf --max-time 2 "http://127.0.0.1:$SPEECH_PORT/health" >/dev/null 2>&1; then
      say "speech ready :$SPEECH_PORT"
      return
    fi
    sleep 1
  done
  say "speech did not become ready; inspect $LOGS/speech.log"
}

start_stack() {
  load_environment
  [[ -x "$CORE_PY" ]] || die "core python missing"
  [[ -x "$HERMES_BIN" ]] || die "hermes missing; run ./scripts/hermes-layer1-probe.sh bootstrap"
  "$HERMES_PY" "$ROOT/scripts/apply-teacher-hermes-loop.py" \
    || die "could not apply teacher Hermes loop patches"
  mkdir -p "$LOGS" "$PIDS" "$DATA_DIR" "$HERMES_HOME"
  stop_all
  install -m 0600 "$ROOT/infra/hermes/config.yaml" "$HERMES_HOME/config.yaml"
  install -m 0600 "$ROOT/infra/hermes/SOUL.md" "$HERMES_HOME/SOUL.md"
  "$CORE_PY" - "$HERMES_HOME/config.yaml" "$HERMES_MODEL_NAME" "$HERMES_PORT" <<'PY'
import sys
from pathlib import Path
import yaml
path = Path(sys.argv[1])
config = yaml.safe_load(path.read_text(encoding="utf-8"))
config["model"]["default"] = sys.argv[2]
config["gateway"]["api_server"]["port"] = int(sys.argv[3])
path.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
PY
  chmod 0600 "$HERMES_HOME/config.yaml"
  start_speech_if_ready
  start_one core "$CORE_PY" "$ROOT/services/classroom-core/app.py"
  wait_for core "http://127.0.0.1:$CORE_PORT/health"
  start_one hermes "$HERMES_BIN" gateway run --external-supervisor
  wait_for hermes "http://127.0.0.1:$HERMES_PORT/health" "$HERMES_API_KEY"
  wait_for_speech
  say "teacher-agent ready  core=:$CORE_PORT hermes=:$HERMES_PORT speech=:$SPEECH_PORT"
}

drive() {
  load_environment
  CORE_HTTP="http://127.0.0.1:${CORE_PORT}" \
    "$CORE_PY" "$ROOT/services/agent/evals/teacher_agent_l1.py"
}

chat() {
  load_environment
  CORE_HTTP="http://127.0.0.1:${CORE_PORT}" \
    "$CORE_PY" "$ROOT/services/agent/evals/teacher_agent_chat.py"
}

case "${1:-start}" in
  start) start_stack ;;
  drive) drive ;;
  chat) chat ;;
  stop) load_environment; stop_all ;;
  *) echo "usage: $0 [start|drive|stop|chat]" >&2; exit 2 ;;
esac
