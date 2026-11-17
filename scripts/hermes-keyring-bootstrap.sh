#!/usr/bin/env bash
# Print `export BWS_ACCESS_TOKEN=...` for bws-env-exec, or nothing if no token is available.
# Installed at ~/.hermes/bin/hermes-keyring-bootstrap.sh.
# Sources:
#   1. TPM2-sealed copy at $HERMES_BWS_CRED (systemd-creds --user): every call, no D-Bus.
#   2. gnome-keyring login collection: only when the sealed copy is missing or unreadable, or
#      its last keyring check is older than $HERMES_KEYRING_REFRESH_S (default 1 h; picks up a
#      rotated token and reseals it), and only by one caller at a time. Each keyring read is a
#      short-lived Secret Service client, and a client that vanishes with a property Get in
#      flight aborts gnome-keyring-daemon (core dumps 2026-11-16 01:23, 2026-11-17 00:19), so
#      this script must not probe the keyring on every call.
#      Only read when unlocked: a locked lookup blocks until a GUI unlock that never comes.
set -euo pipefail
SERVICE="${HERMES_KEYRING_SERVICE:-org.hermes.agent}"
KEY="${HERMES_KEYRING_BWS_KEY:-bws-access-token}"
CRED="${HERMES_BWS_CRED:-$HOME/.config/hermes/bws-access-token.cred}"
REFRESH_S="${HERMES_KEYRING_REFRESH_S:-3600}"
STAMP="$CRED.keyring-checked"
# The keyring lives on the systemd user bus; agent shells on the bot screen inherit a private
# dbus-launch bus (/tmp/dbus-*) with no Secret Service, so pin the real one.
user_bus="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/bus"
[[ -S "$user_bus" ]] && export DBUS_SESSION_BUS_ADDRESS="unix:path=$user_bus"

token=""
locked="not checked"
stale() { [[ ! -e "$STAMP" ]] || (( $(date +%s) - $(stat -c %Y "$STAMP") >= REFRESH_S )); }
sealed() { [[ -r "$CRED" ]] && timeout 15 systemd-creds --user decrypt --name="$KEY" "$CRED" - 2>/dev/null || true; }
from_keyring() {  # one caller at a time; reseal on success
  mkdir -p "$(dirname "$CRED")"; chmod 700 "$(dirname "$CRED")"
  exec 9>>"$STAMP"
  flock -n 9 || { exec 9>&-; return 0; }
  touch "$STAMP"
  locked="$(timeout 5 busctl --user get-property org.freedesktop.secrets \
    /org/freedesktop/secrets/aliases/default org.freedesktop.Secret.Collection Locked 2>/dev/null || echo 'b true')"
  if [[ "$locked" == "b false" ]]; then
    token="$(timeout 10 secret-tool lookup service "$SERVICE" key "$KEY" 2>/dev/null || true)"
    if [[ -n "${token// }" ]]; then
      tmp="$CRED.tmp.$$"
      if printf %s "$token" | timeout 15 systemd-creds --user encrypt --name="$KEY" - "$tmp" 2>/dev/null; then
        chmod 600 "$tmp"; mv -f "$tmp" "$CRED"
      else
        rm -f "$tmp"
      fi
    fi
  fi
  exec 9>&-
}

stale && from_keyring
[[ -z "${token// }" ]] && token="$(sealed)"
[[ -z "${token// }" && "$locked" == "not checked" ]] && from_keyring
if [[ -z "${token// }" ]]; then
  echo "hermes-keyring-bootstrap: no BWS token (keyring locked=${locked#b }, sealed copy ${CRED} $( [[ -r $CRED ]] && echo unreadable || echo missing))" >&2
  exit 0
fi
printf "export BWS_ACCESS_TOKEN='%s'\n" "$token"
unset token
