#!/usr/bin/env bash
set -euo pipefail

image=${1:-}
[[ -f $image ]] || exit 0

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
cache_dir=${XDG_CACHE_HOME:-$HOME/.cache}/noctalia
state_file=$cache_dir/pywal-wallpaper
mkdir -p "$cache_dir"

exec 9>"$cache_dir/pywal-wallpaper.lock"
flock 9

if [[ -r $state_file ]] && [[ $(<"$state_file") == "$image" ]] && [[ -r $HOME/.cache/wal/colors.sh ]]; then
  exit 0
fi

"$root/scripts/apply-pywal-theme.sh" "$image"
printf '%s\n' "$image" > "$state_file.tmp"
mv -f "$state_file.tmp" "$state_file"
