#!/usr/bin/env bash
# Select a static wallpaper, stop Wallpaper Engine, and derive the full desktop
# palette from the selected image.
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
WALLPAPER_DIR="$HOME/workspace/UX/background"
WALLPAPER_MODE="$ROOT/scripts/wallpaper-mode.sh"
STATE_FILE="$HOME/.cache/wallpaper-mode/state"

wallpapers() {
  find "$WALLPAPER_DIR" -type f \( -name '*.png' -o -name '*.jpg' -o -name '*.jpeg' -o -name '*.webp' \) -print0 \
    | sort -z
}

apply_theme() {
  local wallpaper=${1:?wallpaper path required}
  [[ -f $wallpaper ]] || { notify-send -u critical "Theme Switcher" "Wallpaper not found: $wallpaper"; return 1; }
  "$WALLPAPER_MODE" static "$wallpaper"
}

show_wallpaper_selector() {
  local -a files=()
  mapfile -d '' -t files < <(wallpapers)
  ((${#files[@]})) || { notify-send -u critical "Theme Switcher" "No wallpapers found"; return 1; }

  local selected
  selected=$(
    for file in "${files[@]}"; do
      printf '%s\t%s\n' "$(basename "$file")" "$file"
    done | rofi -dmenu -i -p 'Static theme' -display-columns 1
  ) || return 0
  [[ -n $selected ]] && apply_theme "${selected#*$'\t'}"
}

cycle_wallpaper() {
  local -a files=()
  mapfile -d '' -t files < <(wallpapers)
  ((${#files[@]})) || return 1

  local state current='' index next=0
  state=$(cat "$STATE_FILE" 2>/dev/null || true)
  [[ $state == static\|* ]] && current=${state#static|}
  for index in "${!files[@]}"; do
    if [[ ${files[$index]} == "$current" ]]; then
      next=$(( (index + 1) % ${#files[@]} ))
      break
    fi
  done
  apply_theme "${files[$next]}"
}

case "${1:-menu}" in
  menu)  show_wallpaper_selector ;;
  cycle) cycle_wallpaper ;;
  *)     apply_theme "$1" ;;
esac
