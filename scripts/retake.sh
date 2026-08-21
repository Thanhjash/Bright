#!/usr/bin/env bash
# Put the room back to the start of the unit, between takes.
#
# Two things go stale after a rehearsal and both are silent:
#
#  1. REOPEN_AFTER_CLOSE_S. Once she has closed a period the room refuses to
#     open another for ten minutes -- no error, no log line anyone would look
#     at, just a pressed card and nothing happening. This exports
#     BRIGHT_REOPEN_AFTER_CLOSE_S=15 so a retake is not a coffee break.
#  2. `sessions`. Every completed take increments PERIODS_HELD, so take two of
#     "Period 1" opens as Period 2 and the front door locks the card you meant
#     to press.
#
#     ./scripts/retake.sh          reset to Period 1 and bring the stack up
#     ./scripts/retake.sh --keep   restart with the record intact
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

"$ROOT/scripts/teacher-agent-l1.sh" stop || true
sleep 1

if [[ "${1:-}" != "--keep" ]]; then
  mkdir -p .runtime/db-backup
  if [[ -f data/bright.db ]]; then
    # Never delete the only copy of what the room witnessed.
    cp data/bright.db ".runtime/db-backup/bright-$(date +%Y%m%d-%H%M%S).db"
  fi
  rm -f data/bright.db data/bright.db-wal data/bright.db-shm
  echo "retake: the record is reset; she will teach Period 1"
fi

BRIGHT_REOPEN_AFTER_CLOSE_S="${BRIGHT_REOPEN_AFTER_CLOSE_S:-15}" \
  "$ROOT/scripts/teacher-agent-l1.sh" start

# Restart the UI too, and do NOT trust hot reload.
#
# Vite's file watcher does not see edits under /mnt/d (the WSL 9p bridge), so a
# dev server started before a change goes on serving the old modules. That cost
# an hour three separate times on 2026-08-21 -- every measurement said "no
# change" and the fix looked wrong when it was the server that was stale. The
# launcher does not manage the UI, so it is restarted here where a person will
# actually see it happen.
UI_PORT="${UI_PORT:-3000}"
UI_PID="$(ss -lptn "sport = :$UI_PORT" 2>/dev/null | grep -o 'pid=[0-9]*' | head -1 | cut -d= -f2 || true)"
[[ -n "${UI_PID:-}" ]] && kill "$UI_PID" 2>/dev/null && sleep 2
( cd "$ROOT/apps/classroom-ui" && nohup pnpm dev --port "$UI_PORT" \
    > "$ROOT/.runtime/teacher-agent/logs/ui.log" 2>&1 & disown )
for _ in $(seq 1 40); do
  curl -sf -o /dev/null --max-time 2 "http://127.0.0.1:$UI_PORT/" && break
  sleep 2
done
echo "retake: the room is serving current code on :$UI_PORT"

# The arrival line is the first thing anyone hears and VieNeu is ~10s cold.
# Warming is idempotent and takes seconds when everything is already cached.
python3 "$ROOT/tools/warm-tts.py" >/dev/null 2>&1 \
  && echo "retake: the unit's spoken lines are warm" \
  || echo "retake: WARNING could not warm TTS -- the opening line will be slow"

# Draft the period while nobody is waiting.
#
# Resetting the database deletes `lesson_plans` along with everything else --
# including the `prepare:<unit>` row -- so without this every take films the
# cold first turn: ~70 seconds of her reading the unit map and writing a plan
# while the class looks at a blank board. `start_teacher_session` already
# replays a prepared plan when one exists; this is what makes one exist.
#
# It runs with a restricted tool set (PREPARE_TOOLS) and cannot say a word, so
# it is safe to fire at a room with nobody in it.
echo "retake: asking her to draft the period (about a minute, nobody is waiting)…"
# Retry, because the turn is flaky in a way that costs the whole rehearsal.
# Observed 2026-08-21: one prepare run used 11 tools and wrote a 346-character
# plan; the very next used ZERO tools and wrote nothing at all -- the model
# simply did nothing that time. HTTP still answered 200, so a single attempt
# cannot tell "she drafted it" from "she went quiet"; only the returned `ok`
# can, and without a retry one bad roll means the opening turn on camera is the
# slow one.
drafted=no
for attempt in 1 2 3; do
  reply="$(curl -sf -X POST --max-time 240 "http://127.0.0.1:${CORE_PORT:-8004}/teacher/prepare" || true)"
  case "$reply" in
    *'"ok": true'*|*'"ok":true'*) drafted=yes; break ;;
  esac
  [[ $attempt -lt 3 ]] && echo "retake: she drafted nothing on attempt $attempt; asking again"
done
if [[ "$drafted" == yes ]]; then
  echo "retake: the period is drafted -- the opening turn will be a greeting, not homework"
else
  echo "retake: WARNING the period is NOT drafted -- the first turn will take about a minute"
fi

echo
echo "  the door:  http://127.0.0.1:3000/"
echo "  the room:  http://127.0.0.1:3000/classroom"
