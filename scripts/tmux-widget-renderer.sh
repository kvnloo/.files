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
    tasks|agents) printf 2 ;;
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

# Terminal adaptations of thinking-orbs' six canvas states. Each frame stays
# five cells wide so harness rows never jitter while the animation advances.
working_orb_frames=('● · ·' '◉ • ·' '• ● •' '· • ◉' '· · ●' '· • ◉' '• ● •' '◉ • ·')
searching_orb_frames=('◜ · ◝' '◟ • ◞' '◝ ● ◜' '◞ • ◟')
solving_orb_frames=('◫ ┊ ◧' '◩ ╋ ◪' '◨ ┊ ◫' '◪ ╋ ◩')
listening_orb_frames=('· ∿ ·' '• ≈ •' '● ∿ ●' '• ≈ •')
composing_orb_frames=('╱ · ╲' '─ • ─' '╲ ● ╱' '─ • ─')
shaping_orb_frames=('· ○ ·' '· △ ·' '· ◇ ·' '· □ ·' '· ◇ ·' '· △ ·')
pulse_frames=('·' '◦' '●' '◦')
orb_frame=${working_orb_frames[0]}
pulse_frame=${pulse_frames[0]}

orb_state_for() {
  local label=${1,,}
  case $label in
    *search*|*research*|*survey*|*inspect*|*investigat*|*look\ up*|*find*) printf searching ;;
    *solv*|*fix*|*debug*|*repair*|*diagnos*|*resolve*) printf solving ;;
    *listen*|*wait*|*await*|*monitor*|*watch*) printf listening ;;
    *compos*|*write*|*draft*|*document*|*summar*|*report*) printf composing ;;
    *shap*|*design*|*build*|*implement*|*refactor*|*create*|*port*) printf shaping ;;
    *) printf working ;;
  esac
}

orb_frame_for() {
  local state=${1:-working} index=${2:-0}
  case $state in
    searching) printf '%s' "${searching_orb_frames[$((index % ${#searching_orb_frames[@]}))]}" ;;
    solving) printf '%s' "${solving_orb_frames[$((index % ${#solving_orb_frames[@]}))]}" ;;
    listening) printf '%s' "${listening_orb_frames[$((index % ${#listening_orb_frames[@]}))]}" ;;
    composing) printf '%s' "${composing_orb_frames[$((index % ${#composing_orb_frames[@]}))]}" ;;
    shaping) printf '%s' "${shaping_orb_frames[$((index % ${#shaping_orb_frames[@]}))]}" ;;
    *) printf '%s' "${working_orb_frames[$((index % ${#working_orb_frames[@]}))]}" ;;
  esac
}

progress_bar() {
  local done=${1:-0} total=${2:-0} active=${3:-0} width=${4:-16}
  local fill_tone=${5:-$glass_fill} soft_tone=${6:-$glass_soft}
  local glint_tone=${7:-$glass_glint} track_tone=${8:-$glass_track}
  local filled=0 index sweep=-10 distance glyph tone
  ((total > 0)) && filled=$(((done * width + total / 2) / total))
  ((active > 0 && filled > 0)) && sweep=$((animation_index % filled))
  for ((index = 0; index < width; index++)); do
    if ((index < filled)); then
      glyph='━'
      ((index == 0)) && glyph='╺'
      ((index == filled - 1)) && glyph='╸'
      tone=$fill_tone
      distance=$((index - sweep))
      ((distance < 0)) && distance=$((-distance))
      ((active > 0 && distance == 1)) && tone=$soft_tone
      ((active > 0 && distance == 0)) && tone=$glint_tone
      printf '%s%s' "$tone" "$glyph"
    else
      glyph='┄'
      ((index == width - 1)) && glyph='╴'
      printf '%s%s' "$track_tone" "$glyph"
    fi
  done
  printf '%s' "$reset"
}

terminal_columns() {
  local columns
  columns=$(tput cols 2>/dev/null || printf 80)
  [[ $columns =~ ^[0-9]+$ ]] || columns=80
  ((columns > 0)) || columns=80
  printf '%s' "$columns"
}

clip_text() {
  local value=${1//$'\n'/ } width=${2:-0}
  if ((width <= 0)); then
    return
  elif ((${#value} > width)); then
    ((width == 1)) && printf '…' || printf '%s…' "${value:0:width-1}"
  else
    printf '%s' "$value"
  fi
}

print_clipped() {
  local tone=$1 value=$2 width=$3
  printf '%s%s%s\n' "$tone" "$(clip_text "$value" "$width")" "$reset"
}

render_agents() {
  local data=$1 columns detail continuation available summary
  columns=$(terminal_columns)
  if [[ -z $data ]]; then
    print_clipped "$yellow" 'workspace-copilot context unavailable' "$columns"
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
          summary="$a active · $b wait · $c alert · $e tracked"
          print_clipped "$text" "$summary" "$columns"
          printf '\n'
          ;;
        GROUP)
          print_clipped "$text" "$a  $b" "$columns"
          ;;
        ROW)
          local indicator indicator_color badge badge_color orb_state
          case $c in
            working|running|started)
              orb_state=$(orb_state_for "$f")
              indicator=$(orb_frame_for "$orb_state" "$animation_index")
              indicator_color=$accent
              ;;
            waiting|parked|idle)
              indicator=$(orb_frame_for listening "$animation_index")
              indicator_color=$yellow
              ;;
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
          available=$((columns - 14))
          detail=$(clip_text "${c^^}  ${d:--}" "$available")
          printf '  %s%s%s %s%s%s  %s%-4s%s  %s%s%s\n' \
            "$muted" "$a" "$reset" "$indicator_color" "$indicator" "$reset" \
            "$badge_color" "$badge" "$reset" "$text" "$detail" "$reset"
          available=$((columns - 7))
          continuation=$(clip_text "${e:--} · ${f:--}" "$available")
          printf '  %s%s└─%s %s%s%s\n' "$muted" "$b" "$reset" "$cyan" "$continuation" "$reset"
          ;;
      esac
    done
  printf '\n'
  print_clipped "$muted" 'ORB  working · searching · solving · listening · composing · shaping' "$columns"
  print_clipped "$muted" 'SOURCE  OMP live harness  DECK managed agent  s inspect / steer' "$columns"
}
render_tasks() {
  local data=$1 session rows columns overall_width phase_width max_text available
  local objective decisions runtime map_file map_tmp scroll_tmp row phase_name name_width
  local glyph summary_text summary done_count active_count pending_count total_count
  local total_rows available_rows max_scroll offset end index record kind first second third fourth fifth sixth
  local section_tone row_tone header_text
  local -a display_records
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
  [[ $rows =~ ^[0-9]+$ ]] || rows=24
  [[ $columns =~ ^[0-9]+$ ]] || columns=80
  ((columns >= 80)) && overall_width=20 || { ((columns >= 55)) && overall_width=12 || overall_width=8; }
  ((columns >= 70)) && phase_width=10 || phase_width=6
  max_text=$((columns > 6 ? columns - 6 : 1))

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

  summary=$(jq -r --arg session "$session" '
    [.tasks[]? | select(.session == $session)] as $tasks
    | [
        ($tasks | map(select(.status == "completed")) | length),
        ($tasks | map(select(.status == "in_progress")) | length),
        ($tasks | map(select(.status == "pending")) | length),
        ($tasks | length)
      ] | @tsv
  ' <<<"$data")
  IFS=$'\t' read -r done_count active_count pending_count total_count <<<"$summary"
  progress_bar "$done_count" "$total_count" "$active_count" "$overall_width"
  summary_text="  ${done_count}/${total_count} complete · ${active_count} active · ${pending_count} queued"
  available=$((columns - overall_width))
  ((available > 0)) && printf '%s\n' "$(clip_text "$summary_text" "$available")" || printf '\n'

  mapfile -t display_records < <(jq -r --arg session "$session" '
    [.tasks[]? | select(.session == $session)]
    | sort_by(.phase_order, .task_order)
    | group_by(.phase_order)
    | map({
        phase: .[0].phase,
        order: (.[0].phase_order // 0),
        done: (map(select(.status == "completed")) | length),
        active: (map(select(.status == "in_progress")) | length),
        pending: (map(select(.status == "pending")) | length),
        total: length
      })
    | map(. + {
        bucket: (
          if .active > 0 then "active"
          elif .pending > 0 then "queued"
          else "done"
          end
        )
      }) as $phases
    | [["NOW", "active"], ["UP NEXT", "queued"], ["DONE", "done"]][] as $section
    | ($phases
       | map(select(.bucket == $section[1]))
       | sort_by(if .bucket == "done" then -.order else .order end)) as $items
    | select(($items | length) > 0)
    | (["SECTION", $section[0], ($items | length), $section[1]] | @tsv),
      ($items[]
       | ["PHASE", .phase, .done, .total, .active, .pending, .bucket]
       | @tsv)
  ' <<<"$data" 2>/dev/null)

  total_rows=${#display_records[@]}
  available_rows=$((rows - 7))
  ((available_rows < 1)) && available_rows=1
  max_scroll=$((total_rows > available_rows ? total_rows - available_rows : 0))
  offset=$task_scroll
  ((offset < 0)) && offset=0
  ((offset > max_scroll)) && offset=$max_scroll
  end=$((offset + available_rows))
  ((end > total_rows)) && end=$total_rows

  runtime=${XDG_RUNTIME_DIR:-/tmp}/tmux-widget-grid-$UID
  mkdir -p "$runtime"
  map_file=$runtime/task-map-${TMUX_PANE#%}.tsv
  map_tmp=$map_file.$$
  scroll_tmp=$task_scroll_max_file.$$
  : >"$map_tmp"
  chmod 600 "$map_tmp"
  printf '%s\n' "$max_scroll" >"$scroll_tmp"
  chmod 600 "$scroll_tmp"
  mv -f "$scroll_tmp" "$task_scroll_max_file"

  if ((max_scroll > 0)); then
    header_text="TASK GROUPS · click row · wheel/j/k scroll · $((offset + 1))-${end}/${total_rows}"
  else
    header_text='TASK GROUPS · click a row for subtasks'
  fi
  print_clipped "$cyan" "$header_text" "$columns"
  row=6

  for ((index = offset; index < end; index++)); do
    record=${display_records[index]}
    IFS=$'\t' read -r kind first second third fourth fifth sixth <<<"$record"
    case $kind in
      SECTION)
        case $third in
          active) section_tone=$accent ;;
          done) section_tone=$muted ;;
          *) section_tone=$text ;;
        esac
        printf '%s%s · %s%s\n' "$section_tone" "$first" "$second" "$reset"
        ;;
      PHASE)
        phase_name=$first
        name_width=$((columns - phase_width - 13))
        ((name_width < 1)) && name_width=1
        ((${#phase_name} > name_width)) && phase_name="${phase_name:0:name_width-1}…"
        case $sixth in
          active)
            glyph='▶'
            row_tone=$glass_glint
            ;;
          done)
            ((second == third)) && glyph='✓' || glyph='–'
            row_tone=$muted
            ;;
          *)
            glyph='○'
            row_tone=$text
            ;;
        esac
        printf '%s%s%s %-*s ' "$row_tone" "$glyph" "$reset" "$name_width" "$phase_name"
        if [[ $sixth == done ]]; then
          progress_bar "$second" "$third" 0 "$phase_width" "$muted" "$muted" "$muted" "$glass_track"
        else
          progress_bar "$second" "$third" "$fourth" "$phase_width"
        fi
        printf ' %s%s/%s%s\n' "$row_tone" "$second" "$third" "$reset"
        printf '%s\t%s\t%s\n' "$row" "$session" "$first" >>"$map_tmp"
        ;;
    esac
    row=$((row + 1))
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
  local animation_clock animation_index data='' columns separator footer
  animation_clock=${EPOCHREALTIME/./}
  animation_index=$((10#$animation_clock / 120000))
  orb_frame=${working_orb_frames[$((animation_index % ${#working_orb_frames[@]}))]}
  pulse_frame=${pulse_frames[$((animation_index % ${#pulse_frames[@]}))]}
  columns=$(terminal_columns)
  printf '%s▰ %s%s\n' "$accent" "$(label_for "$widget")" "$reset"
  if [[ $widget != tasks ]]; then
    separator=$(clip_text '────────────────────────────────────────────────────────────' "$columns")
    printf '%s%s%s\n\n' "$muted" "$separator" "$reset"
  fi
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
    footer='wheel/j/k scroll · g/G top/bottom · R restart · r replace · s agents · m menu'
  elif [[ $widget == overview ]]; then
    footer='R restart · x close · Alt-d focus dashboard'
  else
    footer='R restart · r replace · a add · x remove · s agents · space layout · H/J/K/L swap · m menu'
  fi
  printf '\n'
  print_clipped "$muted" "$footer" "$columns"
}

task_scroll=0
task_scroll_runtime=${XDG_RUNTIME_DIR:-/tmp}/tmux-widget-grid-$UID
task_scroll_max_file=$task_scroll_runtime/task-scroll-max-${TMUX_PANE#%}

handle_key() {
  local key=$1 max=0
  if [[ $widget == tasks ]]; then
    [[ -r $task_scroll_max_file ]] && max=$(<"$task_scroll_max_file")
    [[ $max =~ ^[0-9]+$ ]] || max=0
    case $key in
      j) ((task_scroll < max)) && task_scroll=$((task_scroll + 1)); return ;;
      k) ((task_scroll > 0)) && task_scroll=$((task_scroll - 1)); return ;;
      d) task_scroll=$((task_scroll + 5)); ((task_scroll > max)) && task_scroll=$max; return ;;
      u) task_scroll=$((task_scroll - 5)); ((task_scroll < 0)) && task_scroll=0; return ;;
      g) task_scroll=0; return ;;
      G) task_scroll=$max; return ;;
    esac
  fi
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
    printf '\033[2J\033[H%s' "$frame"
    last_frame=$frame
  fi
  [[ ${TMUX_WIDGET_ONCE:-0} == 1 ]] && exit 0
  key=''
  if IFS= read -rsn1 -t "$interval" key; then
    handle_key "$key"
  fi
done
