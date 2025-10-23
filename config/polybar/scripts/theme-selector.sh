#!/usr/bin/env bash

# Polybar Theme Selector with Rofi
# Allows switching between all installed polybar themes

DIR="$HOME/.config/polybar"

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
    "  Panels"
    "  Pwidgets"
)

# Launch rofi menu (using default rofi theme or launcher theme if available)
if [ -f "$DIR/material/scripts/rofi/launcher.rasi" ]; then
    chosen=$(printf '%s\n' "${themes[@]}" | rofi -dmenu -i -p "Select Polybar Theme" -theme "$DIR/material/scripts/rofi/launcher.rasi")
else
    chosen=$(printf '%s\n' "${themes[@]}" | rofi -dmenu -i -p "Select Polybar Theme")
fi

# If no theme chosen, exit
if [ -z "$chosen" ]; then
    exit 0
fi

# Extract theme name (remove icon and lowercase)
theme_name=$(echo "$chosen" | sed 's/^[^A-Za-z]*//' | tr '[:upper:]' '[:lower:]' | xargs)

# Launch selected theme
case "$theme_name" in
    material)
        ~/.config/polybar/launch.sh --material
        ;;
    shades)
        ~/.config/polybar/launch.sh --shades
        ;;
    hack)
        ~/.config/polybar/launch.sh --hack
        ;;
    docky)
        ~/.config/polybar/launch.sh --docky
        ;;
    cuts)
        ~/.config/polybar/launch.sh --cuts
        ;;
    shapes)
        ~/.config/polybar/launch.sh --shapes
        ;;
    grayblocks)
        ~/.config/polybar/launch.sh --grayblocks
        ;;
    blocks)
        ~/.config/polybar/launch.sh --blocks
        ;;
    colorblocks)
        ~/.config/polybar/launch.sh --colorblocks
        ;;
    forest)
        ~/.config/polybar/launch.sh --forest
        ;;
    panels)
        ~/.config/polybar/launch.sh --panels
        ;;
    pwidgets)
        ~/.config/polybar/launch.sh --pwidgets
        ;;
    *)
        notify-send "Polybar Theme Selector" "Unknown theme: $theme_name"
        ;;
esac

notify-send "Polybar Theme Selector" "Switched to $chosen"
