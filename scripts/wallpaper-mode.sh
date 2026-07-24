#!/usr/bin/env bash
# wallpaper-mode.sh — manage animated/static wallpaper modes and static drawing
#
#   performance  engine off; cached scene frames shown per output
#   chill        engine at 120/120/75 fps (the everyday default)
#   aesthetic    engine synced to native refresh: 540/240/75 fps
#   static FILE [DRAW]  static image with auto/span/fill/fit/center/tile/stretch
#   draw DRAW    redraw the current static wallpaper with a different method
#   off          no wallpaper at all
#   cycle        performance -> chill -> aesthetic -> performance
#   pause/resume/toggle  freeze or resume Wallpaper Engine
#   restore      re-apply the saved mode
#   status       print the saved mode

set -u

ASSETS=/workspace/SteamLibrary/steamapps/common/wallpaper_engine/assets
WP_DIR=/workspace/SteamLibrary/steamapps/workshop/content/431960
WPE=(env SDL_AUDIODRIVER=dummy linux-wallpaperengine --silent --no-audio-processing --assets-dir "$ASSETS")
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
APPLY_PALETTE="$ROOT/scripts/apply-pywal-theme.sh"

# screen|wallpaper_id|chill_fps|native_fps
SCREENS=(
  "DP-1|2133182232|120|540"    # Forgotten Ruins — ASUS ROG PG248QP
  "DP-2|1888636115|120|240"    # Abstract Landscape — AOP 25XV2Q (portrait)
  "HDMI-A-1|2083162856|75|75"  # Hollow Knight — Dell S3222HN
)

CACHE_DIR="$HOME/.cache/wallpaper-mode"
STATE_FILE="$CACHE_DIR/state"
STATIC_FILE="$CACHE_DIR/static-wallpaper"
DRAW_FILE="$CACHE_DIR/draw-mode"
SPAN_DIR="$CACHE_DIR/span"
mkdir -p "$SPAN_DIR"
mkdir -p "$CACHE_DIR"

apply_palette() {
  local image=${1:-}
  [ -n "$image" ] && [ -s "$image" ] && "$APPLY_PALETTE" "$image" >/dev/null
}

notify() { command -v notify-send >/dev/null && notify-send -a wallpaper-mode -h string:x-dunst-stack-tag:wpmode "Wallpaper" "$1"; }

# comm is kernel-truncated to 15 chars; -x on the name avoids matching
# unrelated processes (e.g. shells) whose cmdline mentions the engine
kill_engine()  { pkill -x linux-wallpaper 2>/dev/null; }
kill_swaybg()  { pkill -x swaybg 2>/dev/null; }
engine_pids()  { pgrep -x linux-wallpaper 2>/dev/null; }

resolve_hyprland() {
  hyprctl -j monitors >/dev/null 2>&1 && return 0
  local signature wayland_display
  while IFS=$'\t' read -r signature wayland_display; do
    if HYPRLAND_INSTANCE_SIGNATURE="$signature" hyprctl -j monitors >/dev/null 2>&1; then
      export HYPRLAND_INSTANCE_SIGNATURE="$signature"
      export WAYLAND_DISPLAY="$wayland_display"
      return 0
    fi
  done < <(hyprctl -j instances 2>/dev/null | jq -r '.[] | [.instance, .wl_socket] | @tsv')
  return 1
}

monitor_geometry() {
  resolve_hyprland || return 1
  hyprctl -j monitors | jq -r '
    .[]
    | select((.disabled // false) == false)
    | (.scale // 1) as $scale
    | (.transform // 0) as $transform
    | [
        .name,
        .x,
        .y,
        ((if ($transform % 2) == 1 then .height else .width end) / $scale | floor),
        ((if ($transform % 2) == 1 then .width else .height end) / $scale | floor)
      ]
    | @tsv'
}

prepare_span() {
  local wallpaper=$1
  command -v magick >/dev/null 2>&1 || { echo "span mode requires ImageMagick" >&2; return 1; }
  command -v jq >/dev/null 2>&1 || { echo "span mode requires jq" >&2; return 1; }

  local -a geometry=()
  mapfile -t geometry < <(monitor_geometry)
  ((${#geometry[@]})) || { echo "no active monitors found" >&2; return 1; }

  local min_x=2147483647 min_y=2147483647 max_x=-2147483648 max_y=-2147483648
  local row screen x y width height
  for row in "${geometry[@]}"; do
    IFS=$'\t' read -r screen x y width height <<< "$row"
    ((x < min_x)) && min_x=$x
    ((y < min_y)) && min_y=$y
    ((x + width > max_x)) && max_x=$((x + width))
    ((y + height > max_y)) && max_y=$((y + height))
  done

  local canvas_width=$((max_x - min_x)) canvas_height=$((max_y - min_y))
  local geometry_key cache_key canvas crop
  geometry_key=$(printf '%s\n' "${geometry[@]}")
  cache_key=$(printf '%s\0%s' "$wallpaper" "$geometry_key" | sha256sum | cut -d' ' -f1)
  canvas="$SPAN_DIR/$cache_key-canvas.png"
  if [[ ! -s $canvas ]]; then
    magick "$wallpaper" -auto-orient -resize "${canvas_width}x${canvas_height}^" \
      -gravity center -extent "${canvas_width}x${canvas_height}" "$canvas"
  fi

  for row in "${geometry[@]}"; do
    IFS=$'\t' read -r screen x y width height <<< "$row"
    crop="$SPAN_DIR/$cache_key-$screen.png"
    if [[ ! -s $crop ]]; then
      magick "$canvas" -crop "${width}x${height}+$((x - min_x))+$((y - min_y))" +repage "$crop"
    fi
    printf '%s\t%s\n' "$screen" "$crop"
  done
}

auto_draw_mode() {
  local wallpaper=$1
  local dimensions width height
  dimensions=$(magick identify -format '%w %h' "$wallpaper" 2>/dev/null) || { printf 'fill'; return; }
  read -r width height <<< "$dimensions"

  local -a geometry=()
  mapfile -t geometry < <(monitor_geometry 2>/dev/null)
  ((${#geometry[@]} > 1)) || { printf 'fill'; return; }

  local min_x=2147483647 min_y=2147483647 max_x=-2147483648 max_y=-2147483648 row _ x y w h
  for row in "${geometry[@]}"; do
    IFS=$'\t' read -r _ x y w h <<< "$row"
    ((x < min_x)) && min_x=$x
    ((y < min_y)) && min_y=$y
    ((x + w > max_x)) && max_x=$((x + w))
    ((y + h > max_y)) && max_y=$((y + h))
  done
  if ((width >= max_x - min_x && height >= max_y - min_y)); then
    printf 'span'
  else
    printf 'fill'
  fi
}

start_engine() {  # $1 = fps field index: 3 for chill, 4 for native
  local idx=$1 screen id fps
  for entry in "${SCREENS[@]}"; do
    IFS='|' read -r screen id _ _ <<< "$entry"
    fps=$(echo "$entry" | cut -d'|' -f"$idx")
    "${WPE[@]}" --fps "$fps" --screen-root "$screen" --bg "$WP_DIR/$id" >/dev/null 2>&1 &
  done
}

# Render one frame of each wallpaper to a cached PNG (first performance switch only)
ensure_screenshots() {
  local screen id shot
  for entry in "${SCREENS[@]}"; do
    IFS='|' read -r screen id _ _ <<< "$entry"
    shot="$CACHE_DIR/$screen.png"
    [ -s "$shot" ] || [ -e "$shot.failed" ] && continue
    ( "${WPE[@]}" --fps 30 --screen-root "$screen" --bg "$WP_DIR/$id" \
        --screenshot "$shot" --screenshot-delay 30 >/dev/null 2>&1 & ) 2>/dev/null
    for _ in $(seq 1 60); do [ -s "$shot" ] && break; sleep 0.5; done
    pkill -x linux-wallpaper 2>/dev/null
    # mark wallpapers that can't render (e.g. segfaulting scene) to skip retries
    [ -s "$shot" ] || touch "$shot.failed"
  done
}

mode_performance() {
  kill_engine; kill_swaybg
  ensure_screenshots
  local screen shot
  for entry in "${SCREENS[@]}"; do
    IFS='|' read -r screen _ _ _ <<< "$entry"
    shot="$CACHE_DIR/$screen.png"
    if [ -s "$shot" ]; then
      swaybg -o "$screen" -i "$shot" -m fill >/dev/null 2>&1 &
    else
      swaybg -o "$screen" -c '#101010' >/dev/null 2>&1 &
    fi
  done
  apply_palette "$CACHE_DIR/DP-1.png"
  echo performance > "$STATE_FILE"
  notify "Performance mode — engine off, static frames"
}

mode_chill() {
  kill_engine; kill_swaybg
  start_engine 3
  apply_palette "$CACHE_DIR/DP-1.png"
  echo chill > "$STATE_FILE"
  notify "Chill mode — 120/120/75 fps"
}

mode_aesthetic() {
  kill_engine; kill_swaybg
  start_engine 4
  apply_palette "$CACHE_DIR/DP-1.png"
  echo aesthetic > "$STATE_FILE"
  notify "Aesthetic mode — native 540/240/75 fps"
}

mode_static() {
  local wallpaper=${1:?static mode requires a wallpaper path}
  local requested=${2:-auto}
  [[ -f $wallpaper ]] || { echo "wallpaper not found: $wallpaper" >&2; return 1; }
  case "$requested" in
    auto|span|fill|fit|center|tile|stretch) ;;
    *) echo "unknown draw mode: $requested" >&2; return 1 ;;
  esac

  local resolved=$requested
  [[ $resolved == auto ]] && resolved=$(auto_draw_mode "$wallpaper")

  local -a span_plan=()
  if [[ $resolved == span ]]; then
    mapfile -t span_plan < <(prepare_span "$wallpaper") || return 1
    ((${#span_plan[@]})) || return 1
  fi

  kill_engine
  kill_swaybg

  local row screen image _x _y _width _height
  if [[ $resolved == span ]]; then
    for row in "${span_plan[@]}"; do
      IFS=$'\t' read -r screen image <<< "$row"
      swaybg -o "$screen" -i "$image" -m stretch >/dev/null 2>&1 &
    done
  else
    while IFS=$'\t' read -r screen _x _y _width _height; do
      swaybg -o "$screen" -i "$wallpaper" -m "$resolved" >/dev/null 2>&1 &
    done < <(monitor_geometry)
  fi

  printf '%s\n' "$wallpaper" > "$STATIC_FILE"
  printf '%s\n' "$resolved" > "$DRAW_FILE"
  printf 'static|%s|%s\n' "$requested" "$wallpaper" > "$STATE_FILE"
  apply_palette "$wallpaper"
  notify "Static · $resolved — $(basename "$wallpaper")"
}

mode_off() {
  kill_engine; kill_swaybg
  echo off > "$STATE_FILE"
  notify "Wallpaper off"
}

do_pause()  { engine_pids | xargs -r kill -STOP; notify "Paused — GPU idle, frame frozen"; }
do_resume() { engine_pids | xargs -r kill -CONT; notify "Resumed"; }

current_mode() { cat "$STATE_FILE" 2>/dev/null || echo chill; }

case "${1:-status}" in
  performance) mode_performance ;;
  chill)       mode_chill ;;
  aesthetic)   mode_aesthetic ;;
  static)      mode_static "${2:-}" "${3:-auto}" ;;
  draw)
    wallpaper=$(cat "$STATIC_FILE" 2>/dev/null || true)
    [[ -n $wallpaper ]] || { echo "no static wallpaper has been selected" >&2; exit 1; }
    mode_static "$wallpaper" "${2:-auto}" ;;
  off)         mode_off ;;
  cycle)
    case "$(current_mode)" in
      performance) mode_chill ;;
      chill)       mode_aesthetic ;;
      *)           mode_performance ;;
    esac ;;
  pause)  do_pause ;;
  resume) do_resume ;;
  toggle)
    if engine_pids | head -1 | xargs -r -I{} awk '{print $3}' /proc/{}/stat | grep -q T; then
      do_resume
    else
      do_pause
    fi ;;
  restore)
    saved=$(current_mode)
    case "$saved" in
      performance) mode_performance ;;
      aesthetic)   mode_aesthetic ;;
      off)         mode_off ;;
      static\|*\|*)
        restored=${saved#static|}
        mode_static "${restored#*|}" "${restored%%|*}"
        ;;
      static\|*)   mode_static "${saved#static|}" auto ;;
      *)           mode_chill ;;
    esac ;;
  status) echo "$(current_mode)" ;;
  *) echo "usage: $(basename "$0") {performance|chill|aesthetic|static FILE [auto|span|fill|fit|center|tile|stretch]|draw MODE|off|cycle|pause|resume|toggle|restore|status}" >&2; exit 1 ;;
esac
