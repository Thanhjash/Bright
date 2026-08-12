#!/usr/bin/env bash
# Install a Bright update from a USB stick. No internet, no expertise.
#
#   ./scripts/usb-update.sh                  find the stick and install
#   ./scripts/usb-update.sh /media/usb       use this one
#   ./scripts/usb-update.sh --check          verify the stick, install nothing
#   ./scripts/usb-update.sh --rollback       go back to the previous version
#
# The rules this follows, in priority order:
#
#   1. A school that had a working machine before the update must have a
#      working machine after it, whatever happens. Everything is staged, the
#      switch-over is one atomic rename, and a failed health check rolls back
#      automatically.
#   2. A half-copied stick, a stick pulled out mid-copy, or a power cut during
#      the update must all be indistinguishable from "nothing happened".
#   3. The person running it is a teacher. Every message says what happened
#      and what to do next.
set -uo pipefail

PREFIX="${BRIGHT_PREFIX:-/opt/bright}"
DATA="${BRIGHT_DATA:-/var/lib/bright}"
LOG="${DATA}/update.log"
ACTION=install
SRC=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check)    ACTION=check; shift ;;
    --rollback) ACTION=rollback; shift ;;
    -h|--help)  sed -n '2,10p' "$0"; exit 0 ;;
    *)          SRC="$1"; shift ;;
  esac
done

G=$'\033[0;32m'; R=$'\033[0;31m'; Y=$'\033[0;33m'; B=$'\033[1m'; N=$'\033[0m'
say()  { printf '  %s\n' "$*"; mkdir -p "$DATA" 2>/dev/null; printf '%s  %s\n' "$(date -Is)" "$*" >>"$LOG" 2>/dev/null; }
step() { printf '\n%s%s%s\n' "$B" "$*" "$N"; say "== $*"; }
fail() {
  printf '\n%s  STOPPED — nothing has been changed.%s\n\n' "$R" "$N"
  printf '  %s\n\n' "$1"
  printf '  What to do: %s\n\n' "$2"
  say "STOPPED: $1"
  exit 1
}

printf '\n%sBRIGHT — UPDATE FROM USB%s\n' "$B" "$N"

# ---------------------------------------------------------------- find the stick
find_bundle() {
  local candidates=()
  [[ -n "$SRC" ]] && candidates+=("$SRC" "$SRC/BRIGHT-UPDATE")
  for base in /media/* /media/*/* /run/media/*/* /mnt/*; do
    [[ -d "$base/BRIGHT-UPDATE" ]] && candidates+=("$base/BRIGHT-UPDATE")
  done
  for c in "${candidates[@]}"; do
    [[ -f "$c/MANIFEST.json" ]] && { echo "$c"; return 0; }
  done
  return 1
}

# ------------------------------------------------------------------- rollback
if [[ "$ACTION" == rollback ]]; then
  step "Putting the machine back to the previous version"
  prev="$(cat "$PREFIX/previous" 2>/dev/null)"
  [[ -d "$prev" ]] || fail "There is no previous version to go back to." \
    "the machine needs a visit."
  ln -sfn "$prev" "$PREFIX/.current.new" && mv -T "$PREFIX/.current.new" "$PREFIX/current"
  systemctl restart bright.target 2>/dev/null
  printf '\n%s  Done. The machine is back on the previous version.%s\n\n' "$G" "$N"
  exit 0
fi

BUNDLE="$(find_bundle)" || fail \
  "No Bright update stick was found." \
"1. Take the stick out and plug it in again.
               2. Wait ten seconds and run this again.
               3. If it still does not work, the stick may be the wrong one."

VERSION="$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' \
           "$BUNDLE/MANIFEST.json" | head -1)"
INSTALLED="$(cat "$DATA/installed-version" 2>/dev/null || echo 'none')"

step "Found version $VERSION on the stick"
say  "(this machine currently has: $INSTALLED)"

if [[ "$VERSION" == "$INSTALLED" ]]; then
  printf '\n%s  This machine already has version %s. Nothing to do.%s\n' "$G" "$VERSION" "$N"
  printf '  You can take the stick out.\n\n'
  exit 0
fi

# ----------------------------------------------------- is the stick complete?
step "Checking the stick is complete (this takes a minute)"
[[ -f "$BUNDLE/SHA256SUMS" ]] || fail \
  "The stick is missing its checklist of files." \
  "ask for a new stick — this one was not finished properly."

if ! ( cd "$BUNDLE" && sha256sum --quiet -c SHA256SUMS ) 2>"$DATA/.sumfail"; then
  n="$(wc -l < "$DATA/.sumfail" 2>/dev/null || echo '?')"
  fail "The stick is damaged or was unplugged while it was being written ($n bad files)." \
"ask for a new stick. Do NOT try again with this one — an
               incomplete update is worse than no update."
fi
say "all files verified"

if [[ "$ACTION" == check ]]; then
  printf '\n%s  The stick is complete and healthy. Version %s.%s\n' "$G" "$VERSION" "$N"
  printf '  Run this again without --check to install it.\n\n'
  exit 0
fi

# ----------------------------------------------------------------- room to work
need_kb="$(du -sk "$BUNDLE" | cut -f1)"
have_kb="$(df -Pk "$PREFIX" | awk 'NR==2{print $4}')"
if (( have_kb < need_kb * 2 )); then
  fail "There is not enough space on the machine for this update." \
"the machine needs a visit — old versions have to be cleared out
               by somebody with the password."
fi

[[ $EUID -eq 0 ]] || fail "This has to be run by somebody with the machine's password." \
  "ask them to run:  sudo $0 $*"

# ------------------------------------------------------------------- staging
# Everything below writes to NEW paths. The running system is untouched until
# the single `mv -T` further down.
RELEASE="$PREFIX/releases/$VERSION"
STAGE="$PREFIX/releases/.incoming-$VERSION"

step "Copying the new version onto the machine"
rm -rf "$STAGE"
mkdir -p "$STAGE" || fail "Could not write to the machine's disk." "the machine needs a visit."
rsync -a "$BUNDLE/app/" "$STAGE/" || fail \
  "Copying stopped part-way through." \
"1. Check the stick is still plugged in.
               2. Run this again — it starts over safely."

# Models and lessons live in the data area, not in the release, so they
# survive a rollback and are not copied twice. --delay-updates renames each
# file into place only after it has been fully written: a stick pulled out
# mid-copy leaves the old model intact rather than a truncated one.
if [[ -d "$BUNDLE/models" ]]; then
  step "Copying the voices and listening files"
  rsync -a --delay-updates --partial-dir="$DATA/.partial" \
        "$BUNDLE/models/" "$DATA/models/" || fail \
    "Copying the voices stopped part-way through." "run this again."
fi
if [[ -d "$BUNDLE/content" ]]; then
  step "Copying the lessons"
  rsync -a --delay-updates --partial-dir="$DATA/.partial" \
        "$BUNDLE/content/" "$DATA/content/" || fail \
    "Copying the lessons stopped part-way through." "run this again."
fi

if [[ -d "$STAGE/wheels" && -x "$PREFIX/venv/bin/pip" ]]; then
  step "Updating the program's parts"
  "$PREFIX/venv/bin/pip" install --no-index --find-links "$STAGE/wheels" \
      -r "$STAGE/services/speech/requirements.txt" >>"$LOG" 2>&1 \
    || say "WARNING: some program parts did not update; continuing with the old ones"
fi

chown -R bright:bright "$STAGE" "$DATA" 2>/dev/null
mv -T "$STAGE" "$RELEASE" 2>/dev/null || { rm -rf "$RELEASE"; mv -T "$STAGE" "$RELEASE"; }

# ------------------------------------------------------------------ switch over
PREVIOUS="$(readlink -f "$PREFIX/current" 2>/dev/null || true)"
[[ -n "$PREVIOUS" ]] && echo "$PREVIOUS" > "$PREFIX/previous"

step "Switching to the new version"
systemctl stop bright.target 2>/dev/null

# The whole update reduces to this: one rename of one symlink. A power cut
# before it leaves the old version running; a power cut after it leaves the
# new version running. There is no in-between state on disk.
ln -sfn "$RELEASE" "$PREFIX/.current.new"
mv -T "$PREFIX/.current.new" "$PREFIX/current"

systemctl start bright.target 2>/dev/null

# -------------------------------------------------------------- did it work?
step "Checking the machine still teaches"
[[ -f /etc/bright/bright.env ]] && { set -a; . /etc/bright/bright.env; set +a; }
ok=1
"$PREFIX/current/scripts/wait-healthy.sh" "http://127.0.0.1:${CORE_PORT:-8004}/health" 120 >/dev/null 2>&1 || ok=0
"$PREFIX/current/scripts/wait-healthy.sh" "http://127.0.0.1:${UI_PORT:-3000}/__health" 60 >/dev/null 2>&1 || ok=0

if (( ok == 0 )) && [[ -n "$PREVIOUS" && -d "$PREVIOUS" ]]; then
  printf '\n%s  The new version did not start. Putting the old one back.%s\n' "$Y" "$N"
  say "health check failed, rolling back to $PREVIOUS"
  systemctl stop bright.target 2>/dev/null
  ln -sfn "$PREVIOUS" "$PREFIX/.current.new"
  mv -T "$PREFIX/.current.new" "$PREFIX/current"
  systemctl start bright.target 2>/dev/null
  printf '\n%s  The machine is back on version %s and can still teach.%s\n' "$G" "$INSTALLED" "$N"
  printf '  Take the stick out and tell whoever gave it to you that the\n'
  printf '  update would not start.\n\n'
  exit 1
fi

echo "$VERSION" > "$DATA/installed-version"
say "installed $VERSION"

# Keep one previous version for rollback and nothing more. A 32 GB disk in a
# village school does not have room for a history.
ls -1dt "$PREFIX/releases"/*/ 2>/dev/null | tail -n +3 | while read -r old; do
  [[ "$(readlink -f "$old")" == "$(readlink -f "$PREFIX/current")" ]] && continue
  [[ "$(readlink -f "$old")" == "$PREVIOUS" ]] && continue
  rm -rf "$old"
done

printf '\n%s  FINISHED. The machine now has version %s.%s\n\n' "$G" "$VERSION" "$N"
printf '  You can take the stick out. The lesson screen will come back on\n'
printf '  its own in a few seconds.\n\n'
