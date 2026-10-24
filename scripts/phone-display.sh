#!/usr/bin/env bash
# Provider-adaptive control path: hyprlang uses keyword; Lua uses native
# hyprctl eval with hl.monitor and hl.workspace_rule.
set -euo pipefail

output=${PHONE_DISPLAY_OUTPUT:-PHONE}
mode=${PHONE_DISPLAY_MODE:-3120x1440@120}
position=${PHONE_DISPLAY_POSITION:-4920x420}
scale=${PHONE_DISPLAY_SCALE:-1}
workspace=${PHONE_DISPLAY_WORKSPACE:-20}
service=app-dev.lizardbyte.app.Sunshine.service
chrome_profile=${XDG_DATA_HOME:-$HOME/.local/share}/tldraw-phone
HYPRCTL_BIN=${PHONE_DISPLAY_HYPRCTL:-hyprctl}
SYSTEMCTL_BIN=${PHONE_DISPLAY_SYSTEMCTL:-systemctl}

notify() {
  command -v notify-send >/dev/null 2>&1 && notify-send -a 'Phone display' "$@" || true
}

require() {
  command -v "$1" >/dev/null 2>&1 || { printf '%s is required\n' "$1" >&2; exit 1; }
}

validate_scale() {
  [[ $scale =~ ^[0-9]+([.][0-9]+)?$ ]] || { printf 'scale must be numeric\n' >&2; exit 2; }
}

resolve_hyprland() {
  "$HYPRCTL_BIN" -j monitors >/dev/null 2>&1 && return 0
  local signature wayland_display
  while IFS=$'\t' read -r signature wayland_display; do
    if HYPRLAND_INSTANCE_SIGNATURE="$signature" WAYLAND_DISPLAY="$wayland_display" "$HYPRCTL_BIN" -j monitors >/dev/null 2>&1; then
      export HYPRLAND_INSTANCE_SIGNATURE="$signature"
      export WAYLAND_DISPLAY="$wayland_display"
      return 0
    fi
  done < <("$HYPRCTL_BIN" -j instances 2>/dev/null | jq -r '.[] | [.instance, .wl_socket] | @tsv')
  return 1
}

lua_quote() {
  jq -Rrn --arg value "$1" '$value | @json'
}

hypr_uses_lua() {
  "$HYPRCTL_BIN" systeminfo 2>/dev/null | grep -Fq 'configProvider: lua'
}

configure_display() {
  if hypr_uses_lua; then
    local lua_output lua_mode lua_position lua_workspace
    lua_output=$(lua_quote "$output")
    lua_mode=$(lua_quote "$mode")
    lua_position=$(lua_quote "$position")
    lua_workspace=$(lua_quote "$workspace")
    "$HYPRCTL_BIN" -r eval "hl.monitor({output=$lua_output,mode=$lua_mode,position=$lua_position,scale=$scale})" >/dev/null
    "$HYPRCTL_BIN" -r eval "hl.workspace_rule({workspace=$lua_workspace,monitor=$lua_output,default=true})" >/dev/null
    return
  fi
  "$HYPRCTL_BIN" keyword monitor "$output,$mode,$position,$scale" >/dev/null
  "$HYPRCTL_BIN" keyword workspace "$workspace,monitor:$output,default:true" >/dev/null
}

present() {
  resolve_hyprland || return 1
  "$HYPRCTL_BIN" -j monitors all 2>/dev/null | jq -e --arg output "$output" 'any(.[]; .name == $output)' >/dev/null
}

start_display() {
  validate_scale
  require "$HYPRCTL_BIN"
  require jq
  resolve_hyprland || { printf 'no live Hyprland instance found\n' >&2; exit 1; }

  if ! present; then
    if hypr_uses_lua; then
      # Register Lua monitor/workspace rules before the headless output appears.
      configure_display || { printf 'failed to register phone display for Lua provider\n' >&2; exit 1; }
      "$HYPRCTL_BIN" output create headless "$output" >/dev/null
      configure_display \
        || { "$HYPRCTL_BIN" output remove "$output" >/dev/null 2>&1 || true; printf 'failed to refresh phone display for Lua provider\n' >&2; exit 1; }
    else
      "$HYPRCTL_BIN" output create headless "$output" >/dev/null
      configure_display \
        || { "$HYPRCTL_BIN" output remove "$output" >/dev/null 2>&1 || true; printf 'failed to configure phone display for hyprlang provider\n' >&2; exit 1; }
    fi
  elif ! configure_display; then
    printf 'failed to configure existing phone display for active config provider\n' >&2
    exit 1
  fi
  "$SYSTEMCTL_BIN" --user start "$service"
  notify 'S25 Ultra canvas ready' "$mode · workspace $workspace · Sunshine NVENC"
}

stop_display() {
  if present; then
    "$SYSTEMCTL_BIN" --user stop "$service" 2>/dev/null || true
    "$HYPRCTL_BIN" output remove "$output" >/dev/null
    notify 'S25 Ultra canvas stopped'
  fi
}

launch_canvas() {
  local browser
  start_display
  browser=$(command -v google-chrome-stable || command -v chromium || true)
  [[ -n $browser ]] || { printf 'Google Chrome or Chromium is required\n' >&2; exit 1; }
  mkdir -p "$chrome_profile"
  "$HYPRCTL_BIN" dispatch exec "[workspace $workspace silent] $browser --user-data-dir=$chrome_profile --force-device-scale-factor=2 --no-first-run --app=https://www.tldraw.com" >/dev/null
}

show_status() {
  if present; then
    "$HYPRCTL_BIN" -j monitors all | jq --arg output "$output" '.[] | select(.name == $output) | {name,width,height,refreshRate,scale,position:[.x,.y],workspace:.activeWorkspace.name}'
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
