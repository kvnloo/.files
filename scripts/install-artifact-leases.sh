#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in --activate) ;; *) echo 'Usage: install-artifact-leases.sh --activate (parent deployment permission required)' >&2; exit 2;; esac
[[ $(hostname) == groot && $(id -un) == kvn ]] || { echo 'controller identity mismatch' >&2; exit 1; }
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
sha=$(git -C "$repo" rev-parse HEAD)
base="$HOME/.local/lib/artifact-leases"
mkdir -p "$base" "$HOME/.local/state/artifact-leases" "$HOME/.config/systemd/user"
exec 9>"$HOME/.local/state/artifact-leases/deploy.lock"
flock -n 9 || { echo 'another artifact deployment owns lock' >&2; exit 1; }
dest="/mnt/zer0models/releases/artifact-leases/$sha"
mkdir -p "$dest/scripts" "$dest/config/fleet" "$dest/config/systemd/user"
for file in scripts/artifact-leases.py scripts/worktree-reaper.py scripts/artifact-lease-controller.py config/fleet/artifact-leases.json config/systemd/user/artifact-leases.service config/systemd/user/artifact-leases.timer; do
  git -C "$repo" show "$sha:$file" > "$dest/$file"
done
chmod 755 "$dest/scripts/"*.py
printf '%s\n' "$sha" > "$dest/DEPLOYED_SHA"
if [[ -e "$base/$sha" && ! -L "$base/$sha" ]]; then
  echo "refusing to replace existing artifact release $base/$sha" >&2
  exit 1
fi
ln -sfn "$dest" "$base/$sha"
backup="$HOME/.local/state/artifact-leases/unit-backups/$(date -u +%Y%m%dT%H%M%S%NZ)"
mkdir -p "$backup"
for unit in artifact-leases.service artifact-leases.timer; do
  live="$HOME/.config/systemd/user/$unit"
  if [[ -e "$live" || -L "$live" ]]; then cp -a "$live" "$backup/$unit"; fi
  ln -sfn "$dest/config/systemd/user/$unit" "$live"
done
ln -sfn "$dest" "$base/current"
systemctl --user daemon-reload
systemctl --user enable --now artifact-leases.timer
printf 'Activated artifact-leases.timer source=%s backups=%s\n' "$sha" "$backup"
