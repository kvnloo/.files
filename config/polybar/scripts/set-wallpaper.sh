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

# Generate colors from wallpaper using pywal
wal -i "$WALLPAPER" -n

# Reload Xresources with new pywal colors
xrdb -merge ~/.cache/wal/colors.Xresources

# Restart polybar to apply new colors
~/.config/polybar/launch.sh

notify-send "Wallpaper & Colors Updated" "Polybar colors synced to wallpaper"
