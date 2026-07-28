#!/usr/bin/env bash
# Keep Noctalia, Hyprland, and animated wallpapers on one performance-mode state.
set -u

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
RUNTIME_DIR=${XDG_RUNTIME_DIR:-/tmp}/unified-performance-mode-$UID
ACTIVE_FILE=$RUNTIME_DIR/active
HYPR_FILE=$RUNTIME_DIR/hypr-options
WALLPAPER_FILE=$RUNTIME_DIR/wallpaper-state
WALLPAPER_CHANGED=$RUNTIME_DIR/wallpaper-changed
LOCK_FILE=$RUNTIME_DIR/lock
WALLPAPER_MODE=$ROOT/scripts/wallpaper-mode.sh
mkdir -p "$RUNTIME_DIR"
chmod 700 "$RUNTIME_DIR"

resolve_hyprland() {
  hyprctl -j monitors >/dev/null 2>&1 && return 0
  command -v jq >/dev/null 2>&1 || return 1
  local signature wayland_display
  while IFS=$'\t' read -r signature wayland_display; do
    if HYPRLAND_INSTANCE_SIGNATURE=$signature hyprctl -j monitors >/dev/null 2>&1; then
      export HYPRLAND_INSTANCE_SIGNATURE=$signature
      export WAYLAND_DISPLAY=$wayland_display
      return 0
    fi
  done < <(hyprctl -j instances 2>/dev/null | jq -r '.[] | [.instance, .wl_socket] | @tsv')
  return 1
}

hypr_value() {
  hyprctl getoption "$1" -j 2>/dev/null | jq -r '.int // empty'
}

save_hypr_options() {
  : > "$HYPR_FILE"
  resolve_hyprland || return 0
  local option value
  for option in animations:enabled decoration:blur:enabled decoration:shadow:enabled; do
    value=$(hypr_value "$option")
    [[ $value == 0 || $value == 1 ]] && printf '%s\t%s\n' "$option" "$value" >> "$HYPR_FILE"
  done
}

set_hypr_performance() {
  resolve_hyprland || return 0
  hyprctl keyword animations:enabled false >/dev/null 2>&1 || true
  hyprctl keyword decoration:blur:enabled false >/dev/null 2>&1 || true
  hyprctl keyword decoration:shadow:enabled false >/dev/null 2>&1 || true
}
set_agent_pressure_limits() {
  command -v systemctl >/dev/null 2>&1 || return 0
  systemctl --user set-property --runtime agent.slice \
    CPUWeight=50 IOWeight=25 MemoryHigh=8G MemorySwapMax=16G >/dev/null 2>&1 || true
}

restore_agent_pressure_limits() {
  command -v systemctl >/dev/null 2>&1 || return 0
  systemctl --user set-property --runtime agent.slice \
    CPUWeight=80 IOWeight=50 MemoryHigh=10G MemorySwapMax=24G >/dev/null 2>&1 || true
}


restore_hypr_options() {
  [[ -r $HYPR_FILE ]] || return 0
  resolve_hyprland || return 0
  local option value
  while IFS=$'\t' read -r option value; do
    [[ -n $option && ($value == 0 || $value == 1) ]] || continue
    hyprctl keyword "$option" "$value" >/dev/null 2>&1 || true
  done < "$HYPR_FILE"
}

reduce_wallpaper_load() {
  [[ -x $WALLPAPER_MODE ]] || return 0
  local mode
  mode=$($WALLPAPER_MODE status 2>/dev/null || true)
  printf '%s\n' "$mode" > "$WALLPAPER_FILE"
  case "$mode" in
    chill|aesthetic)
      WALLPAPER_MODE_SILENT=1 "$WALLPAPER_MODE" performance >/dev/null 2>&1 || return 0
      : > "$WALLPAPER_CHANGED"
      ;;
  esac
}

restore_wallpaper_load() {
  [[ -e $WALLPAPER_CHANGED && -r $WALLPAPER_FILE && -x $WALLPAPER_MODE ]] || return 0
  local wallpaper_state=$HOME/.cache/wallpaper-mode/state
  mkdir -p "${wallpaper_state%/*}"
  cat "$WALLPAPER_FILE" > "$wallpaper_state"
  WALLPAPER_MODE_SILENT=1 "$WALLPAPER_MODE" restore >/dev/null 2>&1 || true
}

sync_on() {
  local origin=${1:-manual}
  [[ -e $ACTIVE_FILE ]] && return 0
  save_hypr_options
  reduce_wallpaper_load
  set_hypr_performance
  set_agent_pressure_limits
  printf '%s\n' "$origin" > "$ACTIVE_FILE"
}

sync_off() {
  local requested_origin=${1:-manual}
  [[ -e $ACTIVE_FILE ]] || return 0
  local active_origin
  active_origin=$(cat "$ACTIVE_FILE" 2>/dev/null || printf manual)
  [[ $requested_origin != auto || $active_origin == auto ]] || return 0
  restore_agent_pressure_limits
  restore_hypr_options
  restore_wallpaper_load
  rm -f "$ACTIVE_FILE" "$HYPR_FILE" "$WALLPAPER_FILE" "$WALLPAPER_CHANGED"
}

noctalia() {
  command -v qs >/dev/null 2>&1 || return 0
  qs -c noctalia-shell ipc --any-display call powerProfile "$1" >/dev/null 2>&1 || true
}

with_lock() {
  local action=$1 origin=${2:-manual}
  (
    flock -x 9
    "$action" "$origin"
  ) 9>"$LOCK_FILE"
}

case "${1:-status}" in
  enable)
    origin=${2:-manual}
    with_lock sync_on "$origin"
    noctalia enableNoctaliaPerformance
    ;;
  disable)
    origin=${2:-manual}
    with_lock sync_off "$origin"
    [[ ! -e $ACTIVE_FILE ]] && noctalia disableNoctaliaPerformance
    ;;
  hook-enable)
    with_lock sync_on "${2:-manual}"
    ;;
  hook-disable)
    with_lock sync_off manual
    ;;
  toggle)
    if [[ -e $ACTIVE_FILE ]]; then
      "$0" disable manual
    else
      "$0" enable manual
    fi
    ;;
  status)
    if [[ -e $ACTIVE_FILE ]]; then
      printf 'enabled origin=%s\n' "$(cat "$ACTIVE_FILE")"
    else
      printf 'disabled\n'
    fi
    ;;
  *)
    printf 'usage: %s {enable [auto|manual]|disable [auto|manual]|toggle|status|hook-enable|hook-disable}\n' "$0" >&2
    exit 2
    ;;
esac
