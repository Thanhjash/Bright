#!/usr/bin/env bash
# Drive one lesson the way a child would, and report what actually reached the
# board. This is a REHEARSAL HARNESS, not a test of the teacher's judgement:
# it asserts that the machinery carried her moves, never that she made the
# right ones. Nothing here may tell her what to teach -- every line below is
# either something a child says or a read of what she did in response.
set -uo pipefail
CORE="${CORE:-http://127.0.0.1:8004}"
PAUSE="${PAUSE:-2}"

say_as_child() {   # $1 = what the child says out loud
  printf '\n\033[36m child ▸\033[0m %s\n' "$1"
  curl -s --max-time 180 -X POST "$CORE/teacher/turn" \
    -H 'content-type: application/json' \
    -d "$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$1")" \
    >/dev/null
  show_board
}

show_board() {
  curl -s --max-time 10 "$CORE/teacher/status" | python3 - <<'PY'
import json, sys, textwrap
s = json.load(sys.stdin)
say = (s.get("lastSay") or "").strip()
print("\033[33m teacher ◂\033[0m " + (textwrap.fill(say, 92, subsequent_indent=" " * 11) or "(silent)"))
fault = s.get("lastFault")
if fault:
    print("\033[31m  FAULT   \033[0m " + json.dumps(fault)[:200])
print(f"\033[90m  unit={s.get('unitId')} session={s.get('sessionOpen')} busy={s.get('turnBusy')}\033[0m")
PY
}

board_contents() {
  printf '\n\033[35m=== what is on the board ===\033[0m\n'
  curl -s --max-time 10 "$CORE/teacher/board" 2>/dev/null \
    | python3 -m json.tool 2>/dev/null \
    || echo "(no /teacher/board endpoint -- read it from the projector)"
}

printf '\033[1m Bright -- lesson rehearsal \033[0m  core=%s\n' "$CORE"
curl -sf --max-time 3 "$CORE/teacher/status" >/dev/null || { echo "core is not up"; exit 1; }

printf '\n\033[35m--- she opens the class herself ---\033[0m\n'
curl -s -X POST "$CORE/teacher/session" -H 'content-type: application/json' \
  -d '{"learnerId":"learner-1","learnerName":"Minh","open":false}' | python3 -m json.tool
say_as_child '[sat_down]'

# A child arriving at Unit 1 knows nothing. These are utterances, not cues.
for line in \
  "Hello. I'm Minh." \
  "Hello." \
  "I don't understand." \
  "How are you?" \
  "Fine, thank you." \
  "Xin chào cô." \
  "Goodbye."
do
  sleep "$PAUSE"
  say_as_child "$line"
done

board_contents
printf '\n\033[1m done \033[0m Watch %s for the board, the pictures and the audio.\n' "http://127.0.0.1:3000/classroom"
