#!/usr/bin/env bash
# Layer 1: pinned Hermes + Core MCP tool + hosted provider. No UI/speech/AIRI.
#
#   ./scripts/hermes-layer1-probe.sh bootstrap
#   ./scripts/hermes-layer1-probe.sh run
#   ./scripts/hermes-layer1-probe.sh stop
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  . "$ROOT/.env"
  set +a
fi

RUNTIME_DIR="${BRIGHT_LAYER1_RUNTIME_DIR:-$ROOT/.runtime/layer1}"
LOGS="$RUNTIME_DIR/logs"
PIDS="$RUNTIME_DIR/pids"
HERMES_HOME="${HERMES_HOME:-$RUNTIME_DIR/hermes-home}"
# Dedicated venv. Do not reuse .runtime/hermes-venv — that symlink currently
# points at the parked 0.20.0+bright.2 install.
HERMES_VENV="${LAYER1_HERMES_VENV:-$RUNTIME_DIR/hermes-venv}"
HERMES_PY="${HERMES_PY:-$HERMES_VENV/bin/python}"
HERMES_BIN="${HERMES_BIN:-$HERMES_VENV/bin/hermes}"
CORE_PY="${CORE_PY:-$ROOT/services/classroom-core/.venv/bin/python}"
CORE_PORT="${LAYER1_CORE_PORT:-18004}"
HERMES_PORT="${LAYER1_HERMES_PORT:-18642}"
PROBE="$ROOT/services/agent/evals/hermes_layer1_probe.py"

say() { printf '%s\n' "$*"; }
die() { printf 'layer1-probe: %s\n' "$*" >&2; exit 1; }

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

ensure_secret() {
  local name="$1" value="${!1:-}"
  if is_placeholder "$value"; then
    value="$(generate_loopback_secret)"
    [[ -n "$value" ]] || die "could not generate $name"
    printf -v "$name" '%s' "$value"
  fi
  export "$name"
}

load_environment() {
  HERMES_MODEL_PROVIDER="${HERMES_MODEL_PROVIDER:-custom}"
  HERMES_MODEL_BASE_URL="${HERMES_MODEL_BASE_URL:-${LLM_BASE_URL:-}}"
  HERMES_MODEL_API_KEY="${HERMES_MODEL_API_KEY:-${LLM_API_KEY:-}}"
  HERMES_MODEL_NAME="${HERMES_MODEL_NAME:-${LLM_MODEL:-}}"
  if [[ -z "${HERMES_MODEL_MIMO_DISABLE_THINKING+x}" ]]; then
    HERMES_MODEL_MIMO_DISABLE_THINKING="${LLM_DISABLE_THINKING:-true}"
  fi
  local server_key="${API_SERVER_KEY:-}" client_key="${HERMES_API_KEY:-}"
  if is_placeholder "$server_key"; then
    if ! is_placeholder "$client_key"; then
      server_key="$client_key"
    else
      server_key="$(generate_loopback_secret)"
    fi
  fi
  API_SERVER_KEY="$server_key"
  HERMES_API_KEY="$server_key"
  ensure_secret BRIGHT_MCP_TOKEN
  export HERMES_MODEL_PROVIDER HERMES_MODEL_BASE_URL HERMES_MODEL_API_KEY HERMES_MODEL_NAME
  export HERMES_MODEL_MIMO_DISABLE_THINKING API_SERVER_KEY HERMES_API_KEY BRIGHT_MCP_TOKEN
  export API_SERVER_ENABLED=true
  export API_SERVER_HOST=127.0.0.1
  export API_SERVER_PORT="$HERMES_PORT"
  export API_SERVER_MODEL_NAME=bright-classroom
  export CORE_PORT="$CORE_PORT"
  export LAYER1_CORE_HOST=127.0.0.1
  export LAYER1_CORE_PORT="$CORE_PORT"
  export LAYER1_CORE_URL="http://127.0.0.1:${CORE_PORT}"
  export HERMES_PORT HERMES_HOME HERMES_VENV HERMES_PY HERMES_BIN
  export HERMES_API_URL="http://127.0.0.1:${HERMES_PORT}"
  export HERMES_API_TIMEOUT_S="${HERMES_API_TIMEOUT_S:-45}"
  export HERMES_PINNED_VERSION="$(hermes_version)"
  export BRIGHT_AGENT=hermes
}

pid_file() { printf '%s/%s.pid' "$PIDS" "$1"; }

pid_alive() {
  local file
  file="$(pid_file "$1")"
  [[ -s "$file" ]] && kill -0 "$(<"$file")" 2>/dev/null
}

stop_one() {
  local name="$1" file pid
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
  for name in hermes mcp; do stop_one "$name"; done
  say "layer1 probe stopped"
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

hermes_version() {
  python3 - "$ROOT/infra/hermes/manifest.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])
PY
}

bootstrap() {
  load_environment
  [[ -d "$ROOT/references/hermes-agent/.git" ]] || die "references/hermes-agent is missing"
  mkdir -p "$ROOT/wheels" "$HERMES_HOME"
  local version wheel
  version="$(hermes_version)"
  wheel="$ROOT/wheels/hermes_agent-${version}-py3-none-any.whl"
  if [[ ! -s "$wheel" ]]; then
    python3 "$ROOT/infra/hermes/build_pinned.py" --repo "$ROOT/references/hermes-agent" --outdir "$ROOT/wheels"
  fi
  [[ -s "$wheel" ]] || die "verified Bright Hermes wheel missing: $wheel"
  [[ -x "$HERMES_PY" ]] || python3 -m venv "$HERMES_VENV"
  "$HERMES_VENV/bin/pip" install --find-links "$ROOT/wheels" -r "$ROOT/infra/hermes/requirements.txt" >/dev/null
  "$HERMES_VENV/bin/pip" install --force-reinstall --no-deps "$wheel" >/dev/null
  "$HERMES_PY" "$ROOT/infra/hermes/verify_runtime.py"
}

materialize_config() {
  mkdir -p "$HERMES_HOME"
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
}

preflight() {
  load_environment
  [[ -n "$HERMES_MODEL_API_KEY" ]] && ! is_placeholder "$HERMES_MODEL_API_KEY" \
    || die "hosted provider key missing (LLM_API_KEY / HERMES_MODEL_API_KEY)"
  [[ -n "$HERMES_MODEL_BASE_URL" ]] || die "HERMES_MODEL_BASE_URL / LLM_BASE_URL missing"
  [[ -n "$HERMES_MODEL_NAME" ]] || die "HERMES_MODEL_NAME / LLM_MODEL missing"
  [[ -x "$CORE_PY" ]] || die "classroom-core Python missing: $CORE_PY"
  [[ -x "$HERMES_PY" ]] || die "run bootstrap first (no Hermes python)"
  [[ -x "$HERMES_BIN" ]] || die "run bootstrap first (no hermes binary)"
  "$HERMES_PY" "$ROOT/infra/hermes/verify_runtime.py" >/dev/null \
    || die "installed Hermes is not the verified Bright runtime from infra/hermes/manifest.json"
}

start_stack() {
  mkdir -p "$LOGS" "$PIDS"
  preflight
  stop_all
  materialize_config
  start_one mcp "$CORE_PY" "$PROBE" serve
  wait_for mcp "http://127.0.0.1:$CORE_PORT/health"
  # Hermes expands ${CORE_PORT} from the environment to find Bright MCP.
  start_one hermes "$HERMES_BIN" gateway run --external-supervisor
  wait_for hermes "http://127.0.0.1:$HERMES_PORT/health" "$HERMES_API_KEY"
  say "layer1 sidecar ready (core :$CORE_PORT, hermes :$HERMES_PORT)"
}

run_probe() {
  local run_id artifact
  run_id="$(date -u +%Y%m%dT%H%M%SZ)-$$"
  artifact="${BRIGHT_LAYER1_ARTIFACTS:-$ROOT/tests/.artifacts/hermes-layer1-$run_id}"
  mkdir -p "$artifact"
  load_environment
  start_stack
  set +e
  "$CORE_PY" "$PROBE" run --artifact-dir "$artifact"
  local status=$?
  set -e
  stop_all
  say "artifact: $artifact/result.json"
  return "$status"
}

case "${1:-run}" in
  bootstrap) bootstrap ;;
  run) run_probe ;;
  stop) load_environment; stop_all ;;
  *) echo "usage: $0 [bootstrap|run|stop]" >&2; exit 2 ;;
esac
