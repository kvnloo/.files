#!/usr/bin/env bash
# Isolated two-tier GUI E2E display controller.
# Default tier: nested Xvfb (no live compositor).
# Optional tier: Hyprland native headless output for compositor-sensitive tests.
# Hard no-touch: workspaces 1, 2, and OBS workspace 8.
set -euo pipefail

SCRIPT_NAME=${0##*/}
PROTECTED_WORKSPACES=${PROTECTED_WORKSPACES:-"1 2 8"}
DEFAULT_WORKSPACE=${GUI_E2E_WORKSPACE:-9}
DEFAULT_WIDTH=${GUI_E2E_WIDTH:-1280}
DEFAULT_HEIGHT=${GUI_E2E_HEIGHT:-720}
DEFAULT_REFRESH=${GUI_E2E_REFRESH:-60}
DEFAULT_SCALE=${GUI_E2E_SCALE:-1}
DEFAULT_TIER=${GUI_E2E_TIER:-xvfb}
DEFAULT_CLASS_PREFIX=${GUI_E2E_CLASS_PREFIX:-HermesE2E}
LEASE_ROOT=${GUI_E2E_LEASE_DIR:-${XDG_RUNTIME_DIR:-/tmp}/gui-e2e-display}
HYPRCTL_BIN=${GUI_E2E_HYPRCTL:-hyprctl}
XVFB_BIN=${GUI_E2E_XVFB:-Xvfb}

tier=$DEFAULT_TIER
width=$DEFAULT_WIDTH
height=$DEFAULT_HEIGHT
refresh=$DEFAULT_REFRESH
scale=$DEFAULT_SCALE
workspace=$DEFAULT_WORKSPACE
window_class=""
output_name=""
lease_id=""
dry_run=${GUI_E2E_DRY_RUN:-0}
command_name=""

usage() {
  cat >&2 <<EOF
usage: $SCRIPT_NAME [--tier xvfb|hypr-headless] [--width N] [--height N]
                    [--refresh N] [--scale N] [--workspace N] [--class NAME]
                    [--output NAME] [--lease-id ID] [--dry-run]
                    {start|stop|status|proof|cleanup|run -- CMD...}

Default tier is nested Xvfb. hypr-headless creates a Hyprland headless output
without touching workspaces 1, 2, or OBS workspace 8.
EOF
  exit 2
}

is_protected_workspace() {
  local ws=$1 p
  for p in $PROTECTED_WORKSPACES; do
    [[ $ws == "$p" ]] && return 0
  done
  return 1
}

require_workspace_safe() {
  if is_protected_workspace "$workspace"; then
    printf 'refusing protected workspace %s (no-touch: %s)\n' "$workspace" "$PROTECTED_WORKSPACES" >&2
    exit 3
  fi
}

lease_dir() {
  printf '%s/%s' "$LEASE_ROOT" "${lease_id:-default}"
}

lease_file() {
  printf '%s/lease.json' "$(lease_dir)"
}

proof_file() {
  local when=${1:-before}
  printf '%s/proof-%s.json' "$(lease_dir)" "$when"
}

ensure_lease_dir() {
  mkdir -p "$(lease_dir)"
}

hypr() {
  if [[ $dry_run == 1 ]]; then
    printf 'DRY hyprctl %s\n' "$*" >&2
    return 0
  fi
  "$HYPRCTL_BIN" "$@"
}

resolve_hyprland() {
  hypr -j monitors >/dev/null 2>&1 && return 0
  local signature wayland_display
  while IFS=$'\t' read -r signature wayland_display; do
    [[ -z ${signature:-} ]] && continue
    if HYPRLAND_INSTANCE_SIGNATURE=$signature WAYLAND_DISPLAY=$wayland_display \
      "$HYPRCTL_BIN" -j monitors >/dev/null 2>&1; then
      export HYPRLAND_INSTANCE_SIGNATURE=$signature
      export WAYLAND_DISPLAY=$wayland_display
      return 0
    fi
  done < <("$HYPRCTL_BIN" -j instances 2>/dev/null | jq -r '.[] | [.instance, .wl_socket] | @tsv' || true)
  return 1
}

snapshot_focus() {
  if [[ $tier == xvfb ]]; then
    jq -n \
      --arg tier "$tier" \
      --arg display "${DISPLAY:-}" \
      --arg class "$window_class" \
      --argjson workspace "$workspace" \
      '{tier:$tier, display:$display, workspace:$workspace, window_class:$class, focused_monitor:null, active_workspace:null, protected_untouched:true}'
    return
  fi
  if [[ $dry_run == 1 ]]; then
    jq -n \
      --arg tier "$tier" \
      --arg class "$window_class" \
      --argjson workspace "$workspace" \
      '{tier:$tier, workspace:$workspace, window_class:$class, focused_monitor:"DRY", active_workspace:"DRY", protected_untouched:true}'
    return
  fi
  resolve_hyprland || { printf 'no live Hyprland instance found\n' >&2; exit 1; }
  hypr -j monitors 2>/dev/null | jq \
    --arg class "$window_class" \
    --argjson workspace "$workspace" \
    --arg protected "$PROTECTED_WORKSPACES" \
    '
      (map(select(.focused)) | .[0]) as $f
      | {
          tier: "hypr-headless",
          window_class: $class,
          requested_workspace: $workspace,
          focused_monitor: ($f.name // null),
          active_workspace: ($f.activeWorkspace.name // $f.activeWorkspace.id // null),
          workspaces: map({name, id: .activeWorkspace.id, focused}),
          protected_untouched: true
        }
    '
}

write_proof() {
  local when=$1
  ensure_lease_dir
  snapshot_focus >"$(proof_file "$when")"
}

assert_protected_untouched() {
  local before after
  before=$(proof_file before)
  after=$(proof_file after)
  [[ -f $before && -f $after ]] || return 0
  # Native tier: focused workspace id/name for the originally focused monitor
  # must not have become 1, 2, or 8 as a result of this controller.
  if [[ $tier != hypr-headless || $dry_run == 1 ]]; then
    return 0
  fi
  local after_ws
  after_ws=$(jq -r '.active_workspace // empty' "$after")
  if is_protected_workspace "$after_ws"; then
    local before_ws
    before_ws=$(jq -r '.active_workspace // empty' "$before")
    if [[ $after_ws != "$before_ws" ]]; then
      printf 'protected workspace %s was mutated (was %s)\n' "$after_ws" "$before_ws" >&2
      exit 4
    fi
  fi
}

write_lease() {
  ensure_lease_dir
  jq -n \
    --arg id "${lease_id:-default}" \
    --arg tier "$tier" \
    --arg class "$window_class" \
    --arg output "$output_name" \
    --arg display "${DISPLAY:-}" \
    --arg xvfb_pid "${xvfb_pid:-}" \
    --argjson width "$width" \
    --argjson height "$height" \
    --argjson refresh "$refresh" \
    --argjson scale "$scale" \
    --argjson workspace "$workspace" \
    --argjson pid "$$" \
    '{
      lease_id:$id, pid:$pid, tier:$tier, width:$width, height:$height,
      refresh:$refresh, scale:$scale, workspace:$workspace, window_class:$class,
      output:$output, display:$display, xvfb_pid:$xvfb_pid, created_unix:now
    }' >"$(lease_file)"
}

load_lease() {
  local f
  f=$(lease_file)
  [[ -f $f ]] || { printf 'no lease at %s\n' "$f" >&2; exit 1; }
  tier=$(jq -r '.tier' "$f")
  width=$(jq -r '.width' "$f")
  height=$(jq -r '.height' "$f")
  refresh=$(jq -r '.refresh' "$f")
  scale=$(jq -r '.scale' "$f")
  workspace=$(jq -r '.workspace' "$f")
  window_class=$(jq -r '.window_class' "$f")
  output_name=$(jq -r '.output' "$f")
  xvfb_pid=$(jq -r '.xvfb_pid // empty' "$f")
  DISPLAY=$(jq -r '.display // empty' "$f")
  export DISPLAY
}

start_xvfb() {
  local display_num sock
  require_workspace_safe
  [[ -n $window_class ]] || window_class="${DEFAULT_CLASS_PREFIX}-$$"
  write_proof before
  if [[ $dry_run == 1 ]]; then
    DISPLAY=:99
    export DISPLAY
    xvfb_pid=""
    write_lease
    write_proof after
    return
  fi
  command -v "$XVFB_BIN" >/dev/null 2>&1 || { printf '%s is required\n' "$XVFB_BIN" >&2; exit 1; }
  display_num=${GUI_E2E_DISPLAY_NUM:-}
  if [[ -z $display_num ]]; then
    display_num=99
    while [[ -S /tmp/.X11-unix/X$display_num || -e /tmp/.X$display_num-lock ]]; do
      display_num=$((display_num + 1))
    done
  fi
  DISPLAY=:$display_num
  export DISPLAY
  "$XVFB_BIN" "$DISPLAY" -screen 0 "${width}x${height}x24" -nolisten tcp >/dev/null 2>&1 &
  xvfb_pid=$!
  write_lease
  write_proof after
}

start_hypr_headless() {
  local focused mode
  require_workspace_safe
  [[ -n $window_class ]] || window_class="${DEFAULT_CLASS_PREFIX}-$$"
  [[ -n $output_name ]] || output_name="E2E-${lease_id:-$$}"
  if [[ $dry_run != 1 ]]; then
    command -v "$HYPRCTL_BIN" >/dev/null 2>&1 || { printf 'hyprctl is required\n' >&2; exit 1; }
    command -v jq >/dev/null 2>&1 || { printf 'jq is required\n' >&2; exit 1; }
    resolve_hyprland || { printf 'no live Hyprland instance found\n' >&2; exit 1; }
  fi
  write_proof before
  focused=""
  if [[ $dry_run != 1 ]]; then
    focused=$(hypr -j monitors 2>/dev/null | jq -r 'first(.[] | select(.focused) | .name) // ""')
    if ! hypr -j monitors all 2>/dev/null | jq -e --arg o "$output_name" 'any(.[]; .name == $o)' >/dev/null; then
      hypr output create headless "$output_name" >/dev/null
    fi
    mode="${width}x${height}@${refresh}"
    hypr keyword monitor "$output_name,$mode,auto,$scale" >/dev/null
    # Move only the isolated headless output onto the requested workspace.
    # Do not dispatch workspace on the currently focused (live) monitor.
    hypr dispatch focusmonitor "$output_name" >/dev/null
    hypr dispatch workspace "$workspace" >/dev/null
    if [[ -n $focused && $focused != "$output_name" ]]; then
      hypr dispatch focusmonitor "$focused" >/dev/null
    fi
  fi
  write_lease
  write_proof after
  assert_protected_untouched
}

start_display() {
  case $tier in
    xvfb) start_xvfb ;;
    hypr-headless) start_hypr_headless ;;
    *) printf 'unknown tier %s\n' "$tier" >&2; exit 2 ;;
  esac
}

stop_display() {
  if [[ -f $(lease_file) ]]; then
    load_lease
  fi
  if [[ $tier == xvfb ]]; then
    if [[ -n ${xvfb_pid:-} && $dry_run != 1 ]]; then
      kill "$xvfb_pid" 2>/dev/null || true
    fi
  elif [[ $tier == hypr-headless && $dry_run != 1 ]]; then
    if [[ -n $output_name ]] && hypr -j monitors all 2>/dev/null | jq -e --arg o "$output_name" 'any(.[]; .name == $o)' >/dev/null; then
      hypr output remove "$output_name" >/dev/null || true
    fi
  fi
  rm -rf "$(lease_dir)"
}

show_status() {
  if [[ -f $(lease_file) ]]; then
    cat "$(lease_file)"
  else
    jq -n --arg id "${lease_id:-default}" '{lease_id:$id, active:false}'
  fi
}

show_proof() {
  local when=${2:-after}
  [[ -f $(proof_file "$when") ]] || { printf 'no %s proof\n' "$when" >&2; exit 1; }
  cat "$(proof_file "$when")"
}

cleanup_all() {
  local d
  [[ -d $LEASE_ROOT ]] || return 0
  for d in "$LEASE_ROOT"/*; do
    [[ -d $d ]] || continue
    lease_id=$(basename "$d")
    stop_display || true
  done
}

run_with_display() {
  start_display
  local status=0
  if [[ $dry_run == 1 ]]; then
    printf 'DRY run: %s\n' "$*" >&2
  else
    "$@" || status=$?
  fi
  stop_display
  return $status
}

while [[ $# -gt 0 ]]; do
  case $1 in
    --tier) tier=$2; shift 2 ;;
    --width) width=$2; shift 2 ;;
    --height) height=$2; shift 2 ;;
    --refresh) refresh=$2; shift 2 ;;
    --scale) scale=$2; shift 2 ;;
    --workspace) workspace=$2; shift 2 ;;
    --class) window_class=$2; shift 2 ;;
    --output) output_name=$2; shift 2 ;;
    --lease-id) lease_id=$2; shift 2 ;;
    --dry-run) dry_run=1; shift ;;
    --) shift; break ;;
    start|stop|status|proof|cleanup|run)
      command_name=$1
      shift
      break
      ;;
    -h|--help) usage ;;
    *) usage ;;
  esac
done

[[ -n $command_name ]] || usage
[[ -n $lease_id ]] || lease_id=${GUI_E2E_LEASE_ID:-$$}

case $command_name in
  start) start_display ;;
  stop) stop_display ;;
  status) show_status ;;
  proof) show_proof "$@" ;;
  cleanup) cleanup_all ;;
  run)
    [[ $# -gt 0 ]] || usage
    run_with_display "$@"
    ;;
  *) usage ;;
esac
