#!/usr/bin/env bash

# Sync polybar colors with current pywal theme
# Run this after changing wallpaper with pywal

# Reload Xresources to ensure pywal colors are loaded
xrdb -load ~/.cache/wal/colors.Xresources

# Restart polybar to apply new colors
~/.config/polybar/launch.sh

notify-send "Polybar Colors Synced" "Colors updated from current wallpaper"
