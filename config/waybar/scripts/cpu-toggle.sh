#!/bin/bash
# Toggles between CPU usage and temperature display
# Called by waybar custom/cpu module

STATE_FILE="/tmp/waybar-cpu-mode"

# Toggle mode when called with "toggle"
if [[ "$1" == "toggle" ]]; then
    [[ "$(cat "$STATE_FILE" 2>/dev/null)" == "temp" ]] && echo "usage" > "$STATE_FILE" || echo "temp" > "$STATE_FILE"
    pkill -RTMIN+8 waybar
    exit 0
fi

mode=$(cat "$STATE_FILE" 2>/dev/null || echo "usage")

if [[ "$mode" == "temp" ]]; then
    temp=$(sensors 2>/dev/null | awk '/Package id 0/{gsub(/[+°C]/,"",$4); print int($4)}')
    [[ -z "$temp" ]] && temp=$(awk '{printf "%d", $1/1000}' /sys/class/thermal/thermal_zone1/temp 2>/dev/null)
    printf '{"text": "%s°C", "tooltip": "CPU Package: %s°C\\nClick to show usage", "class": "temp"}\n' "$temp" "$temp"
else
    usage=$(awk '/^cpu /{u=$2+$4; t=$2+$4+$5} END{printf "%.0f", u*100/t}' /proc/stat)
    printf '{"text": "%s%%", "tooltip": "CPU Usage: %s%%\\nClick to show temperature", "class": "usage"}\n' "$usage" "$usage"
fi
