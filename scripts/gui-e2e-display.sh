#!/usr/bin/env bash
# Isolated two-tier GUI display controller for ALL agent-opened windows.
# Default: nested Xvfb. Optional: Hyprland true headless output.
# Hard no-touch: workspaces 1, 2, and OBS workspace 8.
# If isolation cannot be established, refuse launch.
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
KNOWN_ROOTLESS_XVFB=${GUI_E2E_KNOWN_XVFB:-/home/kvn/.hermes/kanban/boards/hermes-agent/workspaces/t_6080dad3/xvfb-root/usr/bin/Xvfb}
DOTFILES_XVFB=${GUI_E2E_DOTFILES_XVFB:-${HOME}/.local/lib/gui-e2e/Xvfb}
XVFB_BIN=${GUI_E2E_XVFB:-}

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
xvfb_pid=""
run_started=0
cleaned=0
child_pid=""

usage() {
  cat <<EOF
usage: $SCRIPT_NAME [--tier xvfb|hypr-headless] [--width N] [--height N]
                    [--refresh N] [--scale N] [--workspace N] [--class NAME]
                    [--output NAME] [--lease-id ID] [--dry-run]
                    {start|stop|status|proof|cleanup|run -- CMD...}

Default tier is nested Xvfb (isolates ALL agent GUI: browser/Electron/native/
dialog/preview/capture). hypr-headless creates a true Hyprland headless output
without focusing it or touching workspaces 1, 2, or OBS workspace 8.
If isolation cannot be established, launch is refused.
EOF
  exit 0
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

resolve_xvfb() {
  if [[ -n ${XVFB_BIN:-} && -x $XVFB_BIN ]]; then
    return 0
  fi
  if command -v Xvfb >/dev/null 2>&1; then
    XVFB_BIN=$(command -v Xvfb)
    return 0
  fi
  local candidate
  for candidate in "$DOTFILES_XVFB" "$KNOWN_ROOTLESS_XVFB"; do
    if [[ -x $candidate ]]; then
      XVFB_BIN=$candidate
      return 0
    fi
  done
  printf 'Xvfb not found on PATH and no rootless/dotfiles binary available; refusing launch\n' >&2
  exit 1
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
      '{tier:$tier, display:$display, workspace:$workspace, window_class:$class, focused_monitor:null, physical_monitor_workspaces:{}, protected_untouched:true}'
    return
  fi
  if [[ $dry_run == 1 ]]; then
    jq -n \
      --arg tier "$tier" \
      --arg class "$window_class" \
      --argjson workspace "$workspace" \
      '{tier:$tier, workspace:$workspace, window_class:$class, focused_monitor:"DRY", physical_monitor_workspaces:{}, protected_untouched:true}'
    return
  fi
  resolve_hyprland || { printf 'no live Hyprland instance found\n' >&2; exit 1; }
  hypr -j monitors 2>/dev/null | jq \
    --arg class "$window_class" \
    --argjson workspace "$workspace" \
    --arg output "$output_name" \
    '
      (map(select(.focused)) | .[0]) as $f
      | {
          tier: "hypr-headless",
          window_class: $class,
          requested_workspace: $workspace,
          headless_output: $output,
          focused_monitor: ($f.name // null),
          physical_monitor_workspaces: (
            map(select((.name != $output) and ((.disabled // false) | not)))
            | map({key: .name, value: (.activeWorkspace.id // .activeWorkspace.name)})
            | from_entries
          ),
          all_monitors: map({name, focused, id: .activeWorkspace.id}),
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
  if [[ $tier != hypr-headless || $dry_run == 1 ]]; then
    return 0
  fi
  local mismatch focused_before focused_after
  mismatch=$(jq -n --slurpfile b "$before" --slurpfile a "$after" '
    ($b[0].physical_monitor_workspaces // {}) as $pb
    | ($a[0].physical_monitor_workspaces // {}) as $pa
    | ($pb | keys_unsorted) as $keys
    | [ $keys[] | select(($pb[.] | tostring) != ($pa[.] | tostring)) ]
  ')
  if [[ $mismatch != "[]" ]]; then
    printf 'physical monitor workspace mapping mutated: %s\n' "$mismatch" >&2
    exit 4
  fi
  focused_before=$(jq -r '.focused_monitor // empty' "$before")
  focused_after=$(jq -r '.focused_monitor // empty' "$after")
  if [[ -n $focused_before && $focused_after != "$focused_before" ]]; then
    printf 'focused monitor mutated: %s -> %s\n' "$focused_before" "$focused_after" >&2
    exit 4
  fi
  if [[ -n $output_name && $focused_after == "$output_name" ]]; then
    printf 'headless output %s became focused; refusing\n' "$output_name" >&2
    exit 4
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
    --arg xvfb_bin "${XVFB_BIN:-}" \
    --argjson width "$width" \
    --argjson height "$height" \
    --argjson refresh "$refresh" \
    --argjson scale "$scale" \
    --argjson workspace "$workspace" \
    --argjson pid "$$" \
    '{
      lease_id:$id, pid:$pid, tier:$tier, width:$width, height:$height,
      refresh:$refresh, scale:$scale, workspace:$workspace, window_class:$class,
      output:$output, display:$display, xvfb_pid:$xvfb_pid, xvfb_bin:$xvfb_bin,
      created_unix:now
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
  XVFB_BIN=$(jq -r '.xvfb_bin // empty' "$f")
  DISPLAY=$(jq -r '.display // empty' "$f")
  export DISPLAY
}

wait_for_x_socket() {
  local display_num=$1
  local sock=/tmp/.X11-unix/X$display_num
  local i
  for i in $(seq 1 50); do
    if ! kill -0 "$xvfb_pid" 2>/dev/null; then
      printf 'Xvfb exited before X socket %s was ready\n' "$sock" >&2
      return 1
    fi
    if [[ -S $sock ]]; then
      return 0
    fi
    sleep 0.05
  done
  printf 'timed out waiting for X socket %s\n' "$sock" >&2
  return 1
}

start_xvfb() {
  local display_num
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
  resolve_xvfb
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
  if ! wait_for_x_socket "$display_num"; then
    kill "$xvfb_pid" 2>/dev/null || true
    wait "$xvfb_pid" 2>/dev/null || true
    xvfb_pid=""
    printf 'refusing launch: isolated Xvfb display not ready\n' >&2
    exit 1
  fi
  write_lease
  write_proof after
}

start_hypr_headless() {
  local mode
  require_workspace_safe
  [[ -n $window_class ]] || window_class="${DEFAULT_CLASS_PREFIX}-$$"
  [[ -n $output_name ]] || output_name="E2E-${lease_id:-$$}"
  if [[ $dry_run != 1 ]]; then
    command -v "$HYPRCTL_BIN" >/dev/null 2>&1 || { printf 'hyprctl is required\n' >&2; exit 1; }
    command -v jq >/dev/null 2>&1 || { printf 'jq is required\n' >&2; exit 1; }
    resolve_hyprland || { printf 'no live Hyprland instance found; refusing launch\n' >&2; exit 1; }
  fi
  write_proof before
  if [[ $dry_run != 1 ]]; then
    if ! hypr -j monitors all 2>/dev/null | jq -e --arg o "$output_name" 'any(.[]; .name == $o)' >/dev/null; then
      hypr output create headless "$output_name" >/dev/null
    fi
    mode="${width}x${height}@${refresh}"
    hypr keyword monitor "$output_name,$mode,auto,$scale" >/dev/null
    # Bind workspace to headless output without focusing it or changing live WS.
    hypr keyword workspace "${workspace},monitor:${output_name},default:true" >/dev/null
    hypr dispatch moveworkspacetomonitor "$workspace" "$output_name" >/dev/null || true
    if [[ -n $window_class ]]; then
      hypr keyword windowrulev2 "workspace ${workspace} silent, class:^(${window_class})\$" >/dev/null || true
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
  write_proof after 2>/dev/null || true
  if [[ $tier == xvfb ]]; then
    if [[ -n ${xvfb_pid:-} && $dry_run != 1 ]]; then
      kill "$xvfb_pid" 2>/dev/null || true
      wait "$xvfb_pid" 2>/dev/null || true
      kill -9 "$xvfb_pid" 2>/dev/null || true
    fi
  elif [[ $tier == hypr-headless && $dry_run != 1 ]]; then
    if [[ -n $output_name ]] && hypr -j monitors all 2>/dev/null | jq -e --arg o "$output_name" 'any(.[]; .name == $o)' >/dev/null; then
      hypr output remove "$output_name" >/dev/null || true
    fi
  fi
  if [[ -f $(lease_file) ]]; then
    mv "$(lease_file)" "$(lease_dir)/lease-stopped.json"
  fi
}

show_status() {
  if [[ -f $(lease_file) ]]; then
    cat "$(lease_file)"
  else
    jq -n --arg id "${lease_id:-default}" '{lease_id:$id, active:false}'
  fi
}

show_proof() {
  local when=${1:-after}
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

on_run_exit() {
  [[ $run_started == 1 ]] || return 0
  [[ $cleaned == 1 ]] && return 0
  cleaned=1
  if [[ -n ${child_pid:-} ]]; then
    kill "$child_pid" 2>/dev/null || true
    wait "$child_pid" 2>/dev/null || true
  fi
  stop_display || true
}

run_with_display() {
  trap on_run_exit EXIT INT TERM
  run_started=1
  start_display
  local status=0
  if [[ $dry_run == 1 ]]; then
    printf 'DRY run: %s\n' "$*" >&2
  else
    "$@" &
    child_pid=$!
    wait "$child_pid" || status=$?
    child_pid=""
  fi
  write_proof after
  assert_protected_untouched
  cleaned=1
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
    *) printf 'unknown argument: %s\n' "$1" >&2; exit 2 ;;
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
    if [[ $1 == -- ]]; then
      shift
      [[ $# -gt 0 ]] || usage
    fi
    run_with_display "$@"
    ;;
  *) usage ;;
esac
