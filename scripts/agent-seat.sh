#!/usr/bin/env bash
# Switch between Hyprland (daily) and a full Sway session (agent canvas).
# Sway takes every connected output — 1 on MBP, 2 on node 0 — nothing hardcoded.
set -euo pipefail

runtime=${XDG_RUNTIME_DIR:-/tmp}/agent-seat
script_dir=$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)
repo_config=$(cd "$script_dir/../config/sway/agent-seat" && pwd)/config
config=${AGENT_SEAT_CONFIG:-$HOME/.config/sway/agent-seat/config}
vt_helper=/usr/local/bin/agent-seat-vt
hypr_vt_file=$runtime/hyprland.vt
hypr_session_file=$runtime/hyprland.session
sway_vt=${AGENT_SEAT_VT:-3}
envfile=$runtime/env
toggle_log=$runtime/toggle.log
sway_log=$runtime/sway.log

notify() {
  command -v notify-send >/dev/null 2>&1 && notify-send -a 'agent-seat' "$@" || true
}

require() {
  command -v "$1" >/dev/null 2>&1 || { printf 'missing %s\n' "$1" >&2; exit 1; }
}

resolve_config() {
  [[ -f $config ]] && return 0
  [[ -f $repo_config ]] && { config=$repo_config; return 0; }
  printf 'no agent-seat sway config at %s\n' "$config" >&2
  exit 1
}

on_hyprland() {
  [[ -n ${HYPRLAND_INSTANCE_SIGNATURE:-} ]] && command -v hyprctl >/dev/null && hyprctl -j monitors >/dev/null 2>&1
}

on_sway() {
  [[ -n ${SWAYSOCK:-} ]] && command -v swaymsg >/dev/null && swaymsg -t get_outputs >/dev/null 2>&1
}

sway_pids() {
  pgrep -u "$UID" -x sway || true
}

sway_sock() {
  local sock
  if [[ -f $envfile ]]; then
    # shellcheck disable=SC1090
    sock=$(. "$envfile" >/dev/null; printf '%s' "${SWAYSOCK:-}")
    if [[ -n $sock && -S $sock ]]; then
      printf '%s\n' "$sock"
      return 0
    fi
  fi
  for sock in "$XDG_RUNTIME_DIR"/sway-ipc."$UID".*.sock; do
    if [[ -S $sock ]]; then
      printf '%s\n' "$sock"
      return 0
    fi
  done
  return 1
}

# Nested X11/Wayland backends show up as X11-* / WL-*. Real session is DRM.
sway_is_drm() {
  local sock json
  sock=$(sway_sock) || return 1
  json=$(swaymsg -s "$sock" -t get_outputs 2>/dev/null) || return 1
  command -v jq >/dev/null 2>&1 || return 1
  jq -e '[.[] | .name] | length > 0 and all(test("^(X11-|WL-|HEADLESS|FALLBACK)") | not)' <<<"$json" >/dev/null
}

sway_running() {
  [[ -n $(sway_pids) ]]
}

kill_sway() {
  local pid
  for pid in $(sway_pids); do
    kill "$pid" 2>/dev/null || true
  done
  sleep 0.2
  for pid in $(sway_pids); do
    kill -9 "$pid" 2>/dev/null || true
  done
}

vt_ok() {
  [[ -x $vt_helper ]] && sudo -n -l "$vt_helper" >/dev/null 2>&1
}

current_vt() {
  local n
  n=${XDG_VTNR:-}
  if [[ $n =~ ^[0-9]+$ ]]; then
    printf '%s\n' "$n"
    return
  fi
  cat /sys/class/tty/tty0/active 2>/dev/null | tr -dc '0-9'
  printf '\n'
}

save_hyprland_origin() {
  mkdir -p "$runtime"
  current_vt >"$hypr_vt_file"
  printf '%s\n' "${XDG_SESSION_ID:-}" >"$hypr_session_file"
}

hyprland_vt() {
  if [[ -s $hypr_vt_file ]]; then
    tr -dc '0-9' <"$hypr_vt_file"
    printf '\n'
  else
    printf '1\n'
  fi
}

print_install_hint() {
  cat >&2 <<'EOF'
agent-seat needs an updated VT helper (one-time sudo).

Ctrl+V has a fish snippet. Run it, then Super+Shift+A again.
EOF
}

write_install_script() {
  cat > /tmp/install-agent-seat-vt.fish <<EOF
#!/usr/bin/env fish
sudo install -m 0755 $script_dir/agent-seat-vt /usr/local/bin/agent-seat-vt
sudo install -m 0440 $script_dir/../config/system/sudoers.d/agent-seat /etc/sudoers.d/agent-seat
sudo visudo -cf /etc/sudoers.d/agent-seat
EOF
  chmod +x /tmp/install-agent-seat-vt.fish
  if command -v wl-copy >/dev/null 2>&1; then
    wl-copy < /tmp/install-agent-seat-vt.fish
  fi
}

ensure_helper() {
  if vt_ok; then
    return 0
  fi
  write_install_script
  print_install_hint
  exit 1
}

# Helper is installed but too old (must be the PAM-session starter).
helper_is_current() {
  [[ -x $vt_helper ]] || return 1
  grep -q 'PAMName=login' "$vt_helper" 2>/dev/null || return 1
  grep -q -- '--runtime mask' "$vt_helper" 2>/dev/null
}

remember_sway_env() {
  mkdir -p "$runtime"
  cat >"$envfile" <<EOF
export SWAYSOCK=$(printf '%q' "${SWAYSOCK:-}")
export WAYLAND_DISPLAY=$(printf '%q' "${WAYLAND_DISPLAY:-}")
export XDG_CURRENT_DESKTOP=sway
EOF
}

apply_outputs() {
  require jq
  require swaymsg
  local name width
  while IFS=$'\t' read -r name width; do
    [[ -n $name ]] || continue
    local scale=1
    if [[ ${width:-0} -ge 2560 ]]; then
      scale=2
    fi
    swaymsg output "$name" enable scale "$scale" >/dev/null
  done < <(swaymsg -t get_outputs | jq -r '.[] | select(.name | test("HEADLESS|FALLBACK|X11-|WL-") | not) | [.name, (.current_mode.width // .rect.width // 0)] | @tsv')
}

attach_virtual() {
  command -v swaymsg >/dev/null || return 0
  local id
  while IFS= read -r id; do
    [[ -n $id ]] || continue
    case $id in
      *[Vv]irtual*|*wtype*|*ydotool*|*dotool*) ;;
      *) continue ;;
    esac
    swaymsg "seat seat-agent1 attach $id" >/dev/null || true
  done < <(swaymsg -t get_inputs | jq -r '.[].identifier')
}

on_sway_start() {
  remember_sway_env
  apply_outputs
  attach_virtual
}

# Colon-separated DRM nodes whose connectors are actually connected.
# MBP panel is amdgpu eDP on card1; Intel card0 has no connected outputs.
pick_drm_devices() {
  local conn card name devices=()
  for conn in /sys/class/drm/card[0-9]*-*; do
    [[ -f $conn/status ]] || continue
    [[ $(<"$conn/status") == connected ]] || continue
    name=${conn##*/}
    card=${name%%-*}
    devices+=("/dev/dri/$card")
  done
  if [[ ${#devices[@]} -eq 0 ]]; then
    printf '%s\n' /dev/dri/card0
    return
  fi
  printf '%s\n' "${devices[@]}" | awk 'NF && !seen[$0]++' | paste -sd:
}

persist_dir() {
  printf '%s\n' "${XDG_STATE_HOME:-$HOME/.local/state}/agent-seat"
}

# drm alone paints the panel and skips libinput — keyboard/pointer stay dead.
# Keep DISPLAY/WAYLAND_DISPLAY unset so wlroots does not pick X11/wayland backends.
wlr_session_backends=drm,libinput

# Runs ON the spare VT via agent-seat-vt. Must not inherit Hyprland's DISPLAY.
# Keep XDG_SESSION_ID — the helper starts a *new* PAM session; Sway needs it.
launch_on_vt() {
  export XDG_RUNTIME_DIR=/run/user/$UID
  runtime=$XDG_RUNTIME_DIR/agent-seat
  sway_log=$runtime/sway.log
  local persist
  persist=$(persist_dir)
  mkdir -p "$runtime" "$persist"
  : >"$sway_log"
  exec > >(stdbuf -oL tee -a "$sway_log" "$persist/sway.log") 2>&1
  resolve_config
  unset DISPLAY WAYLAND_DISPLAY WAYLAND_SOCKET SWAYSOCK I3SOCK
  unset HYPRLAND_INSTANCE_SIGNATURE HYPRLAND_CMD
  export XDG_SESSION_TYPE=wayland
  export XDG_CURRENT_DESKTOP=sway
  export XDG_SESSION_DESKTOP=sway
  export HOME=${HOME:-/home/kvn}
  export WLR_BACKENDS=$wlr_session_backends
  export LIBSEAT_BACKEND=${LIBSEAT_BACKEND:-logind}
  export WLR_DRM_DEVICES
  WLR_DRM_DEVICES=$(pick_drm_devices)
  printf 'launch-on-vt uid=%s session=%s tty=%s drm=%s backends=%s config=%s\n' \
    "$UID" "${XDG_SESSION_ID:-}" "$(tty 2>/dev/null || true)" "$WLR_DRM_DEVICES" "$WLR_BACKENDS" "$config"
  cd "$HOME"
  local i
  for i in $(seq 1 12); do
    printf 'sway attempt %s\n' "$i"
    if dbus-run-session -- /usr/bin/sway --config "$config"; then
      exit 0
    fi
    sleep 0.4
  done
  printf 'sway failed after retries\n'
  exit 1
}

# Ignore logind/video-bus/power and virtual injectors. Need a real kb + pointer.
sway_has_real_input() {
  local sock json
  sock=$(sway_sock) || return 1
  json=$(swaymsg -s "$sock" -t get_inputs 2>/dev/null) || return 1
  command -v jq >/dev/null 2>&1 || return 1
  jq -e '
    def real:
      (.identifier // "") | test("virtual|Video Bus|Power Button|Sleep Button";"i") | not;
    ([.[] | select(.type=="keyboard" and real)] | length > 0)
    and
    ([.[] | select((.type=="pointer" or .type=="touchpad") and real)] | length > 0)
  ' <<<"$json" >/dev/null
}

dump_sway_log() {
  local persist
  persist=$(persist_dir)
  if [[ -s $sway_log ]]; then
    tail -n 40 "$sway_log" >&2 || true
  elif [[ -s $persist/sway.log ]]; then
    tail -n 40 "$persist/sway.log" >&2 || true
  elif [[ -s /tmp/agent-seat/sway.log ]]; then
    tail -n 40 /tmp/agent-seat/sway.log >&2 || true
  fi
}

wait_for_drm_sway() {
  local i have_drm=false
  for i in $(seq 1 100); do
    if sway_is_drm; then
      have_drm=true
      if sway_has_real_input; then
        return 0
      fi
    fi
    sleep 0.1
  done
  if [[ $have_drm == true ]]; then
    printf 'sway came up on DRM without keyboard/pointer (see %s)\n' "$sway_log" >&2
  else
    printf 'sway did not start on DRM (see %s)\n' "$sway_log" >&2
  fi
  dump_sway_log
  return 1
}

fail_back_to_hyprland() {
  local vt
  vt=$(hyprland_vt)
  sudo -n "$vt_helper" chvt "$vt" || true
  notify 'Sway failed' "Blank TTY avoided. See $sway_log"
}

start_sway() {
  require sway
  resolve_config
  mkdir -p "$runtime"
  save_hyprland_origin
  if sway_is_drm; then
    return 0
  fi
  if sway_running; then
    printf 'killing nested/non-DRM sway so it cannot be mistaken for the session\n' >&2
    kill_sway
  fi
  ensure_helper
  if ! helper_is_current; then
    write_install_script
    print_install_hint
    exit 1
  fi
  sudo -n "$vt_helper" start
  if ! wait_for_drm_sway; then
    kill_sway
    fail_back_to_hyprland
    exit 1
  fi
}

to_sway() {
  start_sway
  # start already openvt -s; chvt is idempotent if Sway was already running.
  ensure_helper
  sudo -n "$vt_helper" chvt "$sway_vt"
}

to_hyprland() {
  ensure_helper
  local vt
  vt=$(hyprland_vt)
  sudo -n "$vt_helper" chvt "$vt"
}

toggle() {
  mkdir -p "$runtime" "$(persist_dir)"
  exec >>"$toggle_log" 2>&1
  printf '\n== %s toggle ==\n' "$(date -Iseconds)"
  if on_sway; then
    to_hyprland
  else
    to_sway
  fi
  cp -f "$toggle_log" "$(persist_dir)/toggle.log" 2>/dev/null || true
}

stop_sway() {
  if on_sway; then
    to_hyprland || true
  fi
  if [[ -x $vt_helper ]]; then
    sudo -n "$vt_helper" stop || true
  else
    kill_sway
  fi
}

run_inside() {
  sway_is_drm || start_sway
  if [[ -f $envfile ]]; then
    # shellcheck disable=SC1090
    source "$envfile"
  fi
  if [[ $# -eq 0 ]]; then
    set -- kitty
  fi
  if [[ -n ${SWAYSOCK:-} ]]; then
    exec swaymsg exec "$(printf '%q ' "$@")"
  fi
  exec "$@"
}

show_status() {
  local compositor=unknown
  on_hyprland && compositor=hyprland
  on_sway && compositor=sway
  local sock drm=false
  sock=$(sway_sock || true)
  sway_is_drm && drm=true
  jq -n \
    --arg compositor "$compositor" \
    --arg hypr_vt "$(hyprland_vt)" \
    --arg sway_vt "$sway_vt" \
    --argjson sway_running "$(sway_running && echo true || echo false)" \
    --argjson sway_drm "$drm" \
    --arg sock "${sock:-}" \
    '{compositor:$compositor, hyprland_vt:$hypr_vt, sway_vt:$sway_vt, sway_running:$sway_running, sway_drm:$sway_drm, swaysock:$sock}'
}

usage() {
  printf 'usage: %s {toggle|start|stop|to-sway|to-hyprland|status|run [cmd...]|apply-outputs|on-sway-start|attach|launch-on-vt}\n' "${0##*/}" >&2
  exit 2
}

cmd=${1:-toggle}
shift || true
case $cmd in
  toggle) toggle ;;
  start) start_sway ;;
  stop) stop_sway ;;
  to-sway) to_sway ;;
  to-hyprland) to_hyprland ;;
  status) show_status ;;
  run) run_inside "$@" ;;
  apply-outputs) apply_outputs ;;
  on-sway-start) on_sway_start ;;
  attach) attach_virtual ;;
  launch-on-vt) launch_on_vt ;;
  *) usage ;;
esac
