#!/usr/bin/env bash
# Nhìn xem cô giáo đang làm gì, theo thời gian thực.
# Mở cái này ở một terminal riêng trong lúc bạn đứng trước /classroom.
set -uo pipefail
CORE="${CORE:-http://127.0.0.1:8004}"
printf '\033[1m theo dõi cô giáo \033[0m  %s   (Ctrl-C để thoát)\n\n' "$CORE"
last=""
while true; do
  body="$(curl -s --max-time 5 "$CORE/teacher/status" 2>/dev/null || true)"
  line="$(printf '%s' "$body" | python3 "$(dirname "$0")/_watch_teacher.py" 2>/dev/null || true)"
  if [[ -n "$line" && "$line" != "$last" ]]; then
    printf '%s\n\n' "$line"
    last="$line"
  fi
  sleep 2
done
