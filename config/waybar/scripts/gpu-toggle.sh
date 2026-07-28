#!/bin/bash
# Toggles between GPU utilization and temperature display
# Called by waybar custom/gpu module

STATE_FILE="/tmp/waybar-gpu-mode"

# Toggle mode when called with "toggle"
if [[ "$1" == "toggle" ]]; then
    [[ "$(cat "$STATE_FILE" 2>/dev/null)" == "temp" ]] && echo "usage" > "$STATE_FILE" || echo "temp" > "$STATE_FILE"
    pkill -RTMIN+9 waybar
    exit 0
fi

mode=$(cat "$STATE_FILE" 2>/dev/null || echo "usage")

if [[ "$mode" == "temp" ]]; then
    temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits 2>/dev/null)
    printf '{"text": "%s°C", "tooltip": "GPU Temperature: %s°C\\nClick to show usage", "class": "temp"}\n' "$temp" "$temp"
else
    usage=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null)
    printf '{"text": "%s%%", "tooltip": "GPU Usage: %s%%\\nClick to show temperature", "class": "usage"}\n' "$usage" "$usage"
fi
