#!/usr/bin/env bash
# Build a Bright update stick. Run this at HQ, on a machine WITH internet.
#
#   ./scripts/make-usb-bundle.sh /media/me/BRIGHT
#   ./scripts/make-usb-bundle.sh --version 2026-09-A /media/me/BRIGHT
#
# The stick that comes out is self-contained: everything the appliance needs,
# plus the script that installs it, plus a page of instructions in plain
# language for whoever carries it. It never needs the network at the far end.
#
# Internet exists at authoring time; it only disappears at teaching time. This
# script is the seam between those two worlds.
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VERSION=""
DEST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --version) VERSION="$2"; shift 2 ;;
    -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
    *) DEST="$1"; shift ;;
  esac
done

die()  { printf '\n\033[0;31m%s\033[0m\n\n' "$*" >&2; exit 1; }
step() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }
note() { printf '    %s\n' "$*"; }

[[ -n "$DEST" ]] || die "Where should the bundle go?
  Usage: $0 [--version NAME] /path/to/usb/stick"
VERSION="${VERSION:-$(date +%Y-%m-%d-%H%M)}"
OUT="$DEST/BRIGHT-UPDATE"

# --- 1. everything that must exist before we copy anything ------------------
step "checking what we are about to ship"

DIST="$ROOT/apps/classroom-ui/dist"
[[ -s "$DIST/index.html" ]] || die "The classroom screen has not been built.
  Run first:  cd apps/classroom-ui && pnpm install && pnpm build"

# A stale dist is the classic way to ship an update that changes nothing. This
# is a warning and not an error, because a content-only update is legitimate.
newest_src="$(find "$ROOT/apps/classroom-ui/src" "$ROOT/packages" -type f \
              -newer "$DIST/index.html" -print -quit 2>/dev/null)"
[[ -n "$newest_src" ]] && printf '\033[0;33m    WARNING: source is newer than the build (%s).\n    Run `pnpm build` before shipping, or this update ships the old screen.\033[0m\n' \
  "$(basename "$newest_src")"

step "models"
"$ROOT/scripts/fetch-models.sh" all || die "Could not fetch the models.
  This machine needs internet. Nothing has been written to the stick."

# --- 2. python dependencies, as wheels --------------------------------------
# The appliance has no internet, so `pip install` there must resolve entirely
# from files on this stick.
step "python packages (for offline install on the appliance)"
WHEELS="$ROOT/.build/wheels"
mkdir -p "$WHEELS"
if pip download --dest "$WHEELS" -r "$ROOT/services/speech/requirements.txt" >/dev/null 2>&1; then
  note "$(ls "$WHEELS" | wc -l) packages"
else
  printf '\033[0;33m    WARNING: could not download python packages. The stick will\n    still update lessons and models, but not the program itself.\033[0m\n'
fi

# --- 3. copy ----------------------------------------------------------------
step "writing to $OUT"
mkdir -p "$OUT" || die "Cannot write to $DEST — is the stick plugged in and unlocked?"

copy() {  # src dst
  [[ -e "$1" ]] || return 0
  mkdir -p "$(dirname "$2")"
  rsync -a --delete --exclude '__pycache__' --exclude '*.pyc' "$1" "$2"
}

# The program. node_modules and .git are deliberately absent: the appliance
# runs the built dist and the Python services, and nothing else.
rsync -a --delete \
  --exclude '.git' --exclude 'node_modules' --exclude '.logs' --exclude '.build' \
  --exclude 'models' --exclude 'data' --exclude '__pycache__' --exclude '*.pyc' \
  --exclude 'references' --exclude '.venv' \
  "$ROOT/" "$OUT/app/"

copy "$ROOT/models/"  "$OUT/models/"
copy "$ROOT/content/" "$OUT/content/"
copy "$WHEELS/"       "$OUT/app/wheels/"

# The stick installs itself. Nobody at the far end should have to know a path.
cp "$ROOT/scripts/usb-update.sh" "$OUT/update.sh"
chmod +x "$OUT/update.sh"

# --- 4. manifest + checksums ------------------------------------------------
step "checksums (so a half-copied stick can never be installed)"
( cd "$OUT" && find app models content -type f -print0 2>/dev/null \
    | sort -z | xargs -0 sha256sum > SHA256SUMS )
note "$(wc -l < "$OUT/SHA256SUMS") files"

cat >"$OUT/MANIFEST.json" <<EOF
{
  "version": "$VERSION",
  "created": "$(date -Iseconds)",
  "createdOn": "$(hostname)",
  "components": {
    "app": true,
    "models": $([[ -d "$OUT/models" ]] && echo true || echo false),
    "content": $([[ -d "$OUT/content" ]] && echo true || echo false),
    "wheels": $([[ -d "$OUT/app/wheels" ]] && echo true || echo false)
  },
  "sizeBytes": $(du -sb "$OUT" | cut -f1),
  "signed": false
}
EOF

# Signing is deliberately NOT implemented rather than half-implemented. A
# checksum proves the stick is intact; it does not prove who made it. Before
# these go out to schools at any scale, this needs a detached signature over
# SHA256SUMS and a public key baked into the appliance image, or anybody who
# can write to a USB stick can put code on every machine in the programme.
# Tracked as a blocker for the pilot, not for the demo.

cat >"$OUT/README.txt" <<EOF
BRIGHT — UPDATE STICK
Version $VERSION

WHAT THIS IS
  New lessons and a newer version of the program, for the classroom machine.

WHAT TO DO
  1. The classroom machine should be ON, with the lesson screen showing.
  2. Plug this stick into the machine.
  3. Somebody with the machine's password runs this one line:
         sudo /opt/bright/current/scripts/usb-update.sh
  4. Wait. It takes about five minutes and it says what it is doing.
     The lesson screen may go dark once; that is normal.
  5. When it says FINISHED, take the stick out.

  (If this machine has been set up to update by itself, step 3 happens on its
  own a few seconds after you plug the stick in. You will see it start.)

IF SOMETHING GOES WRONG
  The machine puts itself back the way it was and keeps teaching with the old
  lessons. Nothing is lost. Take the stick out, and tell whoever gave it to
  you what you saw on the screen.

IF YOU ARE NOT SURE THE STICK IS ANY GOOD
  This checks it and changes nothing:
      /opt/bright/current/scripts/usb-update.sh --check
EOF

step "done"
printf '\n  %s\n  %s files, %s\n\n' "$OUT" \
  "$(wc -l < "$OUT/SHA256SUMS")" "$(du -sh "$OUT" | cut -f1)"
printf '  Eject the stick properly before unplugging it, or the checksums on\n'
printf '  it will be right and the files will not.\n\n'
