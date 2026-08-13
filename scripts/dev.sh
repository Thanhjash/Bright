#!/usr/bin/env bash
# Start the whole Bright stack for development.
#
#   ./scripts/dev.sh          start everything, follow logs
#   ./scripts/dev.sh stop     stop everything
#   ./scripts/dev.sh status   what is up
#
# Everything binds 127.0.0.1 only. Nothing listens on an external interface.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOGS="$ROOT/.logs"
mkdir -p "$LOGS"

CORE_PY="$ROOT/services/classroom-core/.venv/bin/python"
[[ -x "$CORE_PY" ]] || CORE_PY=python3
SPEECH_PY="$ROOT/services/speech/.venv/bin/python"
if [[ ! -x "$SPEECH_PY" ]]; then
  if python3 -c 'import fastapi, uvicorn, multipart, piper, faster_whisper' 2>/dev/null; then
    SPEECH_PY=python3
  else
    SPEECH_PY=""
  fi
fi
SERVICES=("core:8004:$CORE_PY $ROOT/services/classroom-core/app.py")
UI_PORT=3000
SPEECH_PORT="${SPEECH_PORT:-8001}"
HERMES_PORT="${HERMES_PORT:-8642}"

c() { printf '\033[%sm%s\033[0m\n' "$1" "$2"; }
pid_on() { ss -lptn "sport = :$1" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1; }

# A checked-in sample value is not a credential.  Treating it as one used to
# wire Core to a sidecar that could not authenticate, then spend its per-turn
# timeout in front of children. Keep this deliberately small and explicit so
# an operator can see why the authored path was selected.
has_hermes_credential() {
  local value="${HERMES_API_KEY:-}"
  local lowered="${value,,}"
  [[ -n "$value" && "$lowered" != change-me* && "$lowered" != changeme* && "$lowered" != placeholder* ]]
}

# NOTE: never use `pkill -f` here. The pattern matches this script's own command
# line and kills the shell running it. Two separate agents hit that during
# development. Always resolve the PID from the listening port instead.
stop_all() {
  for svc in "${SERVICES[@]}"; do
    IFS=: read -r name port _ <<<"$svc"
    local pid; pid="$(pid_on "$port")"
    if [[ -n "$pid" ]]; then kill "$pid" 2>/dev/null && c '0;33' "stopped $name (pid $pid)"; fi
  done
  local upid; upid="$(pid_on "$UI_PORT")"
  [[ -n "$upid" ]] && kill "$upid" 2>/dev/null && c '0;33' "stopped ui (pid $upid)"
  local spid; spid="$(pid_on "$SPEECH_PORT")"
  [[ -n "$spid" ]] && kill "$spid" 2>/dev/null && c '0;33' "stopped speech (pid $spid)"
  local hpid; hpid="$(pid_on "$HERMES_PORT")"
  [[ -n "$hpid" ]] && kill "$hpid" 2>/dev/null && c '0;33' "stopped hermes (pid $hpid)"
  return 0
}

status_all() {
  for svc in "${SERVICES[@]}"; do
    IFS=: read -r name port _ <<<"$svc"
    local pid; pid="$(pid_on "$port")"
    if [[ -n "$pid" ]]; then
      local h; h="$(curl -s --max-time 3 "http://127.0.0.1:$port/health" || echo '{}')"
      c '0;32' "  ● $name  :$port  pid=$pid  $h"
    else
      c '0;31' "  ○ $name  :$port  down"
    fi
  done
  local upid; upid="$(pid_on "$UI_PORT")"
  [[ -n "$upid" ]] && c '0;32' "  ● ui      :$UI_PORT  pid=$upid" || c '0;31' "  ○ ui      :$UI_PORT  down"
  local spid; spid="$(pid_on "$SPEECH_PORT")"
  [[ -n "$spid" ]] && c '0;32' "  ● speech  :$SPEECH_PORT  pid=$spid" || c '0;33' "  ○ speech  :$SPEECH_PORT  optional/down"
  local hpid; hpid="$(pid_on "$HERMES_PORT")"
  [[ -n "$hpid" ]] && c '0;32' "  ● hermes  :$HERMES_PORT  pid=$hpid" || c '0;33' "  ○ hermes  :$HERMES_PORT  optional/down"
}

preflight() {
  local bad=0
  [[ -f "$ROOT/.env" ]] || c '0;33' "no .env — starting the authored offline product path"
  [[ -s "$ROOT/models/piper/en_US-lessac-medium.onnx" ]] || c '0;33' "no Piper voice — Core/UI still start; speech output is unavailable"
  [[ -d "$ROOT/models/whisper" ]] || c '0;33' "no Whisper model — STT will 503 (./scripts/fetch-models.sh stt)"
  [[ -s "$ROOT/models/live2d/haru_greeter_t03.moc3" ]] || c '0;33' "no Live2D model — avatar will not render (./scripts/fetch-models.sh live2d)"
  "$CORE_PY" -c 'import fastapi, uvicorn, websockets' 2>/dev/null || { c '0;31' "classroom-core environment incomplete — install services/classroom-core"; bad=1; }
  if [[ ! -d "$ROOT/apps/classroom-ui/node_modules" && ! -f "$ROOT/apps/classroom-ui/dist/index.html" ]]; then
    c '0;31' "UI is neither installed nor built — run: cd apps/classroom-ui && pnpm install && pnpm build"
    bad=1
  fi
  return $bad
}

start_speech_if_ready() {
  if [[ ! -s "$ROOT/models/piper/en_US-lessac-medium.onnx" ]]; then
    c '0;33' "speech skipped (no Piper voice); authored lesson state remains available"
    return
  fi
  if [[ -z "$SPEECH_PY" ]]; then
    c '0;33' "speech skipped (dependencies unavailable); install services/speech/requirements.txt"
    return
  fi
  nohup "$SPEECH_PY" "$ROOT/services/speech/app.py" >"$LOGS/speech.log" 2>&1 </dev/null &
  disown
  c '0;36' "starting speech on :$SPEECH_PORT  (log: .logs/speech.log)"
}

start_hermes_if_ready() {
  [[ "${BRIGHT_DEV_START_HERMES:-0}" == "1" ]] || return
  if [[ "${BRIGHT_AGENT:-off}" != "hermes" ]]; then
    c '0;33' "Hermes requested but BRIGHT_AGENT is not hermes — skipped"
    return
  fi
  local hermes_bin=""
  hermes_bin="$(command -v hermes 2>/dev/null || true)"
  [[ -n "$hermes_bin" ]] || hermes_bin="$ROOT/references/hermes-agent/.venv/bin/hermes"
  if [[ ! -x "$hermes_bin" ]]; then
    c '0;33' "Hermes requested but no pinned executable is installed — Core uses authored fallback"
    return
  fi
  if [[ -z "${HERMES_HOME:-}" || ! -f "${HERMES_HOME:-/nonexistent}/config.yaml" ]]; then
    c '0;33' "Hermes requested but HERMES_HOME/config.yaml is absent — skipped"
    return
  fi
  if ! has_hermes_credential; then
    c '0;33' "Hermes requested but HERMES_API_KEY is unset/placeholder — skipped"
    return
  fi
  nohup "$hermes_bin" gateway >"$LOGS/hermes.log" 2>&1 </dev/null &
  disown
  c '0;36' "starting optional Hermes on :$HERMES_PORT  (credentials hidden)"
}

start_all() {
  set -a; [[ -f "$ROOT/.env" ]] && . "$ROOT/.env"; set +a
  preflight || { c '0;31' "preflight failed"; exit 1; }
  stop_all

  # Missing hosted credentials must select the working authored path, not a
  # six-second network timeout on every answer.
  if [[ "${BRIGHT_AGENT:-off}" == "hermes" ]] && ! has_hermes_credential; then
    export BRIGHT_AGENT=off
    c '0;33' "Hermes has no usable local API credential — BRIGHT_AGENT=off for this run"
  fi

  start_speech_if_ready

  for svc in "${SERVICES[@]}"; do
    IFS=: read -r name port cmd <<<"$svc"
    nohup $cmd >"$LOGS/$name.log" 2>&1 </dev/null &
    disown
    c '0;36' "starting $name on :$port  (log: .logs/$name.log)"
  done
  start_hermes_if_ready

  # wait for health rather than sleeping a guessed amount
  for svc in "${SERVICES[@]}"; do
    IFS=: read -r name port _ <<<"$svc"
    for _ in $(seq 1 60); do
      curl -sf --max-time 2 "http://127.0.0.1:$port/health" >/dev/null 2>&1 && break
      sleep 1
    done
  done

  if [[ -d "$ROOT/apps/classroom-ui/node_modules" ]]; then
    ( cd "$ROOT/apps/classroom-ui" && nohup pnpm dev --port "$UI_PORT" >"$LOGS/ui.log" 2>&1 </dev/null & disown )
    c '0;36' "starting ui on :$UI_PORT"
    sleep 3
  else
    nohup python3 "$ROOT/scripts/serve-ui.py" --root "$ROOT/apps/classroom-ui/dist" --port "$UI_PORT" >"$LOGS/ui.log" 2>&1 </dev/null &
    disown
    c '0;36' "starting built ui on :$UI_PORT"
  fi

  echo; c '1;32' "stack up"; status_all
  echo
  c '0;37' "  classroom  http://127.0.0.1:$UI_PORT/classroom"
  c '0;37' "  control    http://127.0.0.1:$UI_PORT/control"
  c '0;37' "  logs       tail -f .logs/*.log"
}

case "${1:-start}" in
  start)  start_all ;;
  stop)   stop_all; c '1;33' "stack down" ;;
  status) status_all ;;
  *) echo "usage: $0 [start|stop|status]" >&2; exit 2 ;;
esac
