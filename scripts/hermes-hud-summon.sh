#!/usr/bin/env bash
# Super+Shift+U. Must not move windows or change workspaces.
echo "Hermes HUD shortcut is not armed. It will not move windows." >&2
exit 0

#
# Super+Shift+U. The warm path sends Ctrl+Shift+H into the already-running
# app and focuses the "Hermes HUD" window. That is the instant path.
# Cold start is not success: `warm` parks a resident desktop on
# special:hermes-hud without taking focus, so the next summon does not pay
# Electron + backend boot.
set -euo pipefail

MODE="${1:-summon}"
LOG_DIR="${XDG_STATE_HOME:-$HOME/.local/state}"
LOG="$LOG_DIR/hermes-hud-summon.log"
mkdir -p "$LOG_DIR"

log() { printf '%s %s\n' "$(date -Is)" "$*" >>"$LOG"; }

export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
export WAYLAND_DISPLAY="${WAYLAND_DISPLAY:-wayland-1}"
export XDG_CURRENT_DESKTOP="${XDG_CURRENT_DESKTOP:-Hyprland}"

if [[ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" || -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
  log "missing Hyprland or dbus session; refusing to launch a GUI"
  exit 1
fi

clients_json() { hyprctl clients -j; }

snapshot() {
  python3 - <<'PY'
import json, subprocess
mon = json.loads(subprocess.check_output(["hyprctl", "monitors", "-j"], text=True))
active = next(m for m in mon if m.get("focused"))
win = json.loads(subprocess.check_output(["hyprctl", "activewindow", "-j"], text=True))
print(json.dumps({
    "workspace": active.get("activeWorkspace", {}).get("name") or active.get("activeWorkspace", {}).get("id"),
    "address": win.get("address") or "",
    "class": win.get("class") or "",
}))
PY
}

hermes_rows() {
  clients_json | python3 -c '
import json, sys
rows = json.load(sys.stdin)
for c in rows:
    if (c.get("class") or "").lower() != "hermes":
        continue
    title = c.get("title") or ""
    kind = "hud" if title == "Hermes HUD" else "main"
    print("\t".join([kind, c.get("address") or "", title, str(c.get("pid") or "")]))
'
}

focus_addr() {
  local addr="$1"
  [[ -n "$addr" ]] || return 0
  hyprctl dispatch focuswindow "address:${addr}" >/dev/null
}

park_main() {
  local addr="$1"
  hyprctl dispatch movetoworkspacesilent "special:hermes-hud,address:${addr}" >/dev/null
}

restore_if_stolen() {
  local before="$1"
  local after
  after="$(snapshot)"
  local b_ws b_addr a_ws a_addr
  b_ws="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["workspace"])' <<<"$before")"
  b_addr="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])' <<<"$before")"
  a_ws="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["workspace"])' <<<"$after")"
  a_addr="$(python3 -c 'import json,sys; print(json.load(sys.stdin)["address"])' <<<"$after")"
  if [[ "$a_ws" != "$b_ws" || ( -n "$b_addr" && "$a_addr" != "$b_addr" ) ]]; then
    log "focus stolen ws=$a_ws addr=$a_addr; restoring ws=$b_ws addr=$b_addr"
    if [[ -n "$b_addr" ]]; then
      focus_addr "$b_addr"
    fi
  fi
}

ensure_warm() {
  if hermes_rows | grep -q $'^main\t'; then
    return 0
  fi
  if systemctl --user is-active --quiet hermes-desktop-warm.service 2>/dev/null; then
    return 0
  fi
  local before
  before="$(snapshot)"
  log "cold start begin focus=$(python3 -c 'import json,sys; print(json.load(sys.stdin))' <<<"$before")"
  local t0
  t0="$(date +%s%3N)"
  systemd-run --user --collect --unit=hermes-desktop-warm.service \
    --setenv="WAYLAND_DISPLAY=$WAYLAND_DISPLAY" \
    --setenv="XDG_RUNTIME_DIR=$XDG_RUNTIME_DIR" \
    --setenv="HYPRLAND_INSTANCE_SIGNATURE=$HYPRLAND_INSTANCE_SIGNATURE" \
    --setenv="DBUS_SESSION_BUS_ADDRESS=$DBUS_SESSION_BUS_ADDRESS" \
    --setenv="XDG_CURRENT_DESKTOP=$XDG_CURRENT_DESKTOP" \
    --working-directory="$HOME" \
    -- hermes desktop --skip-build >>"$LOG" 2>&1 || {
      log "systemd-run failed"
      return 1
    }
  local addr=""
  local i
  for i in $(seq 1 80); do
    addr="$(hermes_rows | awk -F'\t' '$1=="main"{print $2; exit}')"
    if [[ -n "$addr" ]]; then
      park_main "$addr"
      restore_if_stolen "$before"
      local ms=$(( $(date +%s%3N) - t0 ))
      log "warm window parked addr=$addr ms=$ms"
      if (( ms > 1000 )); then
        log "cold start exceeded 1s; shortcut must not depend on this path"
      fi
      return 0
    fi
    sleep 0.25
  done
  log "warm start timed out after 20s"
  restore_if_stolen "$before"
  return 1
}

summon() {
  local t0 hud
  t0="$(date +%s%3N)"
  hud="$(hermes_rows | awk -F'\t' '$1=="hud"{print $2; exit}')"
  if [[ -n "$hud" ]]; then
    local active
    active="$(python3 -c 'import json,sys; print(json.load(sys.stdin).get("address") or "")' <<<"$(hyprctl activewindow -j)")"
    if [[ "$active" == "$hud" ]]; then
      hyprctl dispatch sendshortcut CTRL SHIFT, H, "address:${hud}" >/dev/null
      log "hud dismissed ms=$(( $(date +%s%3N) - t0 ))"
      return 0
    fi
    focus_addr "$hud"
    log "hud focused ms=$(( $(date +%s%3N) - t0 ))"
    return 0
  fi
  ensure_warm || return 1
  local main
  main="$(hermes_rows | awk -F'\t' '$1=="main"{print $2; exit}')"
  if [[ -z "$main" ]]; then
    log "no main Hermes window to receive Ctrl+Shift+H"
    return 1
  fi
  hyprctl dispatch sendshortcut CTRL SHIFT, H, "address:${main}" >/dev/null
  local i
  for i in $(seq 1 20); do
    hud="$(hermes_rows | awk -F'\t' '$1=="hud"{print $2; exit}')"
    if [[ -n "$hud" ]]; then
      focus_addr "$hud"
      log "hud summoned ms=$(( $(date +%s%3N) - t0 ))"
      return 0
    fi
    sleep 0.05
  done
  log "Ctrl+Shift+H did not map Hermes HUD within 1s"
  return 1
}

case "$MODE" in
  warm) ensure_warm ;;
  summon) summon ;;
  *) echo "usage: $0 [summon|warm]" >&2; exit 2 ;;
esac
