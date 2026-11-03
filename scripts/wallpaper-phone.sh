#!/usr/bin/env bash
# Put live wallpapers from config/wallpapers/live.json on an Android phone's Wallpaper Engine app.
# usage: wallpaper-phone.sh ADB_SERIAL [WORKSHOP_ID...]   (default: every wallpaper in the list)
# Builds a missing .mpkg from the Steam copy, pushes it to Download/wallpapers and opens it in the app.
# The app then shows its preview; tap the check mark on the phone to apply one.
set -euo pipefail
ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
# Settings shared by the phone scripts (scripts/phone-setup init writes this file).
[[ -r ${XDG_CONFIG_HOME:-$HOME/.config}/phone-setup/env ]] && source "${XDG_CONFIG_HOME:-$HOME/.config}/phone-setup/env"
LIST=${LIVE_LIST:-$ROOT/config/wallpapers/live.json}; [[ -r $LIST ]] || LIST=$ROOT/config/wallpapers/live.json
SERIAL=${1:?adb serial}; shift
STORE=${WE_MPKG_STORE:-$(jq -r .mobile_store "$LIST")}; WS=${WE_WORKSHOP_DIR:-$(jq -r .workshop_dir "$LIST")}
IDS=("$@"); [[ ${#IDS[@]} -gt 0 ]] || mapfile -t IDS < <(jq -r '.wallpapers[].workshop_id' "$LIST")
mkdir -p "$STORE"
for id in "${IDS[@]}"; do
  f="$STORE/$id.mpkg"
  if [[ ! -s $f ]]; then
    uv run -q --with lz4 --with pillow python "$ROOT/scripts/wallpaper-pkg2mpkg.py" "$WS/$id" "$f" >/dev/null
  fi
  adb -s "$SERIAL" shell mkdir -p /sdcard/Download/wallpapers
  adb -s "$SERIAL" push "$f" "/sdcard/Download/wallpapers/$id.mpkg" >/dev/null
  adb -s "$SERIAL" shell am broadcast -a android.intent.action.MEDIA_SCANNER_SCAN_FILE -d "file:///sdcard/Download/wallpapers/$id.mpkg" >/dev/null
  sleep 1
  mid=$(adb -s "$SERIAL" shell content query --uri content://media/external/file --projection _id \
        --where "\"_display_name='$id.mpkg'\"" | sed -n 's/.*_id=\([0-9]*\).*/\1/p' | tail -1)
  [[ -n $mid ]] || { echo "$id: media store has no entry yet" >&2; continue; }
  adb -s "$SERIAL" shell am start -f 0x10008001 -a android.intent.action.VIEW \
    -d "content://media/external/file/$mid" -t application/octet-stream -n io.wallpaperengine.weclient/.BrowseActivity >/dev/null
  echo "$id: opened in Wallpaper Engine"
  sleep 4
done
