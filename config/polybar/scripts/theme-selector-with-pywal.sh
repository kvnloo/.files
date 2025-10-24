#!/usr/bin/env bash

# Polybar Theme Selector with Automatic Pywal Integration
# Automatically applies current wallpaper colors to selected theme

DIR="$HOME/.config/polybar"

# Get current wallpaper from pywal cache
CURRENT_WALLPAPER=$(cat ~/.cache/wal/wal 2>/dev/null)

if [ -z "$CURRENT_WALLPAPER" ]; then
    notify-send "Polybar Theme Selector" "⚠️ No wallpaper set with pywal. Please run: wal -i /path/to/wallpaper"
    exit 1
fi

# Get list of available themes
themes=(
    "  Material"
    "  Shades"
    "  Hack"
    "  Docky"
    "  Cuts"
    "  Shapes"
    "  Grayblocks"
    "  Blocks"
    "  Colorblocks"
    "  Forest"
)

# Launch rofi menu
chosen=$(printf '%s\n' "${themes[@]}" | rofi -dmenu -i -p "Select Polybar Theme")

# If no theme chosen, exit
if [ -z "$chosen" ]; then
    exit 0
fi

# Extract theme name (remove icon and lowercase)
theme_name=$(echo "$chosen" | sed 's/^[^A-Za-z]*//' | tr '[:upper:]' '[:lower:]' | xargs)

# Apply pywal colors to selected theme
if [ -f "$DIR/$theme_name/scripts/pywal.sh" ]; then
    notify-send "Applying Colors" "Updating $theme_name with pywal colors..."
    bash "$DIR/$theme_name/scripts/pywal.sh" "$CURRENT_WALLPAPER"
fi

# Launch selected theme
case "$theme_name" in
    material|shades|hack|docky|cuts|shapes|grayblocks|blocks|colorblocks|forest)
        ~/.config/polybar/launch.sh --$theme_name
        notify-send "Polybar Theme" "✅ Switched to $chosen with pywal colors"
        ;;
    *)
        notify-send "Polybar Theme Selector" "Unknown theme: $theme_name"
        ;;
esac
