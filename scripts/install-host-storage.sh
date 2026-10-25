#!/usr/bin/env bash
set -euo pipefail
[[ ${1:-} == --activate && $# == 3 ]] || { echo 'Usage: install-host-storage.sh --activate AUTOTIER_REPO AUTOTIER_SHA' >&2; exit 2; }
[[ $(hostname) == groot && $(id -un) == kvn && -d /mnt/zer0models/releases ]] || { echo 'host/release-root mismatch' >&2; exit 1; }
mountpoint -q /mnt/zer0models || { echo 'bulk disk is not mounted' >&2; exit 1; }
repo=$(dirname "$(dirname "$(readlink -f "$0")")")
sha=$(git -C "$repo" rev-parse HEAD)
source_repo=$2
source_sha=$(git -C "$source_repo" rev-parse "$3^{commit}")
exec 9>/tmp/files-live-deploy.lock
flock 9
stage() {
  local name=$1 tree=$2 revision=$3 dest="/mnt/zer0models/releases/$1/$3"
  if [[ ! -e $dest ]]; then
    mkdir -p "$dest"
    git -C "$tree" archive "$revision" | tar -xf - -C "$dest"
    printf '{"name":"%s","source_sha":"%s","source_repo":"%s"}\n' "$name" "$revision" "$tree" > "$dest/.deployment-stamp.json"
  fi
  mkdir -p "$HOME/.local/lib/$name"
  ln -sfn "$dest" "$HOME/.local/lib/$name/$revision"
  ln -sfn "$dest" "$HOME/.local/lib/$name/current"
}
stage host-storage "$repo" "$sha"
stage zer0-storage-autotier "$source_repo" "$source_sha"
dest="/mnt/zer0models/releases/host-storage/$sha"
backup="$HOME/.local/state/host-storage/unit-backups/$(date -u +%Y%m%dT%H%M%S%NZ)"
mkdir -p "$backup" "$HOME/.config/zer0" "$HOME/.config/systemd/user"
for unit in fleet-source-retention.service fleet-source-retention.timer zer0-storage-autotier.service zer0-storage-autotier.timer; do
  live="$HOME/.config/systemd/user/$unit"
  if [[ -e $live || -L $live ]]; then cp -a "$live" "$backup/$unit"; fi
  ln -sfn "$dest/config/systemd/user/$unit" "$live"
done
ln -sfn "$dest/config/zer0/storage.toml" "$HOME/.config/zer0/storage.toml"
systemctl --user daemon-reload
systemctl --user enable --now fleet-source-retention.timer zer0-storage-autotier.timer
printf 'host-storage=%s autotier=%s backup=%s\n' "$sha" "$source_sha" "$backup"
