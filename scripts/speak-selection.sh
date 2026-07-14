#!/usr/bin/env bash
# speak-selection.sh — read the selected text aloud via the local Kokoro TTS server.
# Toggle behavior: if already speaking, pressing again stops playback.
# Usage: speak-selection.sh [stop]   (env: KOKORO_VOICE, KOKORO_SPEED)

set -u

PORT=8880
VOICE="${KOKORO_VOICE:-af_heart}"
SPEED="${KOKORO_SPEED:-1.1}"
PIDFILE="${XDG_RUNTIME_DIR:-/tmp}/speak-selection.pid"

stop_playback() {
  if [ -f "$PIDFILE" ]; then
    pkill -P "$(cat "$PIDFILE")" 2>/dev/null
    kill "$(cat "$PIDFILE")" 2>/dev/null
    rm -f "$PIDFILE"
    return 0
  fi
  return 1
}

# Toggle: a second press (or explicit "stop") kills current playback
if [ "${1:-}" = "stop" ]; then stop_playback; exit 0; fi
if stop_playback; then exit 0; fi

# Primary selection first (what's highlighted), clipboard as fallback
TEXT=$(wl-paste -p 2>/dev/null || true)
[ -z "$TEXT" ] && TEXT=$(wl-paste 2>/dev/null || true)
if [ -z "$TEXT" ]; then
  notify-send -t 2000 "TTS" "Nothing selected"
  exit 0
fi

if ! curl -sf -m 2 "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
  notify-send -t 4000 "TTS" "Kokoro server not running — start with: kokoro start"
  exit 1
fi

# Stream: audio starts playing while the rest is still generating
(
  echo $$ >"$PIDFILE"
  jq -n --arg text "$TEXT" --arg voice "$VOICE" --argjson speed "$SPEED" \
    '{model:"kokoro", input:$text, voice:$voice, speed:$speed, response_format:"mp3"}' |
  curl -sN -X POST "http://127.0.0.1:$PORT/v1/audio/speech" \
    -H "Content-Type: application/json" -d @- |
  mpv --no-terminal --no-video --volume=100 -
  rm -f "$PIDFILE"
) &
