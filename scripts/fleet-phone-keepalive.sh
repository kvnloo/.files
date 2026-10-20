#!/usr/bin/env bash
# Keep an Omalauncher phone guest online: install the guest-side watcher and
# harden Android against killing the app. Run on groot; idempotent:
#
#   scripts/fleet-phone-keepalive.sh root@<guest-tailnet-ip> [--port 8022] [--no-android]
#
# Guest side (inside Omalauncher's Arch guest, no systemd):
#   ~/.local/bin/fleet-phone-autostart   flock'd watcher: every 60 s restarts
#                                        tailscaled, sshd, `tern remote serve`
#   /etc/profile.d/zz-fleet-autostart.sh every login shell starts the watcher
#   ~/.local/bin/fleet-phone-android-harden
# Android side, through the guest's own wireless-debugging adb link (skipped
# with --no-android or when the guest has no authorized adb device):
#   fleet-phone-android-harden apply     Doze/standby whitelist, background
#                                        appops, phantom-process killer off;
#   undo file in the guest: ~/.local/state/fleet/android-harden/<model>-<serial>.undo.sh
#   (a copy lands in groot's ~/.local/state/fleet/android-harden/).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST=${1:?usage: fleet-phone-keepalive.sh <root@guest-ip> [--port N] [--no-android]}
shift
PORT=22; ANDROID=1
while [ $# -gt 0 ]; do
  case $1 in --port) PORT=$2; shift 2 ;; --no-android) ANDROID=0; shift ;; *) echo "unknown $1" >&2; exit 2 ;; esac
done
D=(ssh -o BatchMode=yes -o ConnectTimeout=10 -p "$PORT" "$DST")

"${D[@]}" 'case "$(uname -r)" in *android*) ;; *) echo "target is not an Android guest" >&2; exit 1;; esac'

echo "==> guest watcher (tailscaled, sshd, tern remote serve)"
tar -C "$REPO" -cf - scripts/fleet-phone-autostart scripts/fleet-phone-android-harden \
    config/fleet/phone/zz-fleet-autostart.sh |
  "${D[@]}" 'set -e; tmp=$(mktemp -d); tar -xf - -C "$tmp"; install -d -m 0700 /root/.local/bin
    install -m 0755 "$tmp"/scripts/fleet-phone-autostart /root/.local/bin/fleet-phone-autostart
    install -m 0755 "$tmp"/scripts/fleet-phone-android-harden /root/.local/bin/fleet-phone-android-harden
    install -m 0644 "$tmp"/config/fleet/phone/zz-fleet-autostart.sh /etc/profile.d/zz-fleet-autostart.sh
    rm -rf "$tmp"; /root/.local/bin/fleet-phone-autostart
    # Start the watcher now; later login shells find it alive.
    (setsid -f /root/.local/bin/fleet-phone-autostart --watch >/dev/null 2>&1 </dev/null)
    sleep 1; l=/root/.local/state/fleet-autostart; p=$(cat $l/watch.pid 2>/dev/null)
    if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then echo "watcher pid $p"; else echo "watcher not running" >&2; fi
    tail -3 $l/log 2>/dev/null || true'

[ "$ANDROID" = 1 ] || exit 0
echo "==> Android hardening via the guest's adb"
if ! out=$("${D[@]}" 'S=$(adb devices 2>/dev/null | awk "NR>1 && \$2==\"device\"{print \$1; exit}")
    [ -n "$S" ] || { echo "NO_ADB"; exit 0; }
    /root/.local/bin/fleet-phone-android-harden -s "$S" apply'); then
  echo "$out"; exit 1
fi
if [ "$out" = NO_ADB ]; then
  cat <<'EOF'
   no authorized adb device in the guest; on the phone:
     1. Settings > Developer options > Wireless debugging: on
     2. "Pair device with pairing code"; in the guest: adb pair <ip:pair-port>  (type the code there)
     3. in the guest: adb connect <ip:port shown on the Wireless debugging screen>
   then rerun this script (or run fleet-phone-android-harden -s <ip:port> apply from groot)
EOF
  exit 0
fi
echo "$out"
mkdir -p ~/.local/state/fleet/android-harden
"${D[@]}" 'cd ~/.local/state/fleet/android-harden 2>/dev/null && tar -cf - *.undo.sh 2>/dev/null || true' |
  tar -xf - -C ~/.local/state/fleet/android-harden 2>/dev/null || true
echo "undo copies on groot: $(ls ~/.local/state/fleet/android-harden/*.undo.sh 2>/dev/null | tr '\n' ' ')"
