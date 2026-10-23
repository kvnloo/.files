#!/usr/bin/env bash
# Install the polite host-job lane on a phone's Linux guest (Omalauncher PRoot,
# Arch Linux ARM). Run on groot:
#
#   scripts/fleet-phone-setup.sh root@100.104.42.85 [--port 22] [--model SM-S938U]
#
# It only writes files under the guest's ~/.local/lib/fleet, ~/.config/fleet and
# ~/fleet-jobs. It never touches Tern, Tailscale, sshd, Android apps or settings;
# its adb calls are read-only (`getprop`, `dumpsys battery|thermalservice`).
# Idempotent: re-running rewrites the same files.
set -euo pipefail
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET=${1:?usage: fleet-phone-setup.sh root@<tailnet-ip> [--port N] [--model MODEL]}; shift
PORT=22; MODEL=""
while [ $# -gt 0 ]; do
  case $1 in --port) PORT=$2; shift 2 ;; --model) MODEL=$2; shift 2 ;; *) echo "unknown $1" >&2; exit 2 ;; esac
done
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -p "$PORT" "$TARGET")

echo "==> checking $TARGET is an Android Linux guest"
"${SSH[@]}" 'case "$(uname -r)" in *android*) ;; *) echo "not an Android kernel" >&2; exit 1;; esac
  command -v adb >/dev/null || { echo "adb missing in the guest: pacman -S android-tools" >&2; exit 1; }
  command -v python3 >/dev/null || { echo "python3 missing: pacman -S python" >&2; exit 1; }
  for t in nice ionice taskset setsid timeout tar flock; do command -v $t >/dev/null || { echo "$t missing" >&2; exit 1; }; done'

# Pick the adb device that is this phone (the guest reaches its own Android over
# wireless debugging). With --model, refuse anything else.
serial=$("${SSH[@]}" "set -e
  for s in \$(adb devices | awk 'NR>1 && \$2==\"device\"{print \$1}'); do
    m=\$(timeout 10 adb -s \$s shell getprop ro.product.model | tr -d '\r')
    if [ -z '$MODEL' ] || [ \"\$m\" = '$MODEL' ]; then echo \"\$s \$m\"; exit 0; fi
  done; exit 1") || { echo "no matching adb device: enable Wireless debugging and pair the guest's adb with this phone (docs/fleet/README.md)" >&2; exit 1; }
echo "==> adb device: $serial"

tar -C "$REPO/scripts" -cf - fleet-polite-run fleet-node-probe | "${SSH[@]}" "set -e
  umask 022
  install -d ~/.local/lib/fleet ~/.config/fleet ~/fleet-jobs
  tmp=\$(mktemp -d); tar -xf - -C \$tmp
  install -m 0755 \$tmp/fleet-polite-run ~/.local/lib/fleet/polite-run
  install -m 0755 \$tmp/fleet-node-probe ~/.local/lib/fleet/fleet-node-probe
  rm -rf \$tmp
  echo '${serial%% *}' > ~/.config/fleet/adb-serial"
echo "==> installed; gate now:"
"${SSH[@]}" '~/.local/lib/fleet/polite-run --gate-only' || echo "(gate closed right now; jobs will wait)"
