#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in ''|--activate) ;; *) echo "Usage: $0 [--activate]" >&2; exit 2 ;; esac
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
sha=$(git -C "$repo" rev-parse HEAD)
dest="$HOME/.local/lib/z0-state-packet-units/$sha"
backup="$HOME/.local/state/z0int/startup-packet-unit-backups/$(date -u +%Y%m%dT%H%M%S%NZ)"
mkdir -p "$dest" "$HOME/.config/systemd/user" "$backup"
for unit in z0-state-packet.service z0-state-packet.timer; do
  git -C "$repo" show "$sha:config/systemd/user/$unit" > "$dest/$unit"
  live="$HOME/.config/systemd/user/$unit"
  if [[ -e "$live" || -L "$live" ]]; then cp -a "$live" "$backup/$unit"; fi
  ln -sfn "$dest/$unit" "$live"
done
printf 'Installed units from %s at %s; backups %s\n' "$sha" "$dest" "$backup"
if [[ "${1:-}" == --activate ]]; then
  systemctl --user daemon-reload
  systemctl --user start z0-state-packet.service
  systemctl --user enable --now z0-state-packet.timer
fi
