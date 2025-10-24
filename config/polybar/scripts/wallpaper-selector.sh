#!/usr/bin/env bash

# Wallpaper selector with pywal integration
# Select wallpaper from ~/Pictures/Wallpapers and auto-sync colors

WALLPAPER_DIR="${HOME}/Pictures/Wallpapers"

# Create wallpaper directory if it doesn't exist
if [ ! -d "$WALLPAPER_DIR" ]; then
    notify-send "Wallpaper Selector" "Wallpaper directory not found: $WALLPAPER_DIR"
    exit 1
fi

# Get list of wallpapers (jpg, png, jpeg)
wallpapers=$(find "$WALLPAPER_DIR" -type f \( -iname "*.jpg" -o -iname "*.png" -o -iname "*.jpeg" \) -printf "%f\n" | sort)

if [ -z "$wallpapers" ]; then
    notify-send "Wallpaper Selector" "No wallpapers found in $WALLPAPER_DIR"
    exit 1
fi

# Show wallpaper selection with rofi
chosen=$(echo "$wallpapers" | rofi -dmenu -i -p "Select Wallpaper" -theme-str 'window {width: 50%;}')

# If no wallpaper chosen, exit
if [ -z "$chosen" ]; then
    exit 0
fi

# Get full path to chosen wallpaper
wallpaper_path="$WALLPAPER_DIR/$chosen"

# Set wallpaper and generate colors with pywal
wal -i "$wallpaper_path" -n

# Reload Xresources with new pywal colors
xrdb -merge ~/.cache/wal/colors.Xresources

# Restart polybar to apply new colors
~/.config/polybar/launch.sh

notify-send "Wallpaper Changed" "Colors synced from $chosen"
