#!/usr/bin/env bash
set -u
# Mouse drags emit a SIGWINCH for every intermediate cell. Ignore the signal so
# the fixed render cadence coalesces those events instead of repainting per pixel.
trap '' WINCH

widget=${1:-system}
manager=${TMUX_WIDGET_MANAGER:-"$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)/tmux-widget-grid.sh"}

FZF_DEFAULT_OPTS=${FZF_DEFAULT_OPTS:-}
LS_COLORS=${LS_COLORS:-}
palette="$HOME/.cache/wal/colors.sh"
if [[ -r $palette ]]; then
  # shellcheck disable=SC1090
  source "$palette"
fi
background=${background:-#1a1b26}
foreground=${foreground:-#c0caf5}
color1=${color1:-#f7768e}
color2=${color2:-#9ece6a}
color3=${color3:-#e0af68}
color4=${color4:-#7aa2f7}
color5=${color5:-#bb9af7}
color6=${color6:-#7dcfff}
color8=${color8:-#565f89}
# A restrained frosted-glass scale: cool cyan body, white-blue glint, neutral
# slate track. It stays coherent when pywal's primary colors are pink/purple.
glass_fill_hex=${TMUX_WIDGET_GLASS_FILL:-#78cfff}
glass_soft_hex=${TMUX_WIDGET_GLASS_SOFT:-#a8e2ff}
glass_glint_hex=${TMUX_WIDGET_GLASS_GLINT:-#e8fbff}
glass_track_hex=${TMUX_WIDGET_GLASS_TRACK:-#4d5972}

ansi_fg() {
  local hex=${1#\#}
  printf '\033[38;2;%d;%d;%dm' "$((16#${hex:0:2}))" "$((16#${hex:2:2}))" "$((16#${hex:4:2}))"
}
reset=$'\033[0m'
accent=$(ansi_fg "$color4")
red=$(ansi_fg "$color1")
cyan=$(ansi_fg "$color6")
green=$(ansi_fg "$color2")
yellow=$(ansi_fg "$color3")
magenta=$(ansi_fg "$color5")
muted=$(ansi_fg "$color8")
text=$(ansi_fg "$foreground")
glass_fill=$(ansi_fg "$glass_fill_hex")
glass_soft=$(ansi_fg "$glass_soft_hex")
glass_glint=$(ansi_fg "$glass_glint_hex")
glass_track=$(ansi_fg "$glass_track_hex")

label_for() {
  case ${1:-} in
    tasks) printf 'CONTINUOUS TASK UPDATES' ;;
    agents) printf 'LIVE OMP / BACKGROUND AGENTS' ;;
    overview) printf 'OPTIONAL WORKSPACE TELEMETRY' ;;
    topology) printf 'SANITIZED WORKSPACE / TMUX' ;;
    displays) printf 'MONITORS / VIRTUAL DISPLAYS' ;;
    network) printf 'TAILSCALE / NETWORK' ;;
    system) printf 'CLOCK / SYSTEM' ;;
    *) printf 'UNKNOWN WIDGET' ;;
  esac
}

interval_for() {
  case ${1:-} in
    system) printf 2 ;;
    tasks|agents) printf 0.5 ;;
    overview|topology) printf 5 ;;
    displays) printf 8 ;;
    network) printf 10 ;;
    *) printf 5 ;;
  esac
}

context_json() {
  local runtime cache lock now stamp tmp
  runtime=${XDG_RUNTIME_DIR:-/tmp}/tmux-widget-grid-$UID
  cache=$runtime/context.json
  lock=$runtime/context.lock
  umask 077
  mkdir -p "$runtime"
  now=$(date +%s)
  stamp=0
  [[ -r $cache ]] && stamp=$(stat -c %Y "$cache" 2>/dev/null || printf 0)
  if ((now - stamp <= 2)); then
    cat "$cache"
    return
  fi
  exec 9>"$lock"
  if command -v flock >/dev/null 2>&1; then
    flock -w 3 9 || { [[ -r $cache ]] && cat "$cache"; return; }
  fi
  now=$(date +%s)
  stamp=0
  [[ -r $cache ]] && stamp=$(stat -c %Y "$cache" 2>/dev/null || printf 0)
  if ((now - stamp > 2)); then
    tmp=$cache.$$
    if timeout 4s workspace-copilot --json context >"$tmp" 2>/dev/null && jq -e 'type == "object"' "$tmp" >/dev/null 2>&1; then
      chmod 600 "$tmp"
      mv -f "$tmp" "$cache"
    else
      rm -f "$tmp"
    fi
  fi
  [[ -r $cache ]] && cat "$cache"
}

orb_frames=('● · ·' '◉ • ·' '• ● •' '· • ◉' '· · ●' '· • ◉' '• ● •' '◉ • ·')
pulse_frames=('·' '◦' '●' '◦')
orb_frame=${orb_frames[0]}
pulse_frame=${pulse_frames[0]}

progress_bar() {
  local done=${1:-0} total=${2:-0} active=${3:-0} width=${4:-16}
  local filled=0 index sweep=-10 distance glyph tone
  ((total > 0)) && filled=$(((done * width + total / 2) / total))
  ((active > 0 && filled > 0)) && sweep=$((animation_index % filled))
  for ((index = 0; index < width; index++)); do
    if ((index < filled)); then
      glyph='━'
      ((index == 0)) && glyph='╺'
      ((index == filled - 1)) && glyph='╸'
      tone=$glass_fill
      distance=$((index - sweep))
      ((distance < 0)) && distance=$((-distance))
      ((active > 0 && distance == 1)) && tone=$glass_soft
      ((active > 0 && distance == 0)) && tone=$glass_glint
      printf '%s%s' "$tone" "$glyph"
    else
      glyph='┄'
      ((index == width - 1)) && glyph='╴'
      printf '%s%s' "$glass_track" "$glyph"
    fi
  done
  printf '%s' "$reset"
}

render_agents() {
  local data=$1
  if [[ -z $data ]]; then
    printf '%sworkspace-copilot context unavailable%s\n' "$yellow" "$reset"
    return
  fi
  jq -r '
    def active: . == "working" or . == "running" or . == "started";
    def waiting: . == "waiting" or . == "parked" or . == "idle";
    def attention: . == "blocked" or . == "failed";
    ([.agent_deck.sessions[]? |
        [(.status // "-"), (.tool // "agent"), (.project // "-"), (.title // "Agent Deck session"), "deck", (.id // "")]]
     + [.harnesses[]? |
        [(.state // "-"), (.harness // "omp"), (.project // "-"), (.label // "OMP session"), "harness", (.session // "")]]) as $rows
    | ($rows | map(select(.[0] | active))) as $active
    | ($rows | map(select(.[0] | waiting))) as $waiting
    | ($rows | map(select(.[0] | attention))) as $attention
    | ($rows | map(select((.[0] | active or waiting or attention) | not))) as $finished
    | "SUMMARY\t\($active | length)\t\($waiting | length)\t\($attention | length)\t\($finished | length)\t\($rows | length)",
      ([["ACTIVE / EXECUTING", $active], ["WAITING / PARKED", $waiting],
        ["NEEDS ATTENTION", $attention], ["FINISHED / STOPPED", $finished]][]
       | .[0] as $title | .[1] as $items
       | select(($items | length) > 0)
       | "GROUP\t\($title)\t\($items | length)",
         ($items | to_entries[]
          | ["ROW",
             (if .key == (($items | length) - 1) then "└─" else "├─" end),
             (if .key == (($items | length) - 1) then "  " else "│ " end)]
            + .value
          | @tsv))
  ' <<<"$data" 2>/dev/null |
    while IFS=$'\t' read -r kind a b c d e f g h; do
      case $kind in
        SUMMARY)
          printf '%s%s%s active  ·  %s%s%s waiting  ·  %s%s%s attention  ·  %s tracked\n\n' \
            "$accent" "$a" "$reset" "$yellow" "$b" "$reset" "$red" "$c" "$reset" "$e"
          ;;
        GROUP)
          printf '%s%s%s  %s%s%s\n' "$text" "$a" "$reset" "$muted" "$b" "$reset"
          ;;
        ROW)
          local indicator indicator_color badge badge_color
          case $c in
            working|running|started) indicator=$orb_frame; indicator_color=$accent ;;
            waiting|parked|idle) indicator='◌'; indicator_color=$yellow ;;
            blocked|failed) indicator='!'; indicator_color=$red ;;
            completed) indicator='✓'; indicator_color=$green ;;
            *) indicator='·'; indicator_color=$muted ;;
          esac
          if [[ $g == deck ]]; then
            badge='DECK'
            badge_color=$magenta
          else
            badge='OMP'
            badge_color=$cyan
          fi
          printf '  %s%s%s %s%s%s  %s%-4s%s  %s%s%s  %s%s%s\n' \
            "$muted" "$a" "$reset" "$indicator_color" "$indicator" "$reset" \
            "$badge_color" "$badge" "$reset" "$text" "${c^^}" "$reset" "$muted" "$d" "$reset"
          printf '  %s%s└─%s %s%s%s %s·%s %s\n' \
            "$muted" "$b" "$reset" "$cyan" "${e:--}" "$reset" "$muted" "$reset" "${f:--}"
          ;;
      esac
    done
  printf '\n%sSTATUS%s  %s%s%s active   %s◌%s waiting   %s!%s blocked   %s✓%s done   %s·%s stopped\n' \
    "$muted" "$reset" "$accent" "${orb_frames[0]}" "$reset" "$yellow" "$reset" \
    "$red" "$reset" "$green" "$reset" "$muted" "$reset"
  printf '%sSOURCE%s  %sOMP%s live harness   %sDECK%s managed agent   %ss%s inspect / steer\n' \
    "$muted" "$reset" "$cyan" "$reset" "$magenta" "$reset" "$cyan" "$reset"
}
render_tasks() {
  local data=$1 session rows columns overall_width phase_width max_text
  local objective decisions runtime map_file map_tmp row phase_name name_width glyph summary_text
  if [[ -z $data ]]; then
    printf '%sworkspace-copilot context unavailable%s\n' "$yellow" "$reset"
    return
  fi
  session=$(jq -r '[.tasks[]?] | if length == 0 then "" else max_by(.updated_at).session end' <<<"$data")
  if [[ -z $session ]]; then
    printf '%sNo OMP task snapshot published yet.%s\n' "$yellow" "$reset"
    printf '%sThe session-recap extension publishes updates after each todo change.%s\n' "$muted" "$reset"
    return
  fi
  rows=$(tput lines 2>/dev/null || printf 24)
  columns=$(tput cols 2>/dev/null || printf 80)
  ((columns >= 80)) && overall_width=20 || { ((columns >= 55)) && overall_width=12 || overall_width=8; }
  ((columns >= 70)) && phase_width=10 || phase_width=6
  max_text=$((columns - 6))
  ((max_text < 18)) && max_text=18

  objective=$(jq -r --arg session "$session" '
    first(.task_sessions[]? | select(.session == $session) | .objective) // "Objective summary has not been published yet."
  ' <<<"$data")
  decisions=$(jq -r --arg session "$session" '
    (first(.task_sessions[]? | select(.session == $session) | .decisions) // [])
    | if length == 0 then "No high-level decisions published yet." else join(" · ") end
  ' <<<"$data")
  objective=${objective//$'\n'/ }
  decisions=${decisions//$'\n'/ }
  ((${#objective} > max_text)) && objective="${objective:0:max_text-1}…"
  ((${#decisions} > max_text)) && decisions="${decisions:0:max_text-1}…"

  printf '%sOBJ%s  %s\n' "$accent" "$reset" "$objective"
  printf '%sDEC%s  %s\n' "$magenta" "$reset" "$decisions"

  runtime=${XDG_RUNTIME_DIR:-/tmp}/tmux-widget-grid-$UID
  mkdir -p "$runtime"
  map_file=$runtime/task-map-${TMUX_PANE#%}.tsv
  map_tmp=$map_file.$$
  : >"$map_tmp"
  chmod 600 "$map_tmp"
  row=6

  jq -r --arg session "$session" '
    [.tasks[]? | select(.session == $session)] as $tasks
    | ($tasks | map(select(.status == "completed")) | length) as $done
    | ($tasks | map(select(.status == "in_progress")) | length) as $active
    | ($tasks | map(select(.status == "pending")) | length) as $pending
    | "SUMMARY\t\($done)\t\($active)\t\($pending)\t\($tasks | length)",
      ($tasks | sort_by(.phase_order, .task_order) | group_by(.phase_order)[] as $phase |
        "PHASE\t\($phase[0].phase)\t\($phase | map(select(.status == "completed")) | length)\t\($phase | length)\t\($phase | map(select(.status == "in_progress")) | length)")
  ' <<<"$data" 2>/dev/null |
    while IFS=$'\t' read -r kind first second third fourth; do
      case $kind in
        SUMMARY)
          progress_bar "$first" "$fourth" "$second" "$overall_width"
          summary_text="  ${first}/${fourth} complete · ${second} active · ${third} open"
          ((${#summary_text} > columns - overall_width)) && summary_text="  ${first}/${fourth} · ${third} open"
          printf '%s\n' "$summary_text"
          printf '%sTASK GROUPS%s  %sclick a row for subtasks%s\n' "$cyan" "$reset" "$muted" "$reset"
          row=6
          ;;
        PHASE)
          phase_name=$first
          name_width=$((columns - phase_width - 13))
          ((name_width < 10)) && name_width=10
          ((${#phase_name} > name_width)) && phase_name="${phase_name:0:name_width-1}…"
          if ((fourth > 0)); then
            glyph='▶'
          elif ((second == third)); then
            glyph='✓'
          else
            glyph='○'
          fi
          printf '%s%s%s %-*s ' "$glass_glint" "$glyph" "$reset" "$name_width" "$phase_name"
          progress_bar "$second" "$third" "$fourth" "$phase_width"
          printf ' %s/%s\n' "$second" "$third"
          printf '%s\t%s\t%s\n' "$row" "$session" "$first" >>"$map_tmp"
          row=$((row + 1))
          ;;
      esac
    done
  mv -f "$map_tmp" "$map_file"
}


render_topology() {
  local data=$1
  if [[ -z $data ]]; then
    printf '%sworkspace-copilot context unavailable%s\n' "$yellow" "$reset"
    return
  fi
  jq -r '
    .tmux[]?
    | "SESSION \(.session)  projects: \(.projects | join(", "))",
      (.windows[] | "  window \(.index)  \(.name)  (\(.panes | length) panes)",
        (.panes[] | "    \(if .active then "●" else "○" end) pane \(.index)  \(.command)  [\(.project)]"))
  ' <<<"$data" 2>/dev/null
}

render_displays() {
  local data=$1
  if [[ -z $data ]]; then
    printf '%sworkspace-copilot context unavailable%s\n' "$yellow" "$reset"
    return
  fi
  jq -r '
    if (.monitors | length) == 0 then "No monitor metadata available."
    else .monitors[]
      | if .available == false then "Hyprland monitor context unavailable."
        else "\(if .focused then "●" else "○" end) \(.name)\(if (.name | ascii_upcase | test("HEADLESS|VIRTUAL|PHONE")) then "  [virtual]" else "" end)\n    \(.width)x\(.height) @ \((.refresh_hz // 0) | floor) Hz  scale \(.scale)\n    position \(.x),\(.y)  workspace \(.workspace)  transform \(.transform)"
        end
    end
  ' <<<"$data" 2>/dev/null
}

render_network() {
  local state connectivity tail='Tailscale unavailable' online=0 total=0 exit_node='off'
  if command -v nmcli >/dev/null 2>&1; then
    IFS=: read -r state connectivity < <(timeout 2s nmcli -t -f STATE,CONNECTIVITY general 2>/dev/null || true)
  fi
  if command -v tailscale >/dev/null 2>&1 && command -v jq >/dev/null 2>&1; then
    local status
    status=$(timeout 3s tailscale status --json 2>/dev/null || true)
    if [[ $status == \{* ]]; then
      tail=$(jq -r '.BackendState // "unknown"' <<<"$status" 2>/dev/null)
      online=$(jq '[.Peer[]? | select(.Online == true)] | length' <<<"$status" 2>/dev/null)
      total=$(jq '[.Peer[]?] | length' <<<"$status" 2>/dev/null)
      exit_node=$(jq -r 'if (.ExitNodeStatus.Online // false) then "online" elif (.Self.ExitNode // false) then "enabled" else "off" end' <<<"$status" 2>/dev/null)
    fi
  fi
  printf '%sTAILSCALE%s\n  backend       %s\n  peers online  %s / %s\n  exit node     %s\n\n' "$magenta" "$reset" "$tail" "$online" "$total" "$exit_node"
  printf '%sNETWORKMANAGER%s\n  state         %s\n  connectivity  %s\n' "$cyan" "$reset" "${state:-unavailable}" "${connectivity:-unknown}"
}

render_system() {
  local up load mem_total mem_available mem_used disk
  up=$(uptime -p 2>/dev/null || printf unavailable)
  load=$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || printf unavailable)
  mem_total=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null)
  mem_available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null)
  if [[ $mem_total =~ ^[0-9]+$ && $mem_available =~ ^[0-9]+$ && $mem_total -gt 0 ]]; then
    mem_used=$((100 * (mem_total - mem_available) / mem_total))
  else
    mem_used='?'
  fi
  disk=$(timeout 2s df -P / 2>/dev/null | awk 'NR == 2 {print $5}' || true)
  printf '%s%s%s\n' "$accent" "$(date '+%A · %Y-%m-%d')" "$reset"
  printf '%s%s%s\n\n' "$green" "$(date '+%H:%M:%S %Z')" "$reset"
  printf 'uptime   %s\nload     %s\nmemory   %s%% used\nroot fs  %s used\n' "$up" "$load" "$mem_used" "${disk:-?}"
}

render_overview() {
  local data=$1 rows status tail_state='unavailable' online=0 total=0
  local mem_total mem_available mem_used disk load
  rows=$(tput lines 2>/dev/null || printf 12)
  if [[ -z $data ]]; then
    printf '%sworkspace-copilot context unavailable%s\n' "$yellow" "$reset"
    return
  fi

  printf '%sAGENTS%s  ' "$magenta" "$reset"
  jq -r '
    ([.agent_deck.sessions[]?, .harnesses[]?] | length) as $count
    | if $count == 0 then "no active background-agent metadata"
      else "\($count) active session\(if $count == 1 then "" else "s" end)"
      end
  ' <<<"$data"

  printf '%sTMUX%s    ' "$cyan" "$reset"
  jq -r '
    [.tmux[].windows[]] as $windows
    | [$windows[].panes[]] as $panes
    | "\(.tmux | length) sessions · \($windows | length) windows · \($panes | length) live panes"
  ' <<<"$data"

  printf '%sDISPLAY%s ' "$accent" "$reset"
  jq -r '
    [.monitors[]
      | "\(.name) \(.width)x\(.height)@\((.refresh_hz // 0) | floor) ws\(.workspace)\(if (.name | ascii_upcase | test("PHONE|HEADLESS|VIRTUAL")) then " virtual" else "" end)"]
    | join("  │  ")
  ' <<<"$data"

  if ((rows >= 14)); then
    jq -r '
      .tmux[] | "  session \(.session)  " +
        ([.windows[] | "\(.index):\(.name)[\(.panes | length)]"] | join("  "))
    ' <<<"$data"
    jq -r '
      .monitors[]
      | "  \(if .focused then "●" else "○" end) \(.name)  position \(.x),\(.y) · scale \(.scale) · workspace \(.workspace)"
    ' <<<"$data"
  fi

  if command -v tailscale >/dev/null 2>&1; then
    status=$(timeout 3s tailscale status --json 2>/dev/null || true)
    if [[ $status == \{* ]]; then
      tail_state=$(jq -r '.BackendState // "unknown"' <<<"$status")
      online=$(jq '[.Peer[]? | select(.Online == true)] | length' <<<"$status")
      total=$(jq '[.Peer[]?] | length' <<<"$status")
    fi
  fi
  printf '%sNETWORK%s tailscale %s · %s/%s peers online\n' "$green" "$reset" "$tail_state" "$online" "$total"

  mem_total=$(awk '/^MemTotal:/ {print $2}' /proc/meminfo 2>/dev/null)
  mem_available=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo 2>/dev/null)
  if [[ $mem_total =~ ^[0-9]+$ && $mem_available =~ ^[0-9]+$ && $mem_total -gt 0 ]]; then
    mem_used=$((100 * (mem_total - mem_available) / mem_total))
  else
    mem_used='?'
  fi
  load=$(cut -d' ' -f1-3 /proc/loadavg 2>/dev/null || printf unavailable)
  disk=$(timeout 2s df -P / 2>/dev/null | awk 'NR == 2 {print $5}' || true)
  printf '%sSYSTEM%s  %s · load %s · memory %s%% · root %s\n' "$yellow" "$reset" "$(date '+%H:%M:%S')" "$load" "$mem_used" "${disk:-?}"
}

render() {
  local animation_clock animation_index data=''
  animation_clock=${EPOCHREALTIME/./}
  animation_index=$((10#$animation_clock / 120000))
  orb_frame=${orb_frames[$((animation_index % ${#orb_frames[@]}))]}
  pulse_frame=${pulse_frames[$((animation_index % ${#pulse_frames[@]}))]}
  printf '%s▰ %s%s\n' "$accent" "$(label_for "$widget")" "$reset"
  [[ $widget == tasks ]] || printf '%s%s%s\n\n' "$muted" '────────────────────────────────────────────────────────────' "$reset"
  case $widget in
    tasks|overview|agents|topology|displays)
      data=$(context_json)
      "render_$widget" "$data"
      ;;
    network) render_network ;;
    system) render_system ;;
    *) printf '%sUnknown widget: %s%s\n' "$yellow" "$widget" "$reset" ;;
  esac
  if [[ $widget == tasks ]]; then
    printf '\n%s%s%s\n' "$muted" 'R restart · r replace · a add · x remove · s agents · m menu' "$reset"
  elif [[ $widget == overview ]]; then
    printf '\n%s%s%s\n' "$muted" 'R restart · x close · Alt-d focus dashboard' "$reset"
  else
    printf '\n%s%s%s\n' "$muted" 'R restart · r replace · a add · x remove · s agents · space layout · H/J/K/L swap · m menu' "$reset"
  fi
}

handle_key() {
  local key=$1
  if [[ $widget == overview ]]; then
    case $key in
      R) "$manager" refresh ;;
      x) "$manager" remove ;;
    esac
    return
  fi
  case $key in
    R) "$manager" refresh ;;
    r) "$manager" popup-choose replace ;;
    a) "$manager" popup-choose add ;;
    x) "$manager" remove ;;
    s) "$manager" popup-agents ;;
    ' ') "$manager" layout ;;
    H) "$manager" swap left ;;
    J) "$manager" swap down ;;
    K) "$manager" swap up ;;
    L) "$manager" swap right ;;
    m|'?') "$manager" popup ;;
  esac
}

interval=$(interval_for "$widget")
last_frame=''
trap 'exit 0' TERM INT HUP
while :; do
  frame=$(render)
  if [[ $frame != "$last_frame" ]]; then
    printf '\033[H%s\n\033[J' "$frame"
    last_frame=$frame
  fi
  [[ ${TMUX_WIDGET_ONCE:-0} == 1 ]] && exit 0
  key=''
  if IFS= read -rsn1 -t "$interval" key; then
    handle_key "$key"
  fi
done
