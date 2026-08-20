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
if curl -sf -X POST --max-time 240 "http://127.0.0.1:${CORE_PORT:-8004}/teacher/prepare" >/dev/null; then
  echo "retake: the period is drafted -- the opening turn will be a greeting, not homework"
else
  echo "retake: WARNING the period is NOT drafted -- the first turn will take about a minute"
fi

echo
echo "  the door:  http://127.0.0.1:3000/"
echo "  the room:  http://127.0.0.1:3000/classroom"
