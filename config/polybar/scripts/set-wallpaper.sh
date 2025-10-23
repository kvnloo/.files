#!/usr/bin/env bash

# Set wallpaper and auto-sync polybar colors with pywal

if [ -z "$1" ]; then
    echo "Usage: $0 /path/to/wallpaper.jpg"
    exit 1
fi

WALLPAPER="$1"

if [ ! -f "$WALLPAPER" ]; then
    echo "Error: Wallpaper file not found: $WALLPAPER"
    exit 1
fi

# Set wallpaper with feh
feh --bg-scale "$WALLPAPER"

# Update polybar colors with pywal
~/.config/polybar/material/scripts/pywal.sh "$WALLPAPER"

# Restart polybar to apply colors
~/.config/polybar/launch.sh --material

notify-send "Wallpaper & Colors Updated" "Polybar colors synced to wallpaper"
