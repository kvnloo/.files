#!/usr/bin/env bash
# Keep an Omalauncher phone guest online: install the guest's service supervisor and
# harden Android against killing the app. Run on groot; idempotent:
#
#   scripts/fleet-phone-keepalive.sh root@<guest-tailnet-ip> [--port 8022] [--no-android] [--no-rehost]
#
# Guest side (inside Omalauncher's Arch guest, no systemd):
#   busybox (pacman)                     runit's runsv/svlogd/sv
#   ~/.local/bin/fleet-phone-supervise   one runsv per service, services in the
#   ~/.local/share/fleet/sv/<service>/   foreground: tailscaled, sshd, `tern remote
#                                        serve` restart the moment they exit
#   /usr/local/bin/pulseaudio            starts the supervisor from Omalauncher's own
#                                        long-lived, self-restarting PulseAudio session
#   /etc/profile.d/zz-fleet-autostart.sh login shells start it only if none runs
#   ~/.local/bin/fleet-phone-android-harden
# Services already running unsupervised are adopted, not restarted: their run script
# blocks on the old pid (pidfd) and takes over when it exits. Unless --no-rehost, the
# guest's PulseAudio is restarted once (only while nothing plays) so the supervisor
# moves into that session now instead of at the launcher's next start. The old 60 s
# watcher (fleet-phone-autostart --watch) is stopped and removed.
# Android side, through the guest's own wireless-debugging adb link (skipped
# with --no-android or when the guest has no authorized adb device):
#   fleet-phone-android-harden apply     Doze/standby whitelist, background
#                                        appops, phantom-process killer off;
#   undo file in the guest: ~/.local/state/fleet/android-harden/<model>-<serial>.undo.sh
#   (a copy lands in groot's ~/.local/state/fleet/android-harden/).
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DST=${1:?usage: fleet-phone-keepalive.sh <root@guest-ip> [--port N] [--no-android] [--no-rehost]}
shift
PORT=22; ANDROID=1; REHOST=1
while [ $# -gt 0 ]; do
  case $1 in
    --port) PORT=$2; shift 2 ;;
    --no-android) ANDROID=0; shift ;;
    --no-rehost) REHOST=0; shift ;;
    *) echo "unknown $1" >&2; exit 2 ;;
  esac
done
D=(ssh -o BatchMode=yes -o ConnectTimeout=10 -p "$PORT" "$DST")

"${D[@]}" 'case "$(uname -r)" in *android*) ;; *) echo "target is not an Android guest" >&2; exit 1;; esac'

echo "==> guest supervisor (busybox runit: tailscaled, sshd, tern remote serve)"
"${D[@]}" 'pacman -Q busybox >/dev/null 2>&1 || pacman -S --needed --noconfirm busybox >/dev/null; busybox | head -1'
# The guest half: files arrive as a tar on stdin, the script itself as base64 in the command.
read -r -d '' GUEST <<'GUEST' || true
set -e
tmp=$(mktemp -d); tar -xf - -C "$tmp"
src=$tmp/config/fleet/phone; sv=/root/.local/share/fleet/sv
install -d -m 0700 /root/.local/bin "$sv" /root/.local/state/fleet/supervise
install -m 0755 "$tmp"/scripts/fleet-phone-supervise /root/.local/bin/fleet-phone-supervise
install -m 0755 "$tmp"/scripts/fleet-phone-android-harden /root/.local/bin/fleet-phone-android-harden
install -m 0644 "$src"/sv/lib.sh "$sv"/lib.sh
for s in tailscaled sshd tern-remote; do
    install -d -m 0700 "$sv/$s"
    install -m 0755 "$src/sv/$s/run" "$sv/$s/run"
    install -m 0755 "$src/sv/finish" "$sv/$s/finish"
done
for s in tailscaled sshd; do
    install -d -m 0700 "$sv/$s/log"
    install -m 0755 "$src/sv/log-run" "$sv/$s/log/run"
done
install -m 0755 "$src"/pulseaudio-hook /usr/local/bin/pulseaudio
install -m 0644 "$src"/zz-fleet-autostart.sh /etc/profile.d/zz-fleet-autostart.sh
rm -rf "$tmp"
# Retire the 60 s watcher (exact pid from its pidfile; its services keep running).
old=/root/.local/state/fleet-autostart
w=$(cat "$old/watch.pid" 2>/dev/null || true)
if [ -n "$w" ] && tr '\0' ' ' 2>/dev/null <"/proc/$w/cmdline" | grep -q 'fleet-phone-autostart --watch'; then
    kill "$w" && echo "stopped the 60 s watcher (pid $w)"
fi
rm -f /root/.local/bin/fleet-phone-autostart "$old/watch.pid" "$old/heartbeat"
/root/.local/bin/fleet-phone-supervise up
if [ "$REHOST" = 1 ] && ! /root/.local/bin/fleet-phone-supervise status | grep -q 'audio session'; then
    pa=""
    for d in /proc/[0-9]*; do
        c=""; read -r c 2>/dev/null <"$d/comm" || continue
        [ "$c" = pulseaudio ] && tr '\0' ' ' <"$d/cmdline" | grep -q -- '-F /tmp/pulse.pa' && pa=${d#/proc/}
    done
    playing=$(PULSE_SERVER=unix:/run/user/0/pulse/native pactl list short sink-inputs 2>/dev/null | wc -l)
    if [ -n "$pa" ] && [ "$playing" = 0 ]; then
        kill "$pa"  # Omalauncher restarts PulseAudio in ~1 s, through the hook
        i=0; while [ $i -lt 30 ]; do
            /root/.local/bin/fleet-phone-supervise status | grep -q 'audio session' && break
            sleep 0.5; i=$((i + 1))
        done
    elif [ -n "$pa" ]; then
        echo "audio is playing: the supervisor moves into the audio session at PulseAudio's next start"
    fi
fi
/root/.local/bin/fleet-phone-supervise status
GUEST
tar -C "$REPO" -cf - scripts/fleet-phone-supervise scripts/fleet-phone-android-harden \
    config/fleet/phone/zz-fleet-autostart.sh config/fleet/phone/pulseaudio-hook config/fleet/phone/sv |
  "${D[@]}" "f=\$(mktemp); echo $(base64 -w0 <<<"$GUEST") | base64 -d >\$f; REHOST=$REHOST sh \$f; rc=\$?; rm -f \$f; exit \$rc"

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
