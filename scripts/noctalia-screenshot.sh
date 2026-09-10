#!/usr/bin/env bash
set -euo pipefail
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
out="${1:-/tmp/noctalia-screenshot.png}"
geom="${2:-}"
if [[ -n "$geom" ]]; then grim -g "$geom" "$out"; else grim "$out"; fi
printf '%s\n' "$out"
