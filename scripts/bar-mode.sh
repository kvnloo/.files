#!/usr/bin/env bash
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

CACHE_DIR="$HOME/.cache/desktop-shell"
STATE_FILE="$CACHE_DIR/bar-mode"
mkdir -p "$CACHE_DIR"

notify() {
  command -v notify-send >/dev/null 2>&1 &&
    notify-send -a desktop-shell -h string:x-dunst-stack-tag:bar-mode "Desktop bar" "$1"
}

stop_waybar() {
  systemctl --user stop waybar-session.service 2>/dev/null || true
  pkill -x waybar 2>/dev/null || true
}

stop_noctalia() {
  systemctl --user stop noctalia-shell.service 2>/dev/null || true
  if command -v qs >/dev/null 2>&1; then
    qs -c noctalia-shell kill >/dev/null 2>&1 || true
  fi
  pkill -x noctalia 2>/dev/null || true
  pkill -x quickshell 2>/dev/null || true
  pkill -x qs 2>/dev/null || true
}

start_waybar() {
  stop_noctalia
  stop_waybar
  systemd-run --user --unit=waybar-session --collect waybar >/dev/null
  printf 'waybar\n' > "$STATE_FILE"
  notify "Waybar"
}

start_noctalia() {
  local -a command=()
  if command -v noctalia >/dev/null 2>&1; then
    command=(noctalia)
  elif command -v qs >/dev/null 2>&1; then
    command=(qs -c noctalia-shell)
  else
    notify "Noctalia is not installed · sudo pacman -S noctalia-shell"
    return 1
  fi

  stop_waybar
  stop_noctalia
  "$ROOT/scripts/install-noctalia-audio-overlay.py" >/dev/null
  systemd-run --user --unit=noctalia-shell --collect "${command[@]}" >/dev/null
  printf 'noctalia\n' > "$STATE_FILE"
}

current_mode() {
  if pgrep -x waybar >/dev/null 2>&1; then
    printf 'waybar\n'
  elif pgrep -x noctalia >/dev/null 2>&1 || pgrep -x quickshell >/dev/null 2>&1 || pgrep -x qs >/dev/null 2>&1; then
    printf 'noctalia\n'
  else
    cat "$STATE_FILE" 2>/dev/null || printf 'waybar\n'
  fi
}

case "${1:-status}" in
  waybar)   start_waybar ;;
  noctalia) start_noctalia ;;
  toggle)
    if [[ $(current_mode) == waybar ]]; then
      start_noctalia
    else
      start_waybar
    fi
    ;;
  restore)
    if [[ $(cat "$STATE_FILE" 2>/dev/null || printf 'waybar') == noctalia ]]; then
      start_noctalia || start_waybar
    else
      start_waybar
    fi
    ;;
  status) current_mode ;;
  *) echo "usage: $(basename "$0") {waybar|noctalia|toggle|restore|status}" >&2; exit 1 ;;
esac
