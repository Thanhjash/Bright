#!/usr/bin/env bash
# Run Bright's real, hosted happy path on one development machine.
#
# This launcher is intentionally separate from dev.sh.  `dev.sh` remains the
# resilient authored-path command for ordinary development; this command is a
# release gate and refuses to start when any required live dependency is
# missing.  It never changes BRIGHT_AGENT to off.
#
#   ./scripts/ideal-hosted.sh check
#   ./scripts/ideal-hosted.sh bootstrap-hermes
#   ./scripts/ideal-hosted.sh bootstrap-speech
#   ./scripts/ideal-hosted.sh start              # Market Food product lesson
#   ./scripts/ideal-hosted.sh acceptance-start   # composed gate (one turn by default)
#   ./scripts/ideal-hosted.sh status
#   ./scripts/ideal-hosted.sh stop
set -euo pipefail

ROOT="${BRIGHT_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
# Read developer configuration before resolving paths and ports.  The command
# overwrites only the profile safety switches below; provider values remain in
# the local .env and are never echoed.
if [[ -f "$ROOT/.env" ]]; then
  set -a
  # shellcheck disable=SC1090
  . "$ROOT/.env"
  set +a
fi
RUNTIME_DIR="${BRIGHT_IDEAL_RUNTIME_DIR:-$ROOT/.runtime/ideal-hosted}"
LOGS="$RUNTIME_DIR/logs"
PIDS="$RUNTIME_DIR/pids"
EPHEMERAL_HOME_MARKER="$RUNTIME_DIR/acceptance-hermes-home"

CORE_PORT="${CORE_PORT:-8004}"
SPEECH_PORT="${SPEECH_PORT:-8001}"
UI_PORT="${UI_PORT:-3000}"
HERMES_PORT="${HERMES_PORT:-8642}"
PIPER_DIR="${PIPER_DIR:-$ROOT/models/piper}"
WHISPER_DIR="${WHISPER_DIR:-$ROOT/models/whisper}"
WHISPER_MODEL="${WHISPER_MODEL:-small.en}"
HERMES_HOME="${HERMES_HOME:-$RUNTIME_DIR/hermes-home}"
HERMES_VENV="${HERMES_VENV:-$ROOT/.runtime/hermes-venv}"
CORE_PY="${CORE_PY:-$ROOT/services/classroom-core/.venv/bin/python}"
SPEECH_PY="${SPEECH_PY:-$ROOT/services/speech/.venv/bin/python}"
HERMES_PY="${HERMES_PY:-$HERMES_VENV/bin/python}"
HERMES_BIN="${HERMES_BIN:-$HERMES_VENV/bin/hermes}"
CORE_LESSON_RUN="${CORE_LESSON_RUN:-$ROOT/content/lessons/market-food/market-food-01.run.json}"

say() { printf '%s\n' "$*"; }
die() { printf 'ideal-hosted: %s\n' "$*" >&2; exit 1; }

is_placeholder() {
  local value="${1:-}" lower
  lower="${value,,}"
  [[ -z "$value" || "$lower" == change-me* || "$lower" == changeme* || "$lower" == placeholder* ]]
}

generate_loopback_secret() {
  # These credentials authenticate only processes bound to 127.0.0.1.  They
  # are deliberately made in memory for this launcher process: do not add
  # them to .env, a runtime file, a log, or command output.
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex 32
  else
    od -An -N32 -tx1 /dev/urandom | tr -d ' \n'
  fi
}

ensure_ephemeral_loopback_secret() {
  local name="$1" value="${!1:-}" generated
  if ! is_placeholder "$value"; then
    return 0
  fi
  generated="$(generate_loopback_secret)"
  [[ -n "$generated" ]] || die "could not generate local loopback credential"
  printf -v "$name" '%s' "$generated"
  export "$name"
}

align_gateway_api_credentials() {
  # Hermes' API-server adapter authenticates with API_SERVER_KEY. Bright's
  # HTTP adapter intentionally exposes that same local bearer through the
  # HERMES_API_KEY client setting. The two names therefore describe opposite
  # sides of one loopback-only trust boundary, not two independent credentials.
  #
  # Prefer an explicitly supplied API_SERVER_KEY because that is what Hermes'
  # config loader ultimately uses. This also keeps older developer .env files
  # with two different local placeholders/keys working without editing them:
  # the launcher reconciles the client value in this process only.
  local server_key="${API_SERVER_KEY:-}" client_key="${HERMES_API_KEY:-}"
  if is_placeholder "$server_key"; then
    if ! is_placeholder "$client_key"; then
      server_key="$client_key"
    else
      server_key="$(generate_loopback_secret)"
      [[ -n "$server_key" ]] || die "could not generate local loopback credential"
    fi
  fi
  API_SERVER_KEY="$server_key"
  HERMES_API_KEY="$server_key"
  export API_SERVER_KEY HERMES_API_KEY
}

load_legacy_model_defaults() {
  local explicit_hermes_model=0
  for name in HERMES_MODEL_PROVIDER HERMES_MODEL_BASE_URL HERMES_MODEL_API_KEY HERMES_MODEL_NAME; do
    if [[ -n "${!name:-}" ]]; then
      explicit_hermes_model=1
      break
    fi
  done
  # Bright already uses LLM_* for DirectAgent.  The Hermes profile speaks the
  # same OpenAI-compatible provider, so retain those developer credentials as
  # the default and reserve HERMES_MODEL_* for an explicit override/local
  # backend.  Do not reinterpret a supplied Hermes field.
  HERMES_MODEL_PROVIDER="${HERMES_MODEL_PROVIDER:-custom}"
  HERMES_MODEL_BASE_URL="${HERMES_MODEL_BASE_URL:-${LLM_BASE_URL:-}}"
  HERMES_MODEL_API_KEY="${HERMES_MODEL_API_KEY:-${LLM_API_KEY:-}}"
  HERMES_MODEL_NAME="${HERMES_MODEL_NAME:-${LLM_MODEL:-}}"
  # MiMo's OpenAI-compatible endpoint accepts a non-standard *top-level*
  # thinking switch.  Carry the already-proven DirectAgent setting into the
  # hosted profile only when all model fields still come from LLM_*. An
  # explicit Hermes/local backend defaults to false, unless its operator
  # explicitly selects otherwise via HERMES_MODEL_MIMO_DISABLE_THINKING.
  if [[ -z "${HERMES_MODEL_MIMO_DISABLE_THINKING+x}" ]]; then
    if (( explicit_hermes_model )); then
      HERMES_MODEL_MIMO_DISABLE_THINKING=false
    else
      HERMES_MODEL_MIMO_DISABLE_THINKING="${LLM_DISABLE_THINKING:-false}"
    fi
  fi
  export HERMES_MODEL_PROVIDER HERMES_MODEL_BASE_URL HERMES_MODEL_API_KEY HERMES_MODEL_NAME HERMES_MODEL_MIMO_DISABLE_THINKING
}

require_secret() {
  local name="$1" value="${!1:-}"
  [[ -n "$value" ]] || die "$name is required (value is never printed)"
  ! is_placeholder "$value" || die "$name is a placeholder; install a real credential"
}

require_value() {
  local name="$1" value="${!1:-}"
  [[ -n "$value" ]] || die "$name is required"
}

model_cache_dir() {
  case "$WHISPER_MODEL" in
    tiny.en) echo "models--Systran--faster-whisper-tiny.en" ;;
    tiny) echo "models--Systran--faster-whisper-tiny" ;;
    base.en) echo "models--Systran--faster-whisper-base.en" ;;
    base) echo "models--Systran--faster-whisper-base" ;;
    small.en) echo "models--Systran--faster-whisper-small.en" ;;
    small) echo "models--Systran--faster-whisper-small" ;;
    large-v3-turbo) echo "models--mobiuslabsgmbh--faster-whisper-large-v3-turbo" ;;
    *) die "WHISPER_MODEL=$WHISPER_MODEL is not an offline faster-whisper model supported by Bright" ;;
  esac
}

load_environment() {
  # Do this after reading .env so this command's fail-closed values cannot be
  # weakened by developer configuration.
  load_legacy_model_defaults
  align_gateway_api_credentials
  ensure_ephemeral_loopback_secret BRIGHT_MCP_TOKEN
  export BRIGHT_RUN_PROFILE=ideal_hosted
  export BRIGHT_REQUIRE_LIVE_PROFILE=1
  export BRIGHT_AGENT=hermes
  export CORE_DEV=0
  # Hermes only enrolls its API-server platform when it is explicit in its
  # launch environment. Pin these to the same loopback listener/config that
  # Bright's adapter calls; config.yaml remains the narrow tool allowlist.
  export API_SERVER_ENABLED=true
  export API_SERVER_HOST=127.0.0.1
  export API_SERVER_PORT="$HERMES_PORT"
  export API_SERVER_MODEL_NAME=bright-classroom
  export CORE_PORT SPEECH_PORT UI_PORT HERMES_PORT
  export PIPER_DIR WHISPER_DIR WHISPER_MODEL HERMES_HOME CORE_LESSON_RUN
  export HERMES_API_URL="http://127.0.0.1:${HERMES_PORT}"
  # A real local gateway health check is enough to promote Core.  This merely
  # makes that measured check happen promptly; it does not force CORE_MODE.
  unset CORE_MODE
  export CORE_PROBE_INTERVAL_S="${CORE_PROBE_INTERVAL_S:-1}"
  export CORE_RECOVER_AFTER="${CORE_RECOVER_AFTER:-1}"
}

preflight() {
  load_environment
  require_secret HERMES_API_KEY
  require_secret API_SERVER_KEY
  require_secret BRIGHT_MCP_TOKEN
  require_secret HERMES_MODEL_API_KEY
  require_value HERMES_MODEL_PROVIDER
  require_value HERMES_MODEL_BASE_URL
  require_value HERMES_MODEL_NAME
  [[ "${BRIGHT_DATA_POLICY:-}" == "hosted_ephemeral_transcript" ]] \
    || die "ideal profile requires BRIGHT_DATA_POLICY=hosted_ephemeral_transcript"
  [[ "${BRIGHT_HOSTED_RAW_ACK:-}" == "1" ]] \
    || die "ideal profile requires BRIGHT_HOSTED_RAW_ACK=1"

  [[ "$BRIGHT_AGENT" == hermes ]] || die "ideal profile requires BRIGHT_AGENT=hermes"
  [[ "$CORE_DEV" == 0 ]] || die "ideal profile requires CORE_DEV=0"
  [[ -x "$CORE_PY" ]] || die "classroom-core Python is missing: $CORE_PY"
  "$CORE_PY" -c 'import fastapi, uvicorn, websockets' >/dev/null 2>&1 \
    || die "classroom-core Python dependencies are incomplete"
  [[ -x "$SPEECH_PY" ]] || die "speech Python is missing: $SPEECH_PY"
  "$SPEECH_PY" -c 'import fastapi, uvicorn, multipart, piper, faster_whisper' >/dev/null 2>&1 \
    || die "speech Python dependencies are incomplete"
  [[ -s "$PIPER_DIR/en_US-lessac-medium.onnx" ]] \
    || die "required Piper English voice is missing: $PIPER_DIR/en_US-lessac-medium.onnx"
  [[ -d "$WHISPER_DIR/$(model_cache_dir)" ]] \
    || die "required faster-whisper model $WHISPER_MODEL is missing from $WHISPER_DIR"
  [[ -s "$ROOT/apps/classroom-ui/dist/index.html" ]] \
    || die "production UI is not built: $ROOT/apps/classroom-ui/dist/index.html"
  [[ -s "$CORE_LESSON_RUN" ]] || die "lesson run is missing: $CORE_LESSON_RUN"
  [[ -x "$HERMES_PY" ]] || die "pinned Hermes Python is missing: $HERMES_PY"
  [[ -x "$HERMES_BIN" ]] || die "pinned Hermes gateway is missing: $HERMES_BIN"
  [[ -f "$HERMES_HOME/config.yaml" ]] || die "HERMES_HOME/config.yaml is missing: $HERMES_HOME/config.yaml"
  "$HERMES_PY" "$ROOT/infra/hermes/verify_runtime.py" >/dev/null \
    || die "installed Hermes is not the verified Bright runtime from infra/hermes/manifest.json"
  say "ideal hosted preflight passed"
}

bootstrap_hermes() {
  load_environment
  local vendor="$ROOT/references/hermes-agent"
  [[ -d "$vendor/.git" ]] || die "pinned Hermes source checkout is missing: $vendor"
  mkdir -p "$ROOT/wheels" "$HERMES_HOME"
  python3 "$ROOT/infra/hermes/build_pinned.py" --repo "$vendor" --outdir "$ROOT/wheels"
  [[ -x "$HERMES_PY" ]] || python3 -m venv "$HERMES_VENV"
  # The Bright wheel is locally verified; its third-party runtime dependencies
  # are resolved from the configured package index for this developer profile.
  # Offline appliance bundling remains a separate, stricter wheelhouse gate.
  "$HERMES_VENV/bin/pip" install --find-links "$ROOT/wheels" \
    -r "$ROOT/infra/hermes/requirements.txt" >/dev/null
  # The version is intentionally stable while Bright iterates its pinned
  # patch. pip therefore cannot use the version string as proof that the
  # installed files are current. Reinstall the exact verified wheel last.
  local expected_version bright_wheel
  expected_version="$(python3 - "$ROOT/infra/hermes/manifest.json" <<'PY'
import json, sys
print(json.load(open(sys.argv[1], encoding="utf-8"))["version"])
PY
)"
  bright_wheel="$ROOT/wheels/hermes_agent-${expected_version}-py3-none-any.whl"
  [[ -s "$bright_wheel" ]] || die "verified Bright Hermes wheel is missing: $bright_wheel"
  "$HERMES_VENV/bin/pip" install --force-reinstall --no-deps "$bright_wheel" >/dev/null
  install -m 0600 "$ROOT/infra/hermes/config.yaml" "$HERMES_HOME/config.yaml"
  install -m 0600 "$ROOT/infra/hermes/SOUL.md" "$HERMES_HOME/SOUL.md"
  "$HERMES_VENV/bin/python" "$ROOT/infra/hermes/verify_runtime.py"
  say "pinned Hermes runtime bootstrapped"
}

bootstrap_speech() {
  [[ -x "$SPEECH_PY" ]] || python3 -m venv "$(dirname "$(dirname "$SPEECH_PY")")"
  "$(dirname "$SPEECH_PY")/pip" install -r "$ROOT/services/speech/requirements.txt"
  say "speech runtime bootstrapped"
}

pid_file() { printf '%s/%s.pid' "$PIDS" "$1"; }

pid_alive() {
  local file
  file="$(pid_file "$1")"
  [[ -s "$file" ]] && kill -0 "$(<"$file")" 2>/dev/null
}

stop_one() {
  local name="$1" file pid
  file="$(pid_file "$name")"
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
  for name in ui hermes core speech; do stop_one "$name"; done
  if [[ -s "$EPHEMERAL_HOME_MARKER" ]]; then
    local ephemeral_home
    ephemeral_home="$(<"$EPHEMERAL_HOME_MARKER")"
    case "$ephemeral_home" in
      "$RUNTIME_DIR"/hermes-home-acceptance-*) rm -rf -- "$ephemeral_home" ;;
      *) die "refusing to remove invalid ephemeral Hermes home: $ephemeral_home" ;;
    esac
    rm -f "$EPHEMERAL_HOME_MARKER"
  fi
  say "ideal hosted stack stopped"
}

start_one() {
  local name="$1" log="$LOGS/$1.log"
  shift
  nohup "$@" >"$log" 2>&1 </dev/null &
  echo "$!" >"$(pid_file "$name")"
}

wait_for() {
  local name="$1" url="$2" needle="$3" auth="${4:-}" body=""
  for _ in $(seq 1 90); do
    if [[ -n "$auth" ]]; then
      body="$(curl -sf --max-time 3 -H "Authorization: Bearer $auth" "$url" 2>/dev/null || true)"
    else
      body="$(curl -sf --max-time 3 "$url" 2>/dev/null || true)"
    fi
    if [[ -n "$body" ]] && response_matches "$body" "$needle"; then return 0; fi
    sleep 1
  done
  die "$name did not become ready; inspect $LOGS/$name.log"
}

response_matches() {
  local body="$1" requirement="$2"
  # API health handlers are allowed to choose normal or compact JSON
  # serialization.  A literal substring such as `"status": "ok"` made the
  # Hermes readiness gate depend on whitespace, so validate that one stable
  # response contract as JSON.  Other probes intentionally remain literal
  # because they assert payload details (speech model/voice and Core mode).
  if [[ "$requirement" == "json-status-ok" ]]; then
    printf '%s' "$body" | python3 -c '
import json
import sys

try:
    payload = json.load(sys.stdin)
except (json.JSONDecodeError, ValueError):
    raise SystemExit(1)
raise SystemExit(0 if isinstance(payload, dict) and payload.get("status") == "ok" else 1)
'
    return
  fi
  [[ "$body" == *"$requirement"* ]]
}

start_all() {
  mkdir -p "$LOGS" "$PIDS" "$HERMES_HOME"
  install -m 0600 "$ROOT/infra/hermes/config.yaml" "$HERMES_HOME/config.yaml"
  install -m 0600 "$ROOT/infra/hermes/SOUL.md" "$HERMES_HOME/SOUL.md"
  preflight
  stop_all

  # Hermes expands credential/base-url placeholders, but model.default is a
  # literal configuration value. Materialize the selected model into a fresh
  # runtime copy on every start so policy updates deploy deterministically and
  # `${HERMES_MODEL_NAME}` can never reach the provider as the model name.
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

  start_one speech "$SPEECH_PY" "$ROOT/services/speech/app.py"
  wait_for speech "http://127.0.0.1:$SPEECH_PORT/health" '"stt":true'
  wait_for speech "http://127.0.0.1:$SPEECH_PORT/health" '"en"'
  wait_for speech "http://127.0.0.1:$SPEECH_PORT/health" "\"sttModel\":\"$WHISPER_MODEL\""

  start_one core "$CORE_PY" "$ROOT/services/classroom-core/app.py"
  wait_for core "http://127.0.0.1:$CORE_PORT/health" json-status-ok

  # `gateway` without a subcommand launches Hermes' management CLI and can
  # exit successfully without binding the configured API server.  Keep this
  # foreground process pinned to the actual API-server entrypoint; nohup in
  # start_one supplies the external process supervision.
  start_one hermes "$HERMES_BIN" gateway run --external-supervisor
  wait_for hermes "http://127.0.0.1:$HERMES_PORT/health" json-status-ok "$HERMES_API_KEY"
  wait_for core "http://127.0.0.1:$CORE_PORT/health" '"mode":"FULL"'

  start_one ui python3 "$ROOT/scripts/serve-ui.py" --root "$ROOT/apps/classroom-ui/dist" --port "$UI_PORT"
  wait_for ui "http://127.0.0.1:$UI_PORT/__health" json-status-ok
  # The browser owns microphone permission and the Stage audio lease, so the
  # product cannot truthfully be "classroom ready" until the acceptance
  # browser has connected both roles.  Do not turn a running-daemons check
  # into a false claim that the next lesson may start.
  say "ideal hosted services are ready; classroom awaits Stage + Control capability leases"
  status_all
}

component_status() {
  local name="$1" url="$2" needle="$3" auth="${4:-}" body
  if ! pid_alive "$name"; then
    printf '  down  %s\n' "$name"
    return 1
  fi
  if [[ -n "$auth" ]]; then
    body="$(curl -sf --max-time 3 -H "Authorization: Bearer $auth" "$url" 2>/dev/null || true)"
  else
    body="$(curl -sf --max-time 3 "$url" 2>/dev/null || true)"
  fi
  if response_matches "$body" "$needle"; then
    printf '  ready %s\n' "$name"
    return 0
  fi
  printf '  not-ready %s\n' "$name"
  return 1
}

status_all() {
  load_environment
  local bad=0
  component_status speech "http://127.0.0.1:$SPEECH_PORT/health" '"stt":true' || bad=1
  component_status core "http://127.0.0.1:$CORE_PORT/health" '"mode":"FULL"' || bad=1
  # /health is deliberately unauthenticated in Hermes' API-server contract.
  # `status` is a cross-invocation diagnostic: the launcher creates a fresh
  # in-memory loopback key when the developer has not configured one, whereas
  # an already-running gateway holds the key from its own invocation.  Passing
  # that new key would turn a healthy gateway into a false "not-ready" result.
  # Do not relax startup or Core-to-Hermes authentication; both still use the
  # matching per-run bearer above.
  component_status hermes "http://127.0.0.1:$HERMES_PORT/health" json-status-ok || bad=1
  component_status ui "http://127.0.0.1:$UI_PORT/__health" json-status-ok || bad=1
  local readiness
  readiness="$(curl -s --max-time 3 "http://127.0.0.1:$CORE_PORT/ready" 2>/dev/null || true)"
  if [[ "$readiness" == *'"status":"ready"'* ]]; then
    printf '  ready classroom-capabilities\n'
  else
    printf '  waiting classroom-capabilities (open Stage and Control, then grant audio and microphone)\n'
  fi
  return "$bad"
}

case "${1:-start}" in
  check) preflight ;;
  bootstrap-hermes) bootstrap_hermes ;;
  bootstrap-speech) bootstrap_speech ;;
  start) start_all ;;
  acceptance-start)
    # The legacy/default acceptance proof remains one turn.  The explicit v3
    # fixture repeats the same known answer three times to prove the browser,
    # ASR, hosted agent, and causal playback path does not only work once.
    case "${BRIGHT_ACCEPTANCE_FIXTURE:-one-turn}" in
      one-turn) CORE_LESSON_RUN="$ROOT/tests/fixtures/ideal_composed_one_turn.run.json" ;;
      three-turn) CORE_LESSON_RUN="$ROOT/tests/fixtures/ideal_composed_three_turn.run.json" ;;
      *) die "BRIGHT_ACCEPTANCE_FIXTURE must be one-turn or three-turn" ;;
    esac
    # Each acceptance run is intentionally ephemeral. A fresh home prevents a
    # prior interrupted gateway lock/session database from contaminating the
    # next proof; the pinned Bright profile persists no classroom turns.
    HERMES_HOME="$RUNTIME_DIR/hermes-home-acceptance-$$"
    # The automated fixture is a composition/latency gate, not a child-room
    # accuracy claim. Keep the manual/product profile on small.en, while this
    # deterministic synthetic turn uses the measured low-latency local model.
    WHISPER_MODEL="${BRIGHT_ACCEPTANCE_WHISPER_MODEL:-base.en}"
    export WHISPER_THREADS="${BRIGHT_ACCEPTANCE_WHISPER_THREADS:-4}"
    # Calibrated only for the generated adult Piper fixture. The product and
    # child-room safety threshold remains 0.75 and has a separate zero-FA gate.
    export CORE_SPEECH_CORRECT_CONFIDENCE="${BRIGHT_ACCEPTANCE_SPEECH_CONFIDENCE:-0.65}"
    # Hosted-provider latency is measured by this gate. Give correctness/MCP
    # composition room to complete first; the artifact remains the evidence
    # used to tighten the production 6 s teaching budget afterwards.
    export AGENT_TURN_TIMEOUT_S="${BRIGHT_ACCEPTANCE_AGENT_TIMEOUT_S:-90}"
    # The HTTP adapter must not expire before the acceptance-only Core budget.
    # Product `start` still uses the strict production defaults.
    export HERMES_API_TIMEOUT_S="${BRIGHT_ACCEPTANCE_HERMES_TIMEOUT_S:-$AGENT_TURN_TIMEOUT_S}"
    start_all
    printf '%s\n' "$HERMES_HOME" >"$EPHEMERAL_HOME_MARKER"
    ;;
  status) status_all ;;
  stop) stop_all ;;
  *)
    echo "usage: $0 [check|bootstrap-hermes|bootstrap-speech|start|acceptance-start|status|stop]" >&2
    exit 2
    ;;
esac
