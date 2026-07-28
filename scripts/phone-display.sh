#!/usr/bin/env bash
set -euo pipefail

output=PHONE
mode=3120x1440@120
position=4920x420
scale=1
workspace=20
service=app-dev.lizardbyte.app.Sunshine.service
chrome_profile=${XDG_DATA_HOME:-$HOME/.local/share}/tldraw-phone

notify() {
  command -v notify-send >/dev/null 2>&1 && notify-send -a 'Phone display' "$@" || true
}

require() {
  command -v "$1" >/dev/null 2>&1 || { printf '%s is required\n' "$1" >&2; exit 1; }
}

resolve_hyprland() {
  hyprctl -j monitors >/dev/null 2>&1 && return 0
  local signature wayland_display
  while IFS=$'\t' read -r signature wayland_display; do
    if HYPRLAND_INSTANCE_SIGNATURE="$signature" WAYLAND_DISPLAY="$wayland_display" hyprctl -j monitors >/dev/null 2>&1; then
      export HYPRLAND_INSTANCE_SIGNATURE="$signature"
      export WAYLAND_DISPLAY="$wayland_display"
      return 0
    fi
  done < <(hyprctl -j instances 2>/dev/null | jq -r '.[] | [.instance, .wl_socket] | @tsv')
  return 1
}

present() {
  resolve_hyprland || return 1
  hyprctl -j monitors all 2>/dev/null | jq -e --arg output "$output" 'any(.[]; .name == $output)' >/dev/null
}

start_display() {
  local focused
  require hyprctl
  require jq
  resolve_hyprland || { printf 'no live Hyprland instance found\n' >&2; exit 1; }
  focused=$(hyprctl -j monitors 2>/dev/null | jq -r 'first(.[] | select(.focused) | .name) // ""')
  if ! present; then
    hyprctl output create headless "$output" >/dev/null
  fi
  hyprctl keyword monitor "$output,$mode,$position,$scale" >/dev/null
  hyprctl dispatch focusmonitor "$output" >/dev/null
  hyprctl dispatch workspace "$workspace" >/dev/null
  if [[ -n $focused && $focused != "$output" ]]; then
    hyprctl dispatch focusmonitor "$focused" >/dev/null
  fi
  systemctl --user start "$service"
  notify 'S25 Ultra canvas ready' "$mode · workspace $workspace · Sunshine NVENC"
}

stop_display() {
  if present; then
    systemctl --user stop "$service" 2>/dev/null || true
    hyprctl output remove "$output" >/dev/null
    notify 'S25 Ultra canvas stopped'
  fi
}

launch_canvas() {
  local browser
  start_display
  browser=$(command -v google-chrome-stable || command -v chromium || true)
  [[ -n $browser ]] || { printf 'Google Chrome or Chromium is required\n' >&2; exit 1; }
  mkdir -p "$chrome_profile"
  hyprctl dispatch exec "[workspace $workspace silent] $browser --user-data-dir=$chrome_profile --force-device-scale-factor=2 --no-first-run --app=https://www.tldraw.com" >/dev/null
}

show_status() {
  if present; then
    hyprctl -j monitors all | jq --arg output "$output" '.[] | select(.name == $output) | {name,width,height,refreshRate,scale,position:[.x,.y],workspace:.activeWorkspace.name}'
  else
    printf '{"name":"%s","active":false}\n' "$output"
  fi
}

case ${1:-toggle} in
  start) start_display ;;
  stop) stop_display ;;
  toggle) if present; then stop_display; else start_display; fi ;;
  canvas|tldraw) launch_canvas ;;
  status) show_status ;;
  pair) start_display; xdg-open https://localhost:47990 >/dev/null 2>&1 ;;
  *) printf 'usage: %s {start|stop|toggle|canvas|status|pair}\n' "${0##*/}" >&2; exit 2 ;;
esac
