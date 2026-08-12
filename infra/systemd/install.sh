#!/usr/bin/env bash
# Install Bright as an appliance: a system user, the directory layout, the
# systemd units, and nothing else. Run once, as root, on the box that will
# live in the school.
#
#   sudo ./infra/systemd/install.sh /opt/bright/releases/2026-08-11
#
# Idempotent: safe to re-run. It never overwrites /etc/bright/bright.env once
# that file exists, because that is where the school's own settings live.
set -uo pipefail

RELEASE="${1:-}"
PREFIX=/opt/bright
DATA=/var/lib/bright
LOGS=/var/log/bright
CONF=/etc/bright
UNITS=(bright.target bright-speech.service bright-core.service bright-hermes.service bright-ui.service bright-kiosk.service)

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

die() { printf '\n%s\n\n' "$*" >&2; exit 1; }
step() { printf '\033[1;36m==>\033[0m %s\n' "$*"; }

[[ $EUID -eq 0 ]] || die "This has to run as root. Try:  sudo $0 $*"

if [[ -z "$RELEASE" ]]; then
  RELEASE="$PREFIX/releases/$(date +%Y-%m-%d-%H%M%S)"
  step "no release path given, using $RELEASE"
fi

# --- 1. the user the appliance runs as --------------------------------------
# Not root. If a lesson bundle from a USB stick ever contains something it
# should not, the blast radius is one unprivileged account.
step "system user 'bright'"
id -u bright >/dev/null 2>&1 || useradd --system --home "$DATA" --shell /usr/sbin/nologin bright
# The kiosk needs the GPU, the tty and the sound card.
for grp in video render input audio tty; do
  getent group "$grp" >/dev/null 2>&1 && usermod -aG "$grp" bright
done

# --- 2. directories ----------------------------------------------------------
step "directories"
install -d -o bright -g bright -m 0755 "$PREFIX" "$PREFIX/releases" "$DATA" "$LOGS" \
        "$DATA/models" "$DATA/content" "$DATA/kiosk" "$DATA/hermes" "$DATA/hermes/classroom"
install -d -m 0755 "$CONF"

# --- 3. the release ----------------------------------------------------------
if [[ ! -d "$RELEASE" ]]; then
  step "copying this checkout to $RELEASE"
  install -d -o bright -g bright "$RELEASE"
  # --delete is deliberately absent: never destroy a directory this script did
  # not create.
  rsync -a --exclude .git --exclude node_modules --exclude .logs \
        --exclude models --exclude '__pycache__' "$REPO/" "$RELEASE/"
  chown -R bright:bright "$RELEASE"
fi
ln -sfn "$RELEASE" "$PREFIX/.current.new"
mv -T "$PREFIX/.current.new" "$PREFIX/current"
step "current -> $(readlink -f $PREFIX/current)"

# --- 4. python environment ---------------------------------------------------
# Kept OUTSIDE the release directory and at a stable path, so flipping to a new
# release does not invalidate the units' ExecStart lines.
if [[ ! -x "$PREFIX/venv/bin/python3" ]]; then
  step "python environment"
  python3 -m venv "$PREFIX/venv" || die "python3-venv is not installed.
  What to do:  sudo apt-get install -y python3-venv"
  chown -R bright:bright "$PREFIX/venv"
fi
step "installing python dependencies (offline if wheels/ is present)"
if [[ -d "$RELEASE/wheels" ]]; then
  "$PREFIX/venv/bin/pip" install --no-index --find-links "$RELEASE/wheels" \
      -r "$RELEASE/services/speech/requirements.txt" >/dev/null \
    || die "Could not install the offline Python packages from the USB stick.
  What to do: the USB bundle is incomplete. Ask for a new one."
else
  printf '    no wheels/ directory — skipping (run with internet, or build a USB bundle)\n'
fi

# Hermes is optional: Core still teaches the authored lesson without it. If a
# release contains the pinned wheel set, install it into an isolated venv so
# its fast-moving dependency graph cannot disturb speech/core.
if compgen -G "$RELEASE/wheels/hermes_agent-0.20.0-*.whl" >/dev/null 2>&1; then
  if [[ ! -x "$PREFIX/hermes-venv/bin/python3" ]]; then
    step "Hermes python environment"
    python3 -m venv "$PREFIX/hermes-venv" || die "python3-venv is not installed."
  fi
  step "installing pinned Hermes runtime"
  "$PREFIX/hermes-venv/bin/pip" install --no-index --find-links "$RELEASE/wheels" \
      -r "$RELEASE/infra/hermes/requirements.txt" >/dev/null \
    || die "Could not install the pinned Hermes packages from wheels/."
  chown -R bright:bright "$PREFIX/hermes-venv"
else
  printf '    no Hermes 0.20.0 wheel — agent runtime remains optional/offline\n'
fi

# Profile policy is release-owned, but never overwrite a field-edited profile.
if [[ ! -f "$DATA/hermes/classroom/config.yaml" ]]; then
  install -m 0640 -o bright -g bright "$RELEASE/infra/hermes/config.yaml" \
      "$DATA/hermes/classroom/config.yaml"
fi
if [[ ! -f "$DATA/hermes/classroom/SOUL.md" ]]; then
  install -m 0640 -o bright -g bright "$RELEASE/infra/hermes/SOUL.md" \
      "$DATA/hermes/classroom/SOUL.md"
fi

# --- 5. configuration --------------------------------------------------------
if [[ -f "$CONF/bright.env" ]]; then
  step "keeping existing $CONF/bright.env"
else
  step "creating $CONF/bright.env"
  install -m 0640 -o root -g bright "$HERE/bright.env.example" "$CONF/bright.env"
fi

# --- 6. units ----------------------------------------------------------------
step "systemd units"
for unit in "${UNITS[@]}"; do
  install -m 0644 "$HERE/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable bright.target "${UNITS[@]:1}" >/dev/null 2>&1

# --- 7. boot experience ------------------------------------------------------
# A teacher must never see a login prompt or a wall of kernel messages. These
# are suggestions, not enforced, because they depend on the base image.
cat <<'EOF'

Installed.

  Start it now:      systemctl start bright.target
  Check it:          /opt/bright/current/scripts/doctor.sh
  Watch it boot:     journalctl -f -u 'bright-*'

Two things to do on the appliance image itself, once:

  1. Hide the boot text from the classroom. In /etc/default/grub add
       GRUB_CMDLINE_LINUX_DEFAULT="quiet splash loglevel=0 vt.global_cursor_default=0"
     then run  update-grub

  2. Make power loss safe. This box will be unplugged mid-lesson, often.
     Mount the data partition with  data=ordered  (ext4 default) and do NOT
     enable write caching on a disk without power-loss protection.

EOF
