#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in ''|--activate) ;; *) echo "Usage: $0 [--activate]" >&2; exit 2 ;; esac
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
sha=$(git -C "$repo" rev-parse HEAD)
name=z0int-model-identity-units
base="/mnt/zer0models/releases/$name"
dest="$base/$sha"
mkdir -p "$base" "$HOME/.local/lib/$name" "$HOME/.config/systemd/user"
if [[ ! -e "$dest" ]]; then
  stage=$(mktemp -d "$base/.install-XXXXXXXX")
  trap 'rm -rf "$stage"' EXIT
  git -C "$repo" archive "$sha" | tar -xf - -C "$stage"
  printf '{"name":"%s","source_sha":"%s"}\n' "$name" "$sha" > "$stage/.deployment-stamp.json"
  mv "$stage" "$dest"
  trap - EXIT
fi
ln -sfn "$dest" "$HOME/.local/lib/$name/$sha"
ln -sfn "$dest" "$HOME/.local/lib/$name/current"
for unit in z0int-policy.service z0int-model-identity.service z0int-model-identity.path z0int-model-identity.timer; do
  cmp <(git -C "$repo" show "$sha:config/systemd/user/$unit") "$dest/config/systemd/user/$unit"
  ln -sfn "$dest/config/systemd/user/$unit" "$HOME/.config/systemd/user/$unit"
done
# Preserve existing enablement, but migrate pinned historical targets too.
# Install-only does not enable or start a unit that was not already enabled.
for link in default.target.wants/z0int-model-identity.path timers.target.wants/z0int-model-identity.timer; do
  live="$HOME/.config/systemd/user/$link"
  if [[ -L "$live" ]]; then
    ln -sfn "../${link##*/}" "$live"
  fi
done
printf 'Installed identity units from %s at %s\n' "$sha" "$dest"
if [[ "${1:-}" == --activate ]]; then
  systemctl --user daemon-reload
  systemctl --user start z0int-model-identity.service
  systemctl --user enable --now z0int-model-identity.path z0int-model-identity.timer
fi
