#!/usr/bin/env bash
# Build the pywal → Hermes liquid-glass theme and publish where Desktop looks.
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
python3 "$root/scripts/build_theme.py"

cache="${XDG_CACHE_HOME:-$HOME/.cache}/wal"
theme_src="$cache/hermes-liquid-glass-theme.json"
dest_dir="$HOME/.hermes/liquid-glass-wal"
mkdir -p "$dest_dir"
cp -f "$theme_src" "$dest_dir/theme.json"
printf '%s\n' "$HOME" >"$dest_dir/home"
date +%s >"$cache/hermes-liquid-glass.stamp"

printf 'hermes-liquid-glass: %s\n' "$dest_dir/theme.json" >&2
