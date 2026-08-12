#!/usr/bin/env bash
# Block until a Bright service reports healthy, or give up.
#
#   ./scripts/wait-healthy.sh <url> [timeout_seconds] [require_key]
#
# Used as `ExecStartPost=` in the systemd units. That matters: systemd's
# `After=` only orders *process start*, not *readiness*. A unit whose
# ExecStartPost blocks is not considered "started" until it returns, so
# putting the health poll here is what makes `After=` mean what a reader
# assumes it means. Without it the kiosk opens the page before classroom-core
# is listening, the WebSocket fails, and the first thing a teacher sees is a
# reconnect spinner.
#
# `require_key` is an optional literal that must appear in the response body.
# The speech service answers /health as soon as its HTTP server is up, but
# reports `"stt":true` only once Whisper is actually resident. Loading Whisper
# is the single largest term in the cold-boot budget, so "the port is open" is
# not the same question as "the class can start".
set -uo pipefail

URL="${1:?usage: wait-healthy.sh <url> [timeout_s] [require_key]}"
TIMEOUT="${2:-120}"
REQUIRE="${3:-}"

start=$(date +%s)
last=""

# Quotes and spaces are stripped from both sides before comparing, so a unit
# file can pass a plain `stt:true` and never fight systemd's escaping rules
# over the `"` characters in the real JSON.
normalise() { tr -d '"[:space:]' <<<"$1"; }

while :; do
  body="$(curl -sf --max-time 3 "$URL" 2>/dev/null)" && {
    if [[ -z "$REQUIRE" || "$(normalise "$body")" == *"$(normalise "$REQUIRE")"* ]]; then
      printf 'ready after %ss: %s %s\n' "$(( $(date +%s) - start ))" "$URL" "$body"
      exit 0
    fi
    last="$body"
  }
  if (( $(date +%s) - start >= TIMEOUT )); then
    printf 'NOT READY after %ss: %s\n' "$TIMEOUT" "$URL" >&2
    [[ -n "$last" ]] && printf 'last answer was: %s\n' "$last" >&2
    [[ -n "$REQUIRE" ]] && printf 'was waiting for: %s\n' "$REQUIRE" >&2
    printf 'What to do: run ./scripts/doctor.sh — it will say which part is missing.\n' >&2
    exit 1
  fi
  sleep 1
done
