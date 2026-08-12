#!/usr/bin/env bash
# Bright — system check.
#
# Written for the person who is actually there: a teacher, alone, in a school
# with no IT support and no internet. Every line of output answers one of two
# questions — "is this part working?" and, if not, "what do I do?"
#
#   ./scripts/doctor.sh            check everything, print a report
#   ./scripts/doctor.sh --short    just the verdict
#
# Rules this script follows, because they are the difference between a useful
# tool and another thing that is broken:
#   * It never changes anything. Reading a broken system must be safe.
#   * It never prints a stack trace, an exit code, or the word "exception".
#   * It never says "failed" without saying what to do next.
#   * It works when half the system is down. That is when it is needed.
set -uo pipefail

SHORT=0
[[ "${1:-}" == "--short" ]] && SHORT=1

# ---------------------------------------------------------------- environment
# Appliance layout if it is installed; otherwise this checkout.
if [[ -d /opt/bright/current ]]; then
  ROOT=/opt/bright/current
  DATA_DEFAULT=/var/lib/bright
  MODE=appliance
else
  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  DATA_DEFAULT="$ROOT/data"
  MODE=workshop
fi
[[ -f /etc/bright/bright.env ]] && { set -a; . /etc/bright/bright.env; set +a; }
[[ -f "$ROOT/.env" ]] && { set -a; . "$ROOT/.env"; set +a; }

SPEECH_PORT="${SPEECH_PORT:-8001}"
CORE_PORT="${CORE_PORT:-8004}"
UI_PORT="${UI_PORT:-3000}"
HERMES_PORT="${HERMES_PORT:-8642}"
DATA_DIR="${DATA_DIR:-$DATA_DEFAULT}"
DB_PATH="${CORE_DB_PATH:-$DATA_DIR/bright.db}"
MODELS="${BRIGHT_MODELS:-$ROOT/models}"
[[ -d "$MODELS" ]] || MODELS="$DATA_DIR/models"

PROBLEMS=0
WARNINGS=0

# ------------------------------------------------------------------- printing
if [[ -t 1 ]]; then
  G=$'\033[0;32m'; R=$'\033[0;31m'; Y=$'\033[0;33m'; D=$'\033[2m'; B=$'\033[1m'; N=$'\033[0m'
else
  G=""; R=""; Y=""; D=""; B=""; N=""
fi

ok()   { printf '  %sworking%s   %s\n' "$G" "$N" "$1"; }
warn() { WARNINGS=$((WARNINGS+1)); printf '  %scheck%s     %s\n' "$Y" "$N" "$1"; [[ $SHORT -eq 1 ]] || printf '%s\n' "$2"; }
bad()  { PROBLEMS=$((PROBLEMS+1));  printf '  %sPROBLEM%s   %s\n' "$R" "$N" "$1"; [[ $SHORT -eq 1 ]] || printf '%s\n' "$2"; }
say()  { printf '            %s\n' "$1"; }
head2(){ printf '\n%s%s%s\n' "$B" "$1" "$N"; }

pid_on() { ss -lptn "sport = :$1" 2>/dev/null | grep -oP 'pid=\K[0-9]+' | head -1; }
health() { curl -s --max-time 4 "http://127.0.0.1:$1$2" 2>/dev/null; }
hermes_health() {
  curl -s --max-time 4 \
    -H "Authorization: Bearer ${HERMES_API_KEY:-${API_SERVER_KEY:-}}" \
    "http://127.0.0.1:$HERMES_PORT/health" 2>/dev/null
}

printf '\n%sBright — system check%s\n' "$B" "$N"
printf '%s%s  ·  %s%s\n' "$D" "$(date '+%A %d %B %Y, %H:%M')" "$MODE" "$N"

# =============================================================== 1. the parts
head2 "Is it running?"

# --- teaching program (classroom-core) --------------------------------------
core_body="$(health "$CORE_PORT" /health)"
if [[ "$core_body" == *'"status":"ok"'* ]]; then
  core_mode="$(sed -n 's/.*"mode":"\([A-Z]*\)".*/\1/p' <<<"$core_body")"
  ok "The teaching program is running.${core_mode:+  (mode: $core_mode)}"
  if [[ "$core_mode" == "OFFLINE" || "$core_mode" == "DEGRADED" ]]; then
    warn "The lesson is running WITHOUT its assistant." \
"$(say 'What this means: the lesson still plays from start to finish and'
  say 'the children can do every activity. What is missing is the part that'
  say 'adapts to the class — it will follow the plan exactly as written.'
  say ''
  say 'What to do: nothing. This is normal and the class can go ahead.'
  say 'Mention it the next time somebody visits.')"
  fi
elif [[ -n "$(pid_on "$CORE_PORT")" ]]; then
  bad "The teaching program has started but is not answering." \
"$(say 'What to do:  1. Turn the machine off, wait ten seconds, turn it on.'
  say '             2. If this message comes back, the machine needs a visit.')"
else
  bad "The teaching program is NOT running. Lessons cannot start." \
"$(say 'What to do:  1. Turn the machine off, wait ten seconds, turn it on.'
  say '             2. Wait two minutes and run this check again.'
  say '             3. If it is still not running, the machine needs a visit.')"
fi

# --- adaptive teacher (Hermes) ---------------------------------------------
hermes_body="$(hermes_health)"
if [[ "$hermes_body" == *'"status":"ok"'* || "$hermes_body" == *'"status": "ok"'* ]]; then
  ok "The adaptive teaching assistant is ready."
elif [[ -n "$(pid_on "$HERMES_PORT")" ]]; then
  warn "The adaptive assistant has started but is not ready." \
"$(say 'What this means: the lesson still works, but follows its authored plan.'
  say 'What to do: teach today; mention this the next time somebody visits.')"
else
  warn "The adaptive teaching assistant is offline." \
"$(say 'What this means: the lesson still works from start to finish, but it'
  say 'will not adapt its next activity to the class today.'
  say ''
  say 'What to do: nothing during class. The authored lesson is the safe fallback.')"
fi

# --- classroom screen (ui) ---------------------------------------------------
if [[ -n "$(health "$UI_PORT" /__health)" || -n "$(pid_on "$UI_PORT")" ]]; then
  ok "The classroom screen is being served."
else
  bad "The classroom screen is NOT being served. The projector will be blank." \
"$(say 'What to do:  1. Turn the machine off and on again.'
  say '             2. If it stays blank, the machine needs a visit.')"
fi

# --- voice (speech) ----------------------------------------------------------
sp_body="$(health "$SPEECH_PORT" /health)"
if [[ "$sp_body" == *'"status":"ok"'* ]]; then
  if [[ "${sp_body//[[:space:]\"]/}" == *'stt:true'* ]]; then
    ok "The voice works: the character can speak and can hear the children."
  else
    warn "The character can SPEAK but cannot HEAR the children." \
"$(say 'What this means: activities where a child answers out loud will not'
  say 'work. Everything the children tap or point at still works.'
  say ''
  say 'What to do: turn the machine off and on again. If it comes back,'
  say 'the listening files may be missing — see the next section.')"
  fi
else
  bad "The voice is NOT running. The character will be silent." \
"$(say 'What this means: the lesson still appears on screen but nothing is'
  say 'spoken aloud.'
  say ''
  say 'What to do:  1. Turn the machine off and on again.'
  say '             2. Wait THREE minutes — the voice takes the longest to'
  say '                wake up — and run this check again.')"
fi

# --- the projector -----------------------------------------------------------
if [[ $MODE == appliance ]]; then
  if systemctl is-active --quiet bright-kiosk.service 2>/dev/null; then
    ok "The projector screen is on."
  else
    bad "The projector screen is not on." \
"$(say 'What to do:  1. Check the projector cable is pushed in at both ends'
  say '                and that the projector itself is switched on.'
  say '             2. Turn the machine off and on again.')"
  fi
fi

# ======================================================== 2. starts by itself
if [[ $MODE == appliance ]]; then
  head2 "Will it start by itself next time?"
  missing=""
  for unit in bright-speech bright-core bright-hermes bright-ui bright-kiosk; do
    systemctl is-enabled --quiet "$unit.service" 2>/dev/null || missing="$missing $unit"
  done
  if [[ -z "$missing" ]]; then
    ok "Yes. Switching the machine on is all anyone has to do."
  else
    bad "No — some parts will not come back after a power cut:$missing" \
"$(say 'What to do: this one needs somebody with the password. Ask them to run'
  say '   sudo systemctl enable bright.target bright-core bright-hermes bright-ui bright-speech bright-kiosk')"
  fi
fi

# ============================================================== 3. the files
head2 "Are the lesson files and voices on the machine?"

check_file() {  # path, human name, consequence, fix
  if [[ -s "$1" ]]; then ok "$2"
  else bad "MISSING — $2" "$(say "$3"; say ''; say "What to do: $4")"; fi
}

check_file "$MODELS/piper/en_US-lessac-medium.onnx" \
  "English voice." \
  "Without it the character cannot speak English." \
  "the machine needs a visit with a Bright USB stick."
check_file "$MODELS/piper/vi_VN-vais1000-medium.onnx" \
  "Vietnamese voice." \
  "Without it the character cannot explain in Vietnamese when a child is stuck." \
  "the machine needs a visit with a Bright USB stick."

if compgen -G "$MODELS/whisper/*" >/dev/null 2>&1; then
  ok "Listening files (so the character can hear the children)."
else
  bad "MISSING — listening files." \
"$(say 'Without them the character cannot hear the children speak.'
  say ''
  say 'What to do: the machine needs a visit with a Bright USB stick.')"
fi

if compgen -G "$MODELS/live2d/*.moc3" >/dev/null 2>&1 || \
   compgen -G "$ROOT/apps/classroom-ui/dist/live2d/*" >/dev/null 2>&1; then
  ok "The character's animation files."
else
  warn "The character's animation files are missing." \
"$(say 'The lesson still works, but there will be no character on screen.'
  say ''
  say 'What to do: mention it the next time somebody visits.')"
fi

if [[ -s "$ROOT/apps/classroom-ui/dist/index.html" ]]; then
  ok "The classroom screen has been built."
else
  bad "The classroom screen has not been installed properly." \
"$(say 'The projector will show an error page instead of the lesson.'
  say ''
  say 'What to do: run the update from the USB stick again:'
  say "   $ROOT/scripts/usb-update.sh")"
fi

# ============================================== 4. the children's records
head2 "Are the children's records safe?"

if [[ ! -f "$DB_PATH" ]]; then
  warn "No records yet — no class has been taught on this machine." \
"$(say 'What to do: nothing. This is what a brand-new machine looks like.')"
else
  # Read-only integrity check. `sqlite3` is often not installed on a minimal
  # appliance image, so go through Python, which is guaranteed to be there
  # because the services are written in it.
  report="$(python3 - "$DB_PATH" <<'PY' 2>/dev/null
import sqlite3, sys, os
p = sys.argv[1]
try:
    # immutable=0, but open read-only so a check can never be the thing that
    # breaks the records it is checking.
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    integrity = c.execute("PRAGMA integrity_check").fetchone()[0]
    journal = c.execute("PRAGMA journal_mode").fetchone()[0]
    try:
        students = c.execute("SELECT count(*) FROM students").fetchone()[0]
        obs = c.execute("SELECT count(*) FROM observations").fetchone()[0]
    except sqlite3.Error:
        students = obs = -1
    c.close()
    wal = os.path.getsize(p + "-wal") if os.path.exists(p + "-wal") else 0
    print(f"{integrity}|{journal}|{students}|{obs}|{wal}")
except Exception as exc:
    print(f"UNREADABLE|{exc}|0|0|0")
PY
)"
  IFS='|' read -r integrity journal students obs walsize <<<"${report:-UNREADABLE|no answer|0|0|0}"

  if [[ "$integrity" == "ok" ]]; then
    ok "The records file is undamaged.  ($students children, $obs notes)"
  elif [[ "$integrity" == "UNREADABLE" ]]; then
    bad "The children's records cannot be read." \
"$(say 'What this means: the lesson will still run, but the machine will not'
  say 'remember what each child struggled with last week.'
  say ''
  say 'What to do: do NOT delete anything. The machine needs a visit — the'
  say "records are in  $DB_PATH")"
  else
    bad "The children's records are damaged." \
"$(say 'What to do: do NOT delete anything and do NOT keep teaching on this'
  say 'machine if you can avoid it. It needs a visit. The records are in'
  say "  $DB_PATH")"
  fi

  if [[ "$journal" == "wal" ]]; then
    ok "The records survive a power cut mid-lesson."
  else
    bad "The records are NOT protected against a power cut (mode: $journal)." \
"$(say 'What this means: if the power goes out during a lesson, this machine'
  say 'can lose or damage what it knows about the children.'
  say ''
  say 'What to do: the machine needs a visit. Do not wait for it to happen.')"
  fi

  if (( walsize > 64*1024*1024 )); then
    warn "The records have a large amount of unfiled work ($((walsize/1024/1024)) MB)." \
"$(say 'What to do: turn the machine off and on again — it files itself away'
  say 'on a clean shutdown. Mention it if it comes back.')"
  fi
fi

# --- the disk under the records ---------------------------------------------
fstype="$(stat -f -c %T "$DATA_DIR" 2>/dev/null)"
case "$fstype" in
  ext2/ext3|xfs|btrfs|ext4) : ;;
  "") : ;;
  *) warn "The records are stored on an unusual disk ($fstype)." \
"$(say 'What this means: on this kind of storage the protection against power'
  say 'cuts cannot be relied on. This is normal on a development laptop and'
  say 'wrong on a school machine.'
  say ''
  say 'What to do: if this is a school machine, it needs a visit.')" ;;
esac

# ================================================================= 5. space
head2 "Is there room, and is the clock right?"

avail_kb="$(df -Pk "$DATA_DIR" 2>/dev/null | awk 'NR==2{print $4}')"
if [[ -n "$avail_kb" ]]; then
  avail_gb=$(( avail_kb / 1024 / 1024 ))
  if (( avail_kb < 512*1024 )); then
    bad "The disk is full. Lessons will stop working very soon." \
"$(say 'What to do: the machine needs a visit. Nothing here is safe to delete'
  say 'without help.')"
  elif (( avail_kb < 3*1024*1024 )); then
    warn "The disk is nearly full (${avail_gb} GB left)." \
"$(say 'What to do: mention this the next time somebody visits.')"
  else
    ok "There is room on the disk (${avail_gb} GB free)."
  fi
fi

year="$(date +%Y)"
if (( year < 2026 || year > 2100 )); then
  bad "The machine's clock is wrong (it thinks it is $year)." \
"$(say 'What this means: lessons will be filed under the wrong date, so'
  say '"what this child did last week" will be wrong.'
  say ''
  say 'What to do: the small battery inside the machine has run out. It needs'
  say 'a visit. Teaching still works in the meantime.')"
else
  ok "The clock looks right ($(date '+%d %B %Y'))."
fi

# ============================================================ 6. privacy
head2 "Is anything visible from outside this machine?"
external="$(ss -lptn 2>/dev/null | awk 'NR>1 {print $4}' \
  | grep -Ev '^(127\.|\[::1\]|\[::ffff:127)' \
  | grep -E ":($SPEECH_PORT|$CORE_PORT|$HERMES_PORT|$UI_PORT)$")"
if [[ -z "$external" ]]; then
  ok "No. Nothing about the children leaves this machine."
else
  bad "Part of the system is reachable from the network." \
"$(say 'What this means: children'"'"'s records could be read by another'
  say 'computer on the same network. This must not happen.'
  say ''
  say 'What to do: unplug the network cable and ask for a visit.'
  say "Details: $external")"
fi

# ================================================================= verdict
printf '\n'
if (( PROBLEMS == 0 && WARNINGS == 0 )); then
  printf '%s  Everything is working. You can start the lesson.%s\n\n' "$G" "$N"
  exit 0
elif (( PROBLEMS == 0 )); then
  printf '%s  You can teach today.%s %d thing(s) to mention next time somebody visits.\n\n' \
    "$G" "$N" "$WARNINGS"
  exit 0
else
  printf '%s  %d problem(s) found.%s Read the "What to do" lines above, in order.\n' \
    "$R" "$PROBLEMS" "$N"
  printf '  Almost everything is fixed by turning the machine off, waiting ten\n'
  printf '  seconds, turning it on, waiting two minutes, and running this again.\n\n'
  exit 1
fi
