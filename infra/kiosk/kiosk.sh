#!/usr/bin/env bash
# Launch the classroom stage full screen. This is the only thing a child ever
# sees: no address bar, no tabs, no Ubuntu, no Chrome.
#
# Run by infra/systemd/bright-kiosk.service via `xinit`, which is why this
# script must exec the browser in the foreground -- when it returns, X exits.
#
#   DISPLAY=:0 ./infra/kiosk/kiosk.sh        # against an existing X display
set -uo pipefail

KIOSK_URL="${KIOSK_URL:-http://127.0.0.1:${UI_PORT:-3000}/classroom}"
STATE_DIR="${KIOSK_STATE_DIR:-/var/lib/bright/kiosk}"

find_browser() {
  if [[ -n "${CHROMIUM_BIN:-}" && -x "${CHROMIUM_BIN}" ]]; then
    echo "$CHROMIUM_BIN"; return 0
  fi
  for candidate in chromium chromium-browser google-chrome-stable google-chrome; do
    command -v "$candidate" 2>/dev/null && return 0
  done
  return 1
}

BROWSER="$(find_browser)" || {
  cat >&2 <<'EOF'

The classroom screen cannot open because no web browser is installed.

  What to do: on the appliance run
      sudo apt-get install -y chromium
  then turn the machine off and on again.

EOF
  exit 1
}

mkdir -p "$STATE_DIR" 2>/dev/null || true

# --- power-cut hygiene ------------------------------------------------------
# When the mains goes out mid-lesson Chromium never writes `exit_type: Normal`,
# so on the next boot it puts a "Restore pages? Chrome didn't shut down
# correctly" bubble on the projector, in front of the class, with no keyboard
# and no mouse to dismiss it. --disable-session-crashed-bubble suppresses the
# bubble; rewriting the profile flag is what stops the restore prompt itself.
for prefs in "$STATE_DIR/Default/Preferences" "$STATE_DIR/Preferences"; do
  [[ -f "$prefs" ]] || continue
  python3 - "$prefs" <<'PY' 2>/dev/null || true
import json, sys
p = sys.argv[1]
try:
    d = json.load(open(p))
except Exception:
    sys.exit(0)
d.setdefault("profile", {})["exit_type"] = "Normal"
d["profile"]["exited_cleanly"] = True
tmp = p + ".tmp"
json.dump(d, open(tmp, "w"))
import os
os.replace(tmp, p)
PY
done

# --- screen hygiene ---------------------------------------------------------
# A lesson has quiet stretches. Without this the projector blanks in the middle
# of a reading task and the teacher has no keyboard to wake it.
if command -v xset >/dev/null 2>&1; then
  xset s off        || true   # no screensaver
  xset s noblank    || true
  xset -dpms        || true   # no display power management
fi
command -v unclutter >/dev/null 2>&1 && unclutter -idle 1 -root &

ARGS=(
  --kiosk "$KIOSK_URL"
  --user-data-dir="$STATE_DIR"
  --disk-cache-dir="$STATE_DIR/cache"
  --start-fullscreen
  --window-position=0,0
)

# THE flag. A kiosk has no user gesture -- nobody clicks anything before the
# lesson begins -- so Chromium keeps the AudioContext suspended and the very
# first spoken line of the lesson plays into silence. Every later line works,
# because by then a child has touched the board. That asymmetry makes this look
# like a TTS bug rather than a browser policy, and costs a day to find.
ARGS+=( --autoplay-policy=no-user-gesture-required )

# Nothing may interrupt a class with a dialog nobody can dismiss.
ARGS+=(
  --noerrdialogs
  --disable-infobars
  --disable-session-crashed-bubble
  --disable-features=Translate,InfiniteSessionRestore,MediaRouter
  --no-first-run
  --no-default-browser-check
  --disable-notifications
  --disable-popup-blocking
  --password-store=basic
)

# Offline appliance: never phone home, never wait on a network that is not
# there. An update check against a dead link is a stalled boot.
ARGS+=(
  --disable-component-update
  --disable-background-networking
  --check-for-update-interval=31536000
  --disable-sync
  --metrics-recording-only
  --disable-breakpad
)

# Live2D is WebGL. Cheap boxes ship iGPUs that Chromium blocklists; without
# this the avatar falls back to software rasterisation and eats a CPU core that
# classroom-core needs for the reflex tier (NS-2, < 100 ms).
ARGS+=(
  --ignore-gpu-blocklist
  --enable-gpu-rasterization
)

# A projector with a touch overlay, not a tablet: no pinch zoom, no
# swipe-to-go-back, no rubber-banding when a child drags a card too far.
ARGS+=(
  --disable-pinch
  --overscroll-history-navigation=0
  --touch-events=enabled
)

exec "$BROWSER" "${ARGS[@]}" "$@"
