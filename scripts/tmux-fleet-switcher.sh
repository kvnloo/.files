#!/usr/bin/env bash
set -euo pipefail

command -v tmux >/dev/null 2>&1 || exit 1
if ! command -v fzf >/dev/null 2>&1; then
  tmux display-message "fleet dashboard requires fzf"
  exit 1
fi

FZF_DEFAULT_OPTS=${FZF_DEFAULT_OPTS:-}
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
color8=${color8:-#737aa2}

harness_name() {
  local command=${1,,} title=${2,,} pane_pid=${3:-}
  case "$command" in
    claude)   printf 'Claude Code' ;;
    codex)    printf 'Codex' ;;
    opencode) printf 'OpenCode' ;;
    gemini)   printf 'Gemini' ;;
    kimi)     printf 'Kimi Code' ;;
    grok)     printf 'Grok' ;;
    omp)      printf 'Oh My Pi' ;;
    bun|node)
      child_commands=$(ps -o args= --ppid "$pane_pid" 2>/dev/null || true)
      if [[ $title == π:* || $title == *'oh my pi'* || $child_commands == *'/omp'* ]]; then
        printf 'Oh My Pi'
      else
        printf '%s' "$command"
      fi
      ;;
    zsh|bash|fish) printf 'Shell' ;;
    *) printf '%s' "${command:-unknown}" ;;
  esac
}

rows=$(
  while IFS='|' read -r pane address active command path title pane_pid; do
    harness=$(harness_name "$command" "$title" "$pane_pid")
    project=$(basename "$path")
    printf 'tmux\t%s\t%s\t%-12s\t%-18s\t%-8s\t%s\n' \
      "$pane" "$active" "$harness" "$project" "$address" "$title"
  done < <(
    tmux list-panes -a -F '#{pane_id}|#{session_name}:#{window_index}.#{pane_index}|#{?pane_active,●,○}|#{pane_current_command}|#{pane_current_path}|#{pane_title}|#{pane_pid}'
  )

  if command -v agent-deck >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
    deck_json=$(agent-deck list --json 2>/dev/null || true)
    if [[ $deck_json == \[* ]]; then
      jq -r '.[] | ["deck", .id, (if .status == "running" then "●" elif .status == "waiting" then "!" elif .status == "error" then "×" else "○" end), (.tool // "agent"), ((.path // "") | split("/") | last), (.group // "-"), (.title // "untitled")] | @tsv' <<< "$deck_json"
    fi
  fi
)

selection=$(
  printf '%s\n' "$rows" |
    fzf \
      --ansi \
      --delimiter=$'\t' \
      --with-nth=3.. \
      --no-multi \
      --layout=reverse \
      --border=rounded \
      --info=inline-right \
      --prompt='󰚩 agents › ' \
      --pointer='▶' \
      --marker='●' \
      --header='state  harness       project             location  task · enter: open · esc: close' \
      --preview='if [ {1} = tmux ]; then tmux capture-pane -ep -t {2} -S -120 2>/dev/null; else agent-deck list --json 2>/dev/null | jq -r '"'"'.[] | select(.id == "{2}")'"'"'; fi' \
      --preview-window='right,58%,wrap,border-left' \
      --color="bg:$background,bg+:$color0,fg:$foreground,fg+:$foreground,hl:$color6,hl+:$color4,border:$color8,prompt:$color6,pointer:$color5,marker:$color2,spinner:$color3,header:$color8"
) || exit 0

[[ -n $selection ]] || exit 0
type=${selection%%$'\t'*}
remainder=${selection#*$'\t'}
target=${remainder%%$'\t'*}

if [[ $type == deck ]]; then
  exec env AGENTDECK_ALLOW_OUTER_TMUX=1 agent-deck session attach "$target"
fi

session=$(tmux display-message -p -t "$target" '#{session_name}')
if [[ -n ${TMUX_AGENT_FLEET_CLIENT:-} ]]; then
  tmux switch-client -c "$TMUX_AGENT_FLEET_CLIENT" -t "=$session"
else
  tmux switch-client -t "=$session"
fi
tmux select-window -t "$target"
tmux select-pane -t "$target"
