#!/usr/bin/env bash
# Route browser/comms audio directly to DX5, bypassing DSP filter chain.
# Uses pw-metadata to override stream targets — the only method WirePlumber
# doesn't fight back on.

set -euo pipefail

DX5_NODE="alsa_output.usb-Topping_DX5-00.analog-stereo"
BYPASS_APPS="Google Chrome|Chromium|Firefox|Brave|Discord|Slack|Telegram Desktop|ZOOM VoiceEngine"
CHECK_INTERVAL=2

get_dx5_id() {
  timeout 2 pw-dump 2>/dev/null \
    | jq -r ".[] | select(.info.props[\"node.name\"]? == \"$DX5_NODE\") | .id" 2>/dev/null \
    | head -1
}

reroute_browsers() {
  local dx5_id
  dx5_id=$(get_dx5_id)
  [ -z "$dx5_id" ] && return

  timeout 2 pw-dump 2>/dev/null | jq -r "
    .[] | select(
      .info.props[\"media.class\"]? == \"Stream/Output/Audio\" and
      ((.info.props[\"application.name\"]? // \"\") | test(\"$BYPASS_APPS\"))
    ) | .id" 2>/dev/null | while read -r stream_id; do
    # Set target via metadata (survives WirePlumber policy)
    timeout 1 pw-metadata -n default "$stream_id" target.node "$dx5_id" >/dev/null 2>&1 || true
  done
}

# Poll loop — simple, reliable, low overhead
while true; do
  reroute_browsers
  sleep "$CHECK_INTERVAL"
done
