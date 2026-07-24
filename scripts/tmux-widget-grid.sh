#!/usr/bin/env bash
set -euo pipefail

command -v tmux >/dev/null 2>&1 || { printf 'tmux is required\n' >&2; exit 1; }
script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
renderer="$script_dir/tmux-widget-renderer.sh"
session=${TMUX_WIDGET_SESSION:-0}
window_name=${TMUX_WIDGET_WINDOW_NAME:-dashboard}
FZF_DEFAULT_OPTS=${FZF_DEFAULT_OPTS:-}
LS_COLORS=${LS_COLORS:-}

registry() {
  printf '%s\n' \
    $'tasks\tContinuous task updates\tlive OMP todo phases, active work, and completion state' \
    $'agents\tLive OMP / background agents\tworkspace-copilot semantic harness state and active assignment' \
    $'overview\tOptional workspace telemetry\tcondensed monitors, network, system, and tmux summary' \
    $'topology\tWorkspace / tmux topology\tprivacy-sanitized sessions, windows, panes, and projects' \
    $'displays\tMonitors / virtual displays\tsanitized monitor geometry, refresh, scale, and workspace' \
    $'network\tTailscale / network\tbackend and peer counts without hostnames or addresses' \
    $'system\tClock / system\ttime, uptime, load, memory, and root filesystem usage'
}

valid_widget() {
  case ${1:-} in tasks|agents|overview|topology|displays|network|system) return 0 ;; *) return 1 ;; esac
}

pane_command() {
  local id=$1 quoted_renderer quoted_id quoted_manager
  printf -v quoted_renderer '%q' "$renderer"
  printf -v quoted_id '%q' "$id"
  printf -v quoted_manager '%q' "$script_dir/tmux-widget-grid.sh"
  printf 'exec env TMUX_WIDGET_MANAGER=%s %s %s' "$quoted_manager" "$quoted_renderer" "$quoted_id"
}

stored_window() {
  local target
  target=$(tmux show-options -gqv @widget_grid_window 2>/dev/null || true)
  [[ -n $target ]] || return 1
  [[ $(tmux show-options -wqv -t "$target" @widget_grid 2>/dev/null || true) == 1 ]] || return 1
  printf '%s' "$target"
}

stored_pane() {
  local target
  target=$(tmux show-options -gqv @widget_grid_pane 2>/dev/null || true)
  [[ -n $target ]] || return 1
  [[ $(tmux show-options -pqv -t "$target" @widget_id 2>/dev/null || true) == tasks ]] || return 1
  printf '%s' "$target"
}

active_target() {
  local target=${TMUX_WIDGET_TARGET:-${TMUX_PANE:-}}
  [[ -n $target ]] || target=$(tmux display-message -p '#{pane_id}')
  [[ $(tmux show-options -wqv -t "$target" @widget_grid 2>/dev/null || true) == 1 ]] || {
    tmux display-message 'widget control is only available inside the dashboard'
    return 1
  }
  printf '%s' "$target"
}

set_widget() {
  local target=$1 id=$2 command
  valid_widget "$id" || { tmux display-message "unknown widget: $id"; return 1; }
  command=$(pane_command "$id")
  tmux set-option -pq -t "$target" @widget_id "$id"
  tmux respawn-pane -k -t "$target" "$command"
}

repair_grid() {
  local window=$1 pane dead id found=0
  while IFS=$'\t' read -r pane dead; do
    id=$(tmux show-options -pqv -t "$pane" @widget_id 2>/dev/null || true)
    valid_widget "$id" || continue
    found=1
    [[ $dead == 1 ]] && set_widget "$pane" "$id"
  done < <(tmux list-panes -t "$window" -F '#{pane_id}\t#{pane_dead}')
  ((found == 1))
}

refresh_grid() {
  local window active layout pane id dedicated
  window=$(stored_window) || { tmux display-message 'widget dashboard is not open'; return 1; }
  active=$(tmux display-message -p -t "$window" '#{pane_id}')
  layout=$(tmux show-options -wqv -t "$window" @widget_layout 2>/dev/null || printf tiled)
  dedicated=$(tmux show-options -wqv -t "$window" @widget_grid_dedicated 2>/dev/null || printf 0)
  while IFS= read -r pane; do
    id=$(tmux show-options -pqv -t "$pane" @widget_id 2>/dev/null || true)
    valid_widget "$id" && set_widget "$pane" "$id"
  done < <(tmux list-panes -t "$window" -F '#{pane_id}')
  if [[ $dedicated == 1 ]]; then
    tmux select-layout -t "$window" "$layout" >/dev/null 2>&1 || tmux select-layout -t "$window" tiled >/dev/null
  fi
  tmux select-pane -t "$active"
  tmux display-message 'dashboard widgets restarted'
}

focus_window() {
  local window=$1
  tmux select-window -t "$window"
  tmux select-pane -t "$window"
}

create_agent_pane() {
  local task=$1 orientation=$2 command pane
  command=$(pane_command agents)
  if [[ $orientation == horizontal ]]; then
    pane=$(tmux split-window -h -p 50 -d -P -F '#{pane_id}' -t "$task" -c "$HOME" "$command")
  else
    pane=$(tmux split-window -v -p 50 -d -P -F '#{pane_id}' -t "$task" -c "$HOME" "$command")
  fi
  tmux set-option -pq -t "$pane" @widget_id agents
  tmux set-option -gq @widget_grid_agent_pane "$pane"
  printf '%s' "$pane"
}

auto_layout() {
  local force=${1:-} window dedicated mode width height count layout
  local task agent task_top agent_top task_width agent_width task_height agent_height
  local current desired group_width group_height half
  window=$(stored_window) || return 0
  mode=$(tmux show-options -wqv -t "$window" @widget_layout_mode 2>/dev/null || printf auto)
  [[ $force == force || $mode == auto ]] || return 0
  dedicated=$(tmux show-options -wqv -t "$window" @widget_grid_dedicated 2>/dev/null || printf 0)
  if [[ $dedicated == 1 ]]; then
    width=$(tmux display-message -p -t "$window" '#{window_width}')
    height=$(tmux display-message -p -t "$window" '#{window_height}')
    count=$(tmux display-message -p -t "$window" '#{window_panes}')
    if ((count <= 2)); then
      ((width >= height * 3)) && layout=even-horizontal || layout=even-vertical
    else
      layout=tiled
    fi
    tmux select-layout -t "$window" "$layout" >/dev/null 2>&1 || return 0
    tmux set-option -wq -t "$window" @widget_layout "$layout"
    tmux set-option -wq -t "$window" @widget_layout_mode auto
    return
  fi

  task=$(stored_pane) || return 0
  agent=$(tmux show-options -gqv @widget_grid_agent_pane 2>/dev/null || true)
  if [[ -z $agent || $(tmux show-options -pqv -t "$agent" @widget_id 2>/dev/null || true) != agents ]]; then
    agent=$(create_agent_pane "$task" horizontal)
  fi
  task_top=$(tmux display-message -p -t "$task" '#{pane_top}')
  agent_top=$(tmux display-message -p -t "$agent" '#{pane_top}')
  task_width=$(tmux display-message -p -t "$task" '#{pane_width}')
  agent_width=$(tmux display-message -p -t "$agent" '#{pane_width}')
  task_height=$(tmux display-message -p -t "$task" '#{pane_height}')
  agent_height=$(tmux display-message -p -t "$agent" '#{pane_height}')
  if [[ $task_top == "$agent_top" ]]; then
    current=horizontal
    group_width=$((task_width + agent_width + 1))
    group_height=$task_height
  else
    current=vertical
    group_width=$((task_width > agent_width ? task_width : agent_width))
    group_height=$((task_height + agent_height + 1))
  fi
  if ((group_width >= 88 || group_height < 18)); then
    desired=horizontal
  else
    desired=vertical
  fi
  if [[ $current != "$desired" ]]; then
    tmux kill-pane -t "$agent"
    agent=$(create_agent_pane "$task" "$desired")
    task_width=$(tmux display-message -p -t "$task" '#{pane_width}')
    agent_width=$(tmux display-message -p -t "$agent" '#{pane_width}')
    task_height=$(tmux display-message -p -t "$task" '#{pane_height}')
    agent_height=$(tmux display-message -p -t "$agent" '#{pane_height}')
  fi
  if [[ $desired == horizontal ]]; then
    half=$(((task_width + agent_width + 1) / 2))
    tmux resize-pane -t "$task" -x "$half" >/dev/null 2>&1 || true
  else
    half=$(((task_height + agent_height + 1) / 2))
    tmux resize-pane -t "$task" -y "$half" >/dev/null 2>&1 || true
  fi
  tmux set-option -wq -t "$window" @widget_layout_mode auto
}

dock_grid() {
  local target=${1:-${TMUX_PANE:-}} old_window window pane agent_pane dedicated
  [[ -n $target ]] || target=$(tmux display-message -p '#{pane_id}')
  if pane=$(stored_pane); then
    auto_layout force
    tmux select-window -t "$pane"
    tmux select-pane -t "$pane"
    tmux display-message 'continuous task dashboard focused · R restart · x close'
    return
  fi
  if old_window=$(stored_window); then
    dedicated=$(tmux show-options -wqv -t "$old_window" @widget_grid_dedicated 2>/dev/null || printf 0)
    if [[ $dedicated == 1 ]]; then
      tmux kill-window -t "$old_window"
    else
      tmux set-option -wu -t "$old_window" @widget_grid 2>/dev/null || true
      tmux set-option -wu -t "$old_window" @widget_grid_dedicated 2>/dev/null || true
    fi
  fi
  command=$(pane_command tasks)
  pane=$(tmux split-window -b -v -p 35 -d -P -F '#{pane_id}' -t "$target" -c "$HOME" "$command")
  window=$(tmux display-message -p -t "$target" '#{window_id}')
  tmux set-option -wq -t "$window" @widget_grid 1
  tmux set-option -wq -t "$window" @widget_grid_dedicated 0
  tmux set-option -pq -t "$pane" @widget_id tasks
  tmux set-option -gq @widget_grid_window "$window"
  tmux set-option -gq @widget_grid_pane "$pane"
  agent_pane=$(create_agent_pane "$pane" horizontal)
  auto_layout force
  tmux select-pane -t "$target"
  tmux display-message 'live task dashboard docked above current pane · Alt-d focuses it'
}

open_grid() {
  local window pane id command first=1
  if window=$(stored_window); then
    if repair_grid "$window"; then
      focus_window "$window"
      tmux display-message 'widget dashboard focused · R restart · r replace · m controls'
      return
    fi
    tmux set-option -wu -t "$window" @widget_grid 2>/dev/null || true
    tmux set-option -wu -t "$window" @widget_grid_dedicated 2>/dev/null || true
    tmux set-option -gu @widget_grid_window 2>/dev/null || true
    tmux set-option -gu @widget_grid_pane 2>/dev/null || true
    tmux set-option -gu @widget_grid_agent_pane 2>/dev/null || true
  fi
  tmux has-session -t "=$session" 2>/dev/null || { tmux display-message "tmux session $session is unavailable"; return 1; }
  command=$(pane_command tasks)
  window=$(tmux new-window -d -P -F '#{window_id}' -t "=$session:" -n "$window_name" -c "$HOME" "$command")
  tmux set-option -wq -t "$window" @widget_grid 1
  tmux set-option -wq -t "$window" @widget_layout even-horizontal
  tmux set-option -wq -t "$window" @widget_grid_dedicated 1
  tmux set-option -wq -t "$window" @widget_layout_mode auto
  tmux set-option -wq -t "$window" automatic-rename off
  tmux set-option -wq -t "$window" pane-border-format ' #P · #{@widget_id} '
  tmux set-option -gq @widget_grid_window "$window"
  pane=$(tmux display-message -p -t "$window" '#{pane_id}')
  tmux set-option -pq -t "$pane" @widget_id tasks
  command=$(pane_command agents)
  pane=$(tmux split-window -h -d -P -F '#{pane_id}' -t "$window" -c "$HOME" "$command")
  tmux set-option -pq -t "$pane" @widget_id agents
  auto_layout force
  focus_window "$window"
  tmux display-message 'task dashboard · live todo + OMP agents · r replace · a add · m menu'
}

fzf_widget() {
  local palette background foreground color0 color2 color3 color4 color5 color6 color8
  command -v fzf >/dev/null 2>&1 || { tmux display-message 'widget chooser requires fzf'; return 1; }
  palette="$HOME/.cache/wal/colors.sh"
  if [[ -r $palette ]]; then
    # shellcheck disable=SC1090
    source "$palette"
  fi
  background=${background:-#1a1b26}
  foreground=${foreground:-#c0caf5}
  color0=${color0:-$background}
  color2=${color2:-#9ece6a}
  color3=${color3:-#e0af68}
  color4=${color4:-#7aa2f7}
  color5=${color5:-#bb9af7}
  color6=${color6:-#7dcfff}
  color8=${color8:-#565f89}
  registry | fzf \
    --delimiter=$'\t' \
    --with-nth=2,3 \
    --no-multi \
    --layout=reverse \
    --border=rounded \
    --info=inline-right \
    --prompt='󰕮 widget › ' \
    --pointer='▶' \
    --header='widget                         source · enter: select · esc: close' \
    --color="bg:$background,bg+:$color0,fg:$foreground,fg+:$foreground,hl:$color6,hl+:$color4,border:$color8,prompt:$color6,pointer:$color5,marker:$color2,spinner:$color3,header:$color8"
}

choose_widget() {
  local mode=${1:-replace} id=${2:-} target window command pane
  target=$(active_target)
  if [[ -z $id ]]; then
    local selection
    selection=$(fzf_widget) || return 0
    id=${selection%%$'\t'*}
  fi
  valid_widget "$id" || { tmux display-message "unknown widget: $id"; return 1; }
  case $mode in
    replace)
      set_widget "$target" "$id"
      tmux display-message "widget replaced: $id"
      ;;
    add)
      window=$(tmux display-message -p -t "$target" '#{window_id}')
      command=$(pane_command "$id")
      pane=$(tmux split-window -d -P -F '#{pane_id}' -t "$target" -c "$HOME" "$command")
      tmux set-option -pq -t "$pane" @widget_id "$id"
      tmux select-layout -t "$window" "$(tmux show-options -wqv -t "$window" @widget_layout 2>/dev/null || printf tiled)" >/dev/null 2>&1 || tmux select-layout -t "$window" tiled >/dev/null
      auto_layout force
      tmux select-pane -t "$pane"
      tmux display-message "widget added: $id"
      ;;
    *) tmux display-message "unknown chooser mode: $mode"; return 1 ;;
  esac
}

popup_choose() {
  local mode=${1:-replace} target popup_cmd
  target=$(active_target)
  printf -v popup_cmd 'exec env TMUX_WIDGET_TARGET=%q %q choose %q' "$target" "$script_dir/tmux-widget-grid.sh" "$mode"
  tmux display-popup -E -t "$target" -w 72% -h 62% "$popup_cmd"
}

agent_selector() {
  local target data rows selection kind navigation session
  target=$(active_target)
  command -v workspace-copilot >/dev/null 2>&1 || {
    tmux display-message 'agent navigation requires workspace-copilot'
    return 1
  }
  data=$(timeout 5s workspace-copilot --json context 2>/dev/null || true)
  rows=$(jq -r '
    def marker($state):
      if ($state == "working" or $state == "running" or $state == "started") then "●"
      elif ($state == "waiting" or $state == "parked" or $state == "idle") then "◌"
      elif ($state == "blocked" or $state == "failed") then "!"
      elif $state == "completed" then "✓"
      else "·" end;
    (.harnesses[]? | (.state // "-") as $state |
      ["harness", (.session // ""), marker($state), $state, "OMP", (.harness // "omp"), (.project // "-"), (.label // "OMP session")] | @tsv),
    (.agent_deck.sessions[]? | (.status // "-") as $state |
      ["deck", (.id // ""), marker($state), $state, "DECK", (.tool // "agent"), (.project // "-"), (.title // "Agent Deck session")] | @tsv)
  ' <<<"$data" 2>/dev/null || true)
  if [[ -z $rows ]]; then
    tmux display-message 'no active agent metadata'
    return 0
  fi
  selection=$(printf '%s\n' "$rows" | fzf \
    --delimiter=$'\t' \
    --with-nth=3.. \
    --no-multi \
    --layout=reverse \
    --border=rounded \
    --info=inline-right \
    --prompt='󰚩 steer › ' \
    --pointer='▶' \
    --header=$'● active  ◌ waiting  ! blocked  ✓ done  · stopped\nstatus  source  engine  project  assignment · enter: open · esc: close') || return 0
  IFS=$'\t' read -r kind navigation _ <<<"$selection"
  if [[ $kind == deck ]]; then
    exec env AGENTDECK_ALLOW_OUTER_TMUX=1 agent-deck session attach "$navigation"
  fi
  if [[ $navigation == %* ]] && tmux display-message -p -t "$navigation" '#{pane_id}' >/dev/null 2>&1; then
    session=$(tmux display-message -p -t "$navigation" '#{session_name}')
    tmux switch-client -t "=$session"
    tmux select-window -t "$navigation"
    tmux select-pane -t "$navigation"
  else
    tmux display-message 'headless OMP subagent: steer it from the parent OMP pane'
  fi
}

popup_agents() {
  local target popup_cmd
  target=$(active_target)
  printf -v popup_cmd 'exec env TMUX_WIDGET_TARGET=%q %q agents' "$target" "$script_dir/tmux-widget-grid.sh"
  tmux display-popup -E -t "$target" -w 84% -h 70% "$popup_cmd"
}

remove_widget() {
  local target window count id dedicated agent_pane
  target=$(active_target)
  window=$(tmux display-message -p -t "$target" '#{window_id}')
  count=$(tmux display-message -p -t "$target" '#{window_panes}')
  id=$(tmux show-options -pqv -t "$target" @widget_id 2>/dev/null || true)
  dedicated=$(tmux show-options -wqv -t "$window" @widget_grid_dedicated 2>/dev/null || printf 0)
  if [[ $id == tasks && $dedicated == 0 ]]; then
    agent_pane=$(tmux show-options -gqv @widget_grid_agent_pane 2>/dev/null || true)
    [[ -n $agent_pane ]] && tmux kill-pane -t "$agent_pane" 2>/dev/null || true
    tmux set-option -gu @widget_grid_agent_pane
    tmux set-option -gu @widget_grid_pane
    tmux set-option -gu @widget_grid_window
    tmux set-option -wu -t "$window" @widget_grid
    tmux set-option -wu -t "$window" @widget_grid_dedicated
    tmux kill-pane -t "$target"
    return
  fi
  if ((count <= 1)); then
    tmux display-message 'the dashboard keeps at least one widget'
    return
  fi
  tmux kill-pane -t "$target"
  [[ $dedicated == 1 ]] && tmux select-layout -t "$window" "$(tmux show-options -wqv -t "$window" @widget_layout 2>/dev/null || printf tiled)" >/dev/null 2>&1 || true
  auto_layout force
}

cycle_layout() {
  local target window current next
  target=$(active_target)
  window=$(tmux display-message -p -t "$target" '#{window_id}')
  current=$(tmux show-options -wqv -t "$window" @widget_layout 2>/dev/null || true)
  case $current in
    tiled) next=even-horizontal ;;
    even-horizontal) next=even-vertical ;;
    even-vertical) next=main-horizontal ;;
    main-horizontal) next=main-vertical ;;
    *) next=tiled ;;
  esac
  tmux select-layout -t "$window" "$next" >/dev/null
  tmux set-option -wq -t "$window" @widget_layout "$next"
  tmux set-option -wq -t "$window" @widget_layout_mode manual
  tmux display-message "dashboard layout: $next"
}

swap_widget() {
  local direction flag target window neighbor
  direction=${1:-}
  case $direction in
    left) flag=-L ;;
    right) flag=-R ;;
    up) flag=-U ;;
    down) flag=-D ;;
    *) tmux display-message "unknown swap direction: $direction"; return 1 ;;
  esac
  target=$(active_target)
  window=$(tmux display-message -p -t "$target" '#{window_id}')
  tmux select-pane -t "$target" "$flag"
  neighbor=$(tmux display-message -p -t "$window" '#{pane_id}')
  if [[ $neighbor == "$target" ]]; then
    tmux display-message "no widget to the $direction"
    return
  fi
  tmux swap-pane -s "$target" -t "$neighbor"
  tmux select-pane -t "$target"
  tmux display-message "widget swapped $direction"
}

menu() {
  local target selection action argument
  target=$(active_target)
  command -v fzf >/dev/null 2>&1 || { tmux display-message 'widget menu requires fzf'; return 1; }
  selection=$(printf '%s\n' \
    $'library\tBrowse the entire widget library' \
    $'agents\tInspect or steer active subagents  [s]' \
    $'auto\tAuto-fit panes to the current tmux size' \
    $'refresh\tRestart every widget' \
    $'replace\tReplace active widget' \
    $'add\tAdd a widget pane' \
    $'remove\tRemove active widget pane' \
    $'layout\tCycle dashboard layout' \
    $'swap left\tSwap widget left  [H]' \
    $'swap down\tSwap widget down  [J]' \
    $'swap up\tSwap widget up  [K]' \
    $'swap right\tSwap widget right  [L]' | fzf --delimiter=$'\t' --with-nth=2 --layout=reverse --border=rounded --prompt='󰕮 controls › ' --header='R restart · r replace · a add · x remove · space layout · H/J/K/L swap') || return 0
  action=${selection%%$'\t'*}
  argument=${action#* }
  case $action in
    refresh) refresh_grid ;;
    agents) agent_selector ;;
    library) choose_widget replace ;;
    auto) tmux set-option -wq -t "$(tmux display-message -p -t "$target" '#{window_id}')" @widget_layout_mode auto; auto_layout force ;;
    replace) choose_widget replace ;;
    add) choose_widget add ;;
    remove) remove_widget ;;
    layout) cycle_layout ;;
    'swap '*) swap_widget "$argument" ;;
  esac
}

popup_menu() {
  local target popup_cmd
  target=$(active_target)
  printf -v popup_cmd 'exec env TMUX_WIDGET_TARGET=%q %q menu' "$target" "$script_dir/tmux-widget-grid.sh"
  tmux display-popup -E -t "$target" -w 68% -h 62% "$popup_cmd"
}

case ${1:-open} in
  dock) dock_grid "${2:-}" ;;
  open|focus) open_grid ;;
  list) registry ;;
  autolayout) auto_layout "${2:-}" ;;
  refresh) refresh_grid ;;
  choose) choose_widget "${2:-replace}" "${3:-}" ;;
  popup-choose) popup_choose "${2:-replace}" ;;
  agents) agent_selector ;;
  popup-agents) popup_agents ;;
  add) choose_widget add "${2:-}" ;;
  remove) remove_widget ;;
  layout) cycle_layout ;;
  swap) swap_widget "${2:-}" ;;
  menu) menu ;;
  library) choose_widget replace ;;
  popup) popup_menu ;;
  *)
    printf 'usage: %s {dock [pane]|open|refresh|list|choose [replace|add] [widget]|library|agents|popup-agents|remove|layout|autolayout [force]|swap {left|down|up|right}|popup}\n' "${0##*/}" >&2
    exit 2
    ;;
esac
