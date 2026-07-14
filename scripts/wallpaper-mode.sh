#!/usr/bin/env bash
# wallpaper-mode.sh — switch linux-wallpaperengine between power/quality modes
#
#   performance  kill the engine, show cached static frames via swaybg (frees GPU + RAM)
#   chill        engine at 120/120/75 fps (the everyday default)
#   aesthetic    engine synced to native refresh: 540/240/75 fps
#   off          no wallpaper at all
#   cycle        performance -> chill -> aesthetic -> performance
#   pause        SIGSTOP the engine: frame freezes, GPU drops to idle, RAM stays
#   resume       SIGCONT after pause
#   toggle       pause <-> resume
#   restore      re-apply last mode (for hyprland autostart); defaults to chill
#   status       print current mode

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
  [ -f "$wallpaper" ] || { echo "wallpaper not found: $wallpaper" >&2; return 1; }
  kill_engine
  kill_swaybg
  local screen
  for entry in "${SCREENS[@]}"; do
    IFS='|' read -r screen _ _ _ <<< "$entry"
    swaybg -o "$screen" -i "$wallpaper" -m fill >/dev/null 2>&1 &
  done
  printf 'static|%s\n' "$wallpaper" > "$STATE_FILE"
  apply_palette "$wallpaper"
  notify "Static theme — $(basename "$wallpaper")"
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
  static)      mode_static "${2:-}" ;;
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
      static\|*)   mode_static "${saved#static|}" ;;
      *)           mode_chill ;;
    esac ;;
  status) echo "$(current_mode)" ;;
  *) echo "usage: $(basename "$0") {performance|chill|aesthetic|static FILE|off|cycle|pause|resume|toggle|restore|status}" >&2; exit 1 ;;
esac
