#!/usr/bin/env bash
# Install only after the reviewed packet and LookFirst releases pass acceptance.
set -euo pipefail
root="$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)"
launcher="$HOME/.local/lib/z0-look-first/current/bin/generate-index"
packet="$HOME/.local/lib/z0-state-packet/current/bin/generate-packet"
[[ -x "$launcher" && -x "$packet" ]] || { printf 'Install the reviewed packet and LookFirst releases first.\n' >&2; exit 1; }
source="$root/config/systemd/user/z0-state-packet.service.d/30-look-first.conf"
target="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/z0-state-packet.service.d/30-look-first.conf"
[[ ! -e "$target" && ! -L "$target" ]] || { printf 'Existing refresh hook must be reviewed, not overwritten.\n' >&2; exit 1; }
install -Dm644 "$source" "$target"
systemctl --user daemon-reload
printf 'LookFirst shares z0-state-packet.timer. No service was started.\n'
