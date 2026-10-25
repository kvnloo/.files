#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in ''|--activate) ;; *) echo "Usage: $0 [--activate]" >&2; exit 2 ;; esac
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
sha=$(git -C "$repo" rev-parse HEAD)
dest="$HOME/.local/lib/z0int-model-identity-units/$sha"
mkdir -p "$dest" "$HOME/.config/systemd/user"
for unit in z0int-model-identity.service z0int-model-identity.path z0int-model-identity.timer; do
  if [[ ! -e "$dest/$unit" ]]; then
    git -C "$repo" show "$sha:config/systemd/user/$unit" > "$dest/$unit"
  fi
  ln -sfn "$dest/$unit" "$HOME/.config/systemd/user/$unit"
done
printf 'Installed identity units from %s at %s\n' "$sha" "$dest"
if [[ "${1:-}" == --activate ]]; then
  systemctl --user daemon-reload
  systemctl --user start z0int-model-identity.service
  systemctl --user enable --now z0int-model-identity.path z0int-model-identity.timer
fi
