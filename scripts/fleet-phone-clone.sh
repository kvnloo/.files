#!/usr/bin/env bash
# Copy the S25's Omalauncher guest setup (Tern launcher, its Tailscale/SSH start
# helpers and the key-only sshd policy) onto another phone's guest, then install
# the polite fleet lane there. Run on groot once the new phone's guest answers ssh:
#
#   scripts/fleet-phone-clone.sh root@100.104.42.85 root@<new-guest-tailnet-ip> [--model SM-S906U1]
#
# Read-only on the source phone. On the target it writes only inside the guest:
# ~/.local/bin/tern*, ~/.local/opt/tern-*, /etc/ssh/sshd_config.d/50-omalauncher.conf.
# Secrets are not copied: no Tailscale state, no ssh host keys, no Tern state, no
# ~/.config, no hermes/bws credentials. The target keeps its own tailnet identity.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SRC=${1:?usage: fleet-phone-clone.sh <src root@ip> <dst root@ip> [--model MODEL]}
DST=${2:?usage: fleet-phone-clone.sh <src root@ip> <dst root@ip> [--model MODEL]}
shift 2
O=(-o BatchMode=yes -o ConnectTimeout=10)

ssh "${O[@]}" "$DST" 'case "$(uname -r)" in *android*) ;; *) echo "target is not an Android guest" >&2; exit 1;; esac
  pacman -Q tailscale openssh android-tools python >/dev/null || { echo "target needs: pacman -S --needed tailscale openssh android-tools python" >&2; exit 1; }'

echo "==> copying Tern launcher + helpers (no state, no keys)"
ssh "${O[@]}" "$SRC" 'cd / && tar -cf - root/.local/bin/tern root/.local/bin/tern-daemon-start root/.local/bin/tern-remote-start \
    root/.local/bin/tern-ssh-start root/.local/bin/tern-tailscale-start root/.local/bin/tern-tailscale-hosts \
    $(ls -d root/.local/opt/tern-* | tail -1) etc/ssh/sshd_config.d/50-omalauncher.conf' |
  ssh "${O[@]}" "$DST" 'cd / && tar -xf - && /usr/bin/sshd -t && echo "sshd policy ok"'

echo "==> installing the polite fleet lane"
"$REPO/scripts/fleet-phone-setup.sh" "$DST" "$@"
echo "next: open Tern once on the phone (it starts tailscaled, sshd and the Tern daemon),"
echo "      add the phone under nodes in config/fleet/nodes.yaml (kind: phone), then: scripts/fleet health"
