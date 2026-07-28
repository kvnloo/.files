#!/usr/bin/env bash
# Generate a palette without changing wallpaper, enforce terminal contrast,
# then signal live desktop surfaces to reload their cached colors.
set -euo pipefail

image=${1:?usage: apply-pywal-theme.sh IMAGE}
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

[[ -f $image ]] || { printf 'palette image not found: %s\n' "$image" >&2; exit 1; }
command -v wal >/dev/null 2>&1 || { printf 'pywal (wal) is required\n' >&2; exit 1; }

wal -i "$image" -n -s -t -e -q
"$root/scripts/sync-pywal-theme.py"

if command -v dunstctl >/dev/null 2>&1; then
  dunstctl reload "$HOME/.cache/wal/dunstrc" >/dev/null 2>&1 || true
fi
if command -v hyprctl >/dev/null 2>&1; then
  hyprctl reload config-only >/dev/null 2>&1 || true
fi
if command -v tmux >/dev/null 2>&1 && tmux list-sessions >/dev/null 2>&1; then
  tmux source-file "$HOME/.tmux.conf" >/dev/null 2>&1 || true
fi
pkill -USR2 waybar 2>/dev/null || true
