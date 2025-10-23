#!/usr/bin/env bash
# Theme Switcher for i3/polybar/rofi/dunst
# Uses pywal to generate colors from wallpapers

WALLPAPER_DIR="$HOME/workspace/UX/background"

# Function to apply theme from wallpaper
apply_theme() {
    local wallpaper="$1"

    if [ ! -f "$wallpaper" ]; then
        notify-send "Theme Switcher" "Wallpaper not found: $wallpaper" -u critical
        return 1
    fi

    # Generate color scheme with pywal
    wal -i "$wallpaper" -n --backend colorthief

    # Update dunst colors dynamically
    update_dunst_colors

    # Reload i3 to apply new colors
    i3-msg reload

    # Reload polybar
    ~/.config/polybar/launch.sh

    # Send notification
    notify-send "Theme Switcher" "Applied theme from: $(basename "$wallpaper")"
}

# Function to update dunst configuration with pywal colors
update_dunst_colors() {
    local dunst_config="$HOME/.config/dunst/dunstrc"
    local bg=$(grep "^background=" ~/.cache/wal/colors.sh | cut -d"'" -f2)
    local fg=$(grep "^foreground=" ~/.cache/wal/colors.sh | cut -d"'" -f2)
    local accent=$(grep "^color1=" ~/.cache/wal/colors.sh | cut -d"'" -f2)

    # Update dunst colors
    sed -i "s/^    background = .*/    background = \"$bg\"/" "$dunst_config"
    sed -i "s/^    foreground = .*/    foreground = \"$fg\"/" "$dunst_config"
    sed -i "s/^    frame_color = .*/    frame_color = \"$accent\"/" "$dunst_config"

    # Restart dunst
    killall dunst
    dunst &
}

# Function to show wallpaper selector with rofi
show_wallpaper_selector() {
    local wallpapers=$(find "$WALLPAPER_DIR" -type f \( -name "*.png" -o -name "*.jpg" \))

    # Create menu with wallpaper names
    local selected=$(echo "$wallpapers" | while read -r wall; do
        echo "$(basename "$wall") | $wall"
    done | rofi -dmenu -i -p "Select Wallpaper" -format "s" | cut -d"|" -f2 | tr -d ' ')

    if [ -n "$selected" ]; then
        apply_theme "$selected"
    fi
}

# Function to cycle to next wallpaper
cycle_wallpaper() {
    local current=$(cat ~/.cache/wal/wal 2>/dev/null)
    local wallpapers=$(find "$WALLPAPER_DIR" -type f \( -name "*.png" -o -name "*.jpg" \) | sort)
    local next=""

    if [ -z "$current" ]; then
        # No current wallpaper, use first one
        next=$(echo "$wallpapers" | head -1)
    else
        # Find next wallpaper in list
        local found=false
        for wall in $wallpapers; do
            if [ "$found" = true ]; then
                next="$wall"
                break
            fi
            if [ "$wall" = "$current" ]; then
                found=true
            fi
        done

        # If we reached the end, wrap to first wallpaper
        if [ -z "$next" ]; then
            next=$(echo "$wallpapers" | head -1)
        fi
    fi

    apply_theme "$next"
}

# Main script logic
case "${1:-menu}" in
    menu)
        show_wallpaper_selector
        ;;
    cycle)
        cycle_wallpaper
        ;;
    *)
        # Direct wallpaper file path
        apply_theme "$1"
        ;;
esac
