#!/usr/bin/env bash
# export-website-wallpaper.sh — capture Forgotten Ruins (or any Scene) for the public site
#
# Desktop path (Linux): linux-wallpaperengine parses scene.pkg and renders via OpenGL
# (Wayland layer-shell / X11). This is NOT a WebM wallpaper on the desktop — Scene runtime.
#
# Public site path: bake a muted WebM loop + poster into website/public/media/.
# Optional "live mode" (local only): document below — never ship scene.pkg to GitHub Pages.
#
# Usage:
#   ./scripts/export-website-wallpaper.sh              # DP-1 Forgotten Ruins defaults
#   ./scripts/export-website-wallpaper.sh --id 2133182232 --seconds 8 --fps 24
#   ./scripts/export-website-wallpaper.sh --poster-only
#
# Requires: linux-wallpaperengine, grim, ffmpeg, magick (ImageMagick), hyprctl, jq
set -euo pipefail

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
WP_DIR="${WE_WORKSHOP:-/workspace/SteamLibrary/steamapps/workshop/content/431960}"
MEDIA="$ROOT/website/public/media"
WORK="$ROOT/website/.capture-work"
SCREEN="${WE_SCREEN:-DP-1}"
WALLPAPER_ID="${WE_ID:-2133182232}"
SECONDS_CAP=6
FPS=24
POSTER_ONLY=0
OUT_STEM="forgotten-ruins"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit "${1:-0}"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --id) WALLPAPER_ID=$2; shift 2 ;;
    --screen) SCREEN=$2; shift 2 ;;
    --seconds) SECONDS_CAP=$2; shift 2 ;;
    --fps) FPS=$2; shift 2 ;;
    --stem) OUT_STEM=$2; shift 2 ;;
    --poster-only) POSTER_ONLY=1; shift ;;
    -h|--help) usage 0 ;;
    *) echo "unknown arg: $1" >&2; usage 1 ;;
  esac
done

WP="$WP_DIR/$WALLPAPER_ID"
[[ -d $WP ]] || { echo "workshop folder missing: $WP" >&2; exit 1; }
command -v linux-wallpaperengine >/dev/null || { echo "linux-wallpaperengine required" >&2; exit 1; }
command -v grim >/dev/null || { echo "grim required" >&2; exit 1; }
command -v ffmpeg >/dev/null || { echo "ffmpeg required" >&2; exit 1; }
command -v magick >/dev/null || { echo "ImageMagick magick required" >&2; exit 1; }

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

resolve_hyprland || { echo "Hyprland not reachable" >&2; exit 1; }

mkdir -p "$MEDIA" "$WORK/frames"
rm -rf "$WORK/frames"
mkdir -p "$WORK/frames"

PREV=$("$ROOT/scripts/wallpaper-mode.sh" status 2>/dev/null || echo chill)
CUR_WS=$(hyprctl -j activeworkspace | jq -r '.id')

cleanup() {
  hyprctl dispatch workspace "$CUR_WS" >/dev/null 2>&1 || true
  "$ROOT/scripts/wallpaper-mode.sh" restore >/dev/null 2>&1 \
    || "$ROOT/scripts/wallpaper-mode.sh" static \
         /home/kvn/workspace/UX/background/3440x1440/galaxy-spiral-purple.jpg auto >/dev/null 2>&1 \
    || true
  rm -rf "$WORK/frames"
}
trap cleanup EXIT

echo "==> starting Scene wallpaper $WALLPAPER_ID on $SCREEN (OpenGL via linux-wallpaperengine)"
"$ROOT/scripts/wallpaper-mode.sh" chill
sleep 1.2
hyprctl dispatch focusmonitor "$SCREEN" >/dev/null
# Empty workspace so grim captures wallpaper, not windows
hyprctl dispatch workspace 99 >/dev/null
sleep 0.7

# Wait until the frame looks like a painted scene (not mostly-black UI)
for _ in $(seq 1 40); do
  grim -t jpeg -q 85 -o "$SCREEN" "$WORK/probe.jpg" 2>/dev/null || true
  MEAN=$(magick "$WORK/probe.jpg" -format '%[fx:mean]' info: 2>/dev/null || echo 0)
  SZ=$(stat -c%s "$WORK/probe.jpg" 2>/dev/null || echo 0)
  # Heuristic: painted scene is brighter / larger than empty/dark UI chrome
  awk -v m="$MEAN" -v s="$SZ" 'BEGIN{exit !((m>0.25 && s>120000) || s>800000)}' && break
  sleep 0.4
done

cp "$WORK/probe.jpg" "$MEDIA/${OUT_STEM}-poster.jpg"
magick "$MEDIA/${OUT_STEM}-poster.jpg" -strip -quality 88 "$MEDIA/${OUT_STEM}-poster.jpg"
magick "$WORK/probe.jpg" -resize 1920x1080 -quality 82 "$MEDIA/${OUT_STEM}-poster.webp"
echo "==> poster: $MEDIA/${OUT_STEM}-poster.jpg"

if [[ $POSTER_ONLY -eq 1 ]]; then
  echo "poster-only done"
  exit 0
fi

FRAMES=$((SECONDS_CAP * FPS))
echo "==> capturing ${FRAMES} jpeg frames @ ${FPS}fps (~${SECONDS_CAP}s)"
DELAY=$(awk -v f="$FPS" 'BEGIN{printf "%.4f", 1/f}')
for i in $(seq -w 1 "$FRAMES"); do
  grim -t jpeg -q 82 -o "$SCREEN" "$WORK/frames/f_$i.jpg" || true
  sleep "$DELAY"
done

echo "==> encoding muted VP9 WebM (target ~2–6MB)"
# Crop top ~36px to drop noctalia panel if present
ffmpeg -y -framerate "$FPS" -pattern_type glob -i "$WORK/frames/f_*.jpg" \
  -vf "crop=iw:ih-36:0:36,scale=1600:-2" \
  -an -c:v libvpx-vp9 -b:v 2M -crf 30 -row-mt 1 -pix_fmt yuv420p \
  "$MEDIA/${OUT_STEM}.webm"

ls -lah "$MEDIA/${OUT_STEM}.webm" "$MEDIA/${OUT_STEM}-poster.jpg"
echo
echo "Done. Site assets:"
echo "  video : media/${OUT_STEM}.webm"
echo "  poster: media/${OUT_STEM}-poster.jpg|.webp"
echo
cat <<'EOF'
Notes
-----
• Desktop = Scene runtime (scene.pkg → OpenGL). Not WebM.
• Do NOT commit workshop scene.pkg / Steam trees.
• Optional live mode (local only): run linux-wallpaperengine --window, then share
  via PipeWire/OBS virtual camera into the browser — visitors cannot use this.
• Prefer this baked WebM for the public GitHub Pages export.
EOF
