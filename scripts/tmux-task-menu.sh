#!/usr/bin/env bash
set -euo pipefail

runtime=${XDG_RUNTIME_DIR:-/tmp}/tmux-widget-grid-$UID
self=$(realpath "$0")
script_dir=$(dirname "$self")
copilot=${WORKSPACE_COPILOT_BIN:-"$script_dir/workspace-copilot"}

format_text() {
  local value=${1//$'\n'/ }
  value=${value//$'\t'/ }
  printf '%s' "${value//#/##}"
}

open_from_click() {
  local pane=${1:-} mouse_y=${2:-} map_file candidate row session phase delta
  [[ $pane == %* && $mouse_y =~ ^[0-9]+$ ]] || exit 0
  map_file="$runtime/task-map-${pane#%}.tsv"
  [[ -r $map_file ]] || exit 0
  candidate=$((mouse_y + 1))

  for delta in 0 -1 1; do
    while IFS=$'\t' read -r row session phase; do
      if [[ $row =~ ^[0-9]+$ ]] && ((row == candidate + delta)); then
        show_menu "$session" "$phase" "$pane"
        return
      fi
    done <"$map_file"
  done
}

show_menu() {
  local session=${1:-} phase=${2:-} pane=${3:-} data counts title status task icon color label
  local -a rows menu
  [[ $pane == %* ]] || exit 0
  [[ -x $copilot ]] || copilot=$(command -v workspace-copilot || true)
  [[ -x $copilot ]] || exit 1
  command -v jq >/dev/null 2>&1 || exit 1

  data=$("$copilot" --json context 2>/dev/null || true)
  [[ $data == \{* ]] || exit 1
  counts=$(jq -r --arg session "$session" --arg phase "$phase" '
    [.tasks[]? | select(.session == $session and .phase == $phase)] as $tasks
    | ($tasks | map(select(.status == "completed")) | length) as $done
    | ($tasks | map(select(.status == "in_progress")) | length) as $active
    | "\($done)/\($tasks | length) complete  ·  \($active) active"
  ' <<<"$data")
  mapfile -t rows < <(jq -r --arg session "$session" --arg phase "$phase" '
    [.tasks[]? | select(.session == $session and .phase == $phase)]
    | sort_by(.task_order)[]
    | [.status, .task] | @tsv
  ' <<<"$data")

  title=$(format_text "$phase")
  ((${#title} > 58)) && title="${title:0:57}…"
  menu=(display-menu -O -t "$pane" -x P -y P -T "#[fg=colour117,bold] $title #[default]" --)
  menu+=("-#[fg=colour60]$(format_text "$counts")#[default]" '' '')
  menu+=('')

  if ((${#rows[@]} == 0)); then
    menu+=("-#[fg=colour60]○  No subtasks published#[default]" '' '')
  else
    for label in "${rows[@]}"; do
      IFS=$'\t' read -r status task <<<"$label"
      case $status in
        completed) icon='✓'; color=78 ;;
        in_progress) icon='▶'; color=117 ;;
        abandoned) icon='–'; color=60 ;;
        *) icon='○'; color=252 ;;
      esac
      task=$(format_text "$task")
      ((${#task} > 68)) && task="${task:0:67}…"
      menu+=("-#[fg=colour${color}]$icon#[default]  $task" '' '')
    done
  fi

  menu+=('')
  menu+=("#[fg=colour60]Esc or click outside to close#[default]" '' '')
  tmux "${menu[@]}"
}

case ${1:-open} in
  open) open_from_click "${2:-}" "${3:-}" ;;
  menu) show_menu "${2:-}" "${3:-}" "${4:-}" ;;
  *) printf 'usage: %s open PANE MOUSE_Y | menu SESSION PHASE PANE\n' "$0" >&2; exit 2 ;;
esac
