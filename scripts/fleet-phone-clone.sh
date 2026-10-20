#!/usr/bin/env bash
# Copy the S25's Omalauncher guest setup (Tern remote start helpers and the
# key-only sshd policy) onto another phone's guest, install the autostart hook
# that brings tailscaled, sshd and `tern remote serve` back after the launcher
# restarts, then install the polite fleet lane there. Run on groot once the new
# phone's guest answers ssh:
#
#   scripts/fleet-phone-clone.sh root@100.104.42.85 root@<new-guest-tailnet-ip> [--port 8022] [--model SM-S906U1]
#
# --port is the target's ssh port (the source is reached with your ssh defaults).
# Read-only on the source phone. On the target it writes only inside the guest:
# ~/.local/bin/{tern-remote-start,tern-ssh-start,fleet-phone-autostart},
# ~/.local/lib/proot-peercred.so, /etc/ssh/sshd_config.d/50-omalauncher.conf,
# /etc/profile.d/zz-fleet-autostart.sh, plus what fleet-phone-setup.sh writes.
# When the target ships its own Tern (/opt/tern/tern/tern, newer Omalauncher),
# the S25's older Tern and its ~/.local/bin/tern launcher are NOT copied (they
# would shadow the newer Tern); otherwise they are, as on the S25.
# Secrets are not copied: no Tailscale state, no ssh host keys, no Tern state, no
# ~/.config, no hermes/bws credentials. The target keeps its own tailnet identity.
# Idempotent: re-running writes the same files.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC=${1:?usage: fleet-phone-clone.sh <src root@ip> <dst root@ip> [--port N] [--model MODEL]}
DST=${2:?usage: fleet-phone-clone.sh <src root@ip> <dst root@ip> [--port N] [--model MODEL]}
shift 2
PORT=22; MODEL_ARGS=()
while [ $# -gt 0 ]; do
  case $1 in --port) PORT=$2; shift 2 ;; --model) MODEL_ARGS=(--model "$2"); shift 2 ;; *) echo "unknown $1" >&2; exit 2 ;; esac
done
O=(-o BatchMode=yes -o ConnectTimeout=10)
D=(ssh "${O[@]}" -p "$PORT" "$DST")

"${D[@]}" 'case "$(uname -r)" in *android*) ;; *) echo "target is not an Android guest" >&2; exit 1;; esac
  pacman -Q tailscale openssh android-tools python >/dev/null || { echo "target needs: pacman -S --needed tailscale openssh android-tools python" >&2; exit 1; }
  for t in setsid flock; do command -v $t >/dev/null || { echo "$t missing" >&2; exit 1; }; done'

if "${D[@]}" 'test -x /opt/tern/tern/tern'; then
  echo "==> target ships its own Tern (/opt/tern/tern/tern): copying start helpers only"
  files='root/.local/bin/tern-remote-start root/.local/bin/tern-ssh-start
    $(ls -d root/.local/opt/tern-*/tern/proot-peercred.so | tail -1) etc/ssh/sshd_config.d/50-omalauncher.conf'
else
  echo "==> copying Tern launcher + helpers (no state, no keys)"
  files='root/.local/bin/tern root/.local/bin/tern-daemon-start root/.local/bin/tern-remote-start
    root/.local/bin/tern-ssh-start root/.local/bin/tern-tailscale-start root/.local/bin/tern-tailscale-hosts
    $(ls -d root/.local/opt/tern-* | tail -1) etc/ssh/sshd_config.d/50-omalauncher.conf'
fi
ssh "${O[@]}" "$SRC" "cd / && tar -cf - ${files//$'\n'/ }" |
  "${D[@]}" 'set -e; tmp=$(mktemp -d); tar -xf - -C "$tmp"
    shim=$(ls "$tmp"/root/.local/opt/tern-*/tern/proot-peercred.so 2>/dev/null | tail -1)
    if [ ! -x /opt/tern/tern/tern ]; then cp -a "$tmp"/root/.local/opt /root/.local/; fi
    install -d -m 0700 /root/.local/bin /root/.local/lib
    for f in "$tmp"/root/.local/bin/*; do install -m 0711 "$f" /root/.local/bin/; done
    if [ -n "$shim" ]; then install -m 0644 "$shim" /root/.local/lib/proot-peercred.so; fi
    install -m 0644 "$tmp"/etc/ssh/sshd_config.d/50-omalauncher.conf /etc/ssh/sshd_config.d/
    rm -rf "$tmp"; /usr/bin/sshd -t && echo "sshd policy ok"'

echo "==> installing the autostart hook (tailscaled, sshd, tern remote serve)"
tar -C "$REPO" -cf - scripts/fleet-phone-autostart config/fleet/phone/zz-fleet-autostart.sh |
  "${D[@]}" 'set -e; tmp=$(mktemp -d); tar -xf - -C "$tmp"
    install -m 0755 "$tmp"/scripts/fleet-phone-autostart /root/.local/bin/fleet-phone-autostart
    install -m 0644 "$tmp"/config/fleet/phone/zz-fleet-autostart.sh /etc/profile.d/zz-fleet-autostart.sh
    rm -rf "$tmp"; /root/.local/bin/fleet-phone-autostart
    l=/root/.local/state/fleet-autostart/log; if [ -s $l ]; then tail -3 $l; else echo "autostart: all already running"; fi'

echo "==> installing the polite fleet lane"
"$REPO/scripts/fleet-phone-setup.sh" "$DST" --port "$PORT" "${MODEL_ARGS[@]}"
echo "next: add the phone under nodes in config/fleet/nodes.yaml (kind: phone, ssh_port: $PORT),"
echo "      then: scripts/fleet nodes && scripts/fleet health --node <name>"
