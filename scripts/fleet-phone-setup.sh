#!/usr/bin/env bash
# Install the polite host-job lane on a phone's Linux guest (Omalauncher PRoot,
# Arch Linux ARM). Run on groot:
#
#   scripts/fleet-phone-setup.sh root@100.104.42.85 [--port 22] [--model SM-S938U] [--defer-adb]
#
# Writes guest fleet APIs and an executor service in an existing runsv tree.
# It never restarts Tern, Tailscale, sshd or the legacy supervisor, or changes
# Android apps/settings. Self-ADB is optional and never gates phone jobs.
# Idempotent: re-running rewrites the same files.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET=${1:?usage: fleet-phone-setup.sh root@<tailnet-ip> [--port N] [--model MODEL]}; shift
PORT=22; MODEL=""; DEFER_ADB=0
while [ $# -gt 0 ]; do
  case $1 in --port) PORT=$2; shift 2 ;; --model) MODEL=$2; shift 2 ;; --defer-adb) DEFER_ADB=1; shift ;; *) echo "unknown $1" >&2; exit 2 ;; esac
done
SSH=(ssh -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=10 -p "$PORT" "$TARGET")

echo "==> checking $TARGET is an Android Linux guest"
"${SSH[@]}" 'case "$(uname -r)" in *android*) ;; *) echo "not an Android kernel" >&2; exit 1;; esac
  command -v python3 >/dev/null || { echo "python3 missing: pacman -S python" >&2; exit 1; }
  for t in setsid timeout tar flock setpriv; do command -v $t >/dev/null || { echo "$t missing" >&2; exit 1; }; done'

# Pick the adb device that is this phone (the guest reaches its own Android over
# wireless debugging). With --model, refuse anything else.
serial=$("${SSH[@]}" "set -e
  for s in \$(adb devices | awk 'NR>1 && \$2==\"device\"{print \$1}'); do
    m=\$(timeout 10 adb -s \$s shell getprop ro.product.model | tr -d '\r')
    if [ -z '$MODEL' ] || [ \"\$m\" = '$MODEL' ]; then echo \"\$s \$m\"; exit 0; fi
  done; exit 1") || {
  serial=""
  echo "self-ADB unavailable; fleet jobs remain available" >&2
}
echo "==> adb device: $serial"

tar -C "$REPO" -cf - scripts/fleet-polite-run scripts/fleet-node-probe scripts/fleet_phone.py scripts/fleet-phone-worker scripts/fleet-phone-supervisor scripts/fleet-phone-supervise config/fleet/phone/sv/fleet-worker/run config/fleet/phone/sv/tern-hosts/run scripts/tern-hosts-sync config/tern/hosts.names config/fleet/phone/sv/finish config/fleet/phone/sv/log-run config/fleet/phone/services.example.json | "${SSH[@]}" "set -e
  umask 022
  install -d ~/.local/lib/fleet ~/.config/fleet ~/fleet-jobs
  tmp=\$(mktemp -d); tar -xf - -C \$tmp
  install -m 0755 \$tmp/scripts/fleet-polite-run ~/.local/lib/fleet/polite-run
  install -m 0755 \$tmp/scripts/fleet-node-probe ~/.local/lib/fleet/fleet-node-probe
  install -m 0644 \$tmp/scripts/fleet_phone.py ~/.local/lib/fleet/fleet_phone.py
  install -m 0755 \$tmp/scripts/fleet-phone-worker ~/.local/lib/fleet/fleet-phone-worker
  install -m 0755 \$tmp/scripts/fleet-phone-supervisor ~/.local/lib/fleet/fleet-phone-supervisor
  install -d /opt/dotfiles-k3s/scripts
  install -m 0644 \$tmp/scripts/fleet_phone.py /opt/dotfiles-k3s/scripts/fleet_phone.py
  install -m 0755 \$tmp/scripts/fleet-phone-supervisor /opt/dotfiles-k3s/scripts/fleet-phone-supervisor
  install -m 0644 \$tmp/config/fleet/phone/services.example.json ~/.config/fleet/phone-services.example.json
  if [ -x ~/.local/bin/fleet-phone-supervise ]; then
    sv=\$HOME/.local/share/fleet/sv/fleet-worker
    install -d -m 0700 \$sv/log
    install -m 0755 \$tmp/config/fleet/phone/sv/fleet-worker/run \$sv/run
    install -m 0755 \$tmp/config/fleet/phone/sv/finish \$sv/finish
    install -m 0755 \$tmp/config/fleet/phone/sv/log-run \$sv/log/run
    th=\$HOME/.local/share/fleet/sv/tern-hosts
    install -d -m 0700 \$th/log ~/.config/tern
    install -m 0755 \$tmp/config/fleet/phone/sv/tern-hosts/run \$th/run
    install -m 0755 \$tmp/config/fleet/phone/sv/finish \$th/finish
    install -m 0755 \$tmp/config/fleet/phone/sv/log-run \$th/log/run
    install -m 0755 \$tmp/scripts/tern-hosts-sync ~/.local/bin/tern-hosts-sync
    install -m 0644 \$tmp/config/tern/hosts.names ~/.config/tern/hosts.names
    install -m 0755 \$tmp/scripts/fleet-phone-supervise ~/.local/bin/fleet-phone-supervise.new
    mv -f ~/.local/bin/fleet-phone-supervise.new ~/.local/bin/fleet-phone-supervise
    echo 'executor service installed: existing tree is untouched; enrolls at next supervisor start'
  fi
  rm -rf \$tmp
  if [ -n '${serial%% *}' ]; then printf '%s\n' '${serial%% *}' > ~/.config/fleet/adb-serial; fi"
echo "==> API installed (not started); launcher owns supervisor lifecycle and opt-in"
echo "==> installed; gate now:"
"${SSH[@]}" '~/.local/lib/fleet/polite-run --gate-only' || echo "(gate closed right now; jobs will wait)"
