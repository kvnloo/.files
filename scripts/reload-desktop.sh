#!/usr/bin/env bash
# Reload Hyprland config, restart waybar, and respawn linux-wallpaperengine on each monitor.

# Shells and automation can retain a stale Hyprland instance after a compositor
# restart. Resolve the live command socket before touching desktop processes.
if ! hyprctl -j monitors >/dev/null 2>&1; then
    while IFS=$'\t' read -r signature wayland_display; do
        if HYPRLAND_INSTANCE_SIGNATURE="$signature" hyprctl -j monitors >/dev/null 2>&1; then
            export HYPRLAND_INSTANCE_SIGNATURE="$signature"
            export WAYLAND_DISPLAY="$wayland_display"
            break
        fi
    done < <(hyprctl -j instances | jq -r '.[] | [.instance, .wl_socket] | @tsv')
fi

if ! hyprctl -j monitors >/dev/null 2>&1; then
    printf 'No live Hyprland instance found\n' >&2
    exit 1
fi

WPE_ASSETS=/workspace/SteamLibrary/steamapps/common/wallpaper_engine/assets
WP_DIR=/workspace/SteamLibrary/steamapps/workshop/content/431960
WPE=(env SDL_AUDIODRIVER=dummy linux-wallpaperengine --silent --no-audio-processing --assets-dir "$WPE_ASSETS")

hyprctl reload
killall waybar linux-wallpaperengine 2>/dev/null
sleep 0.3

# Launch through Hyprland so Waybar inherits the graphical-session environment
# and one process creates exactly one bar per connected output.
hyprctl dispatch exec waybar
"${WPE[@]}" --fps 120 --screen-root DP-1     --bg "$WP_DIR/2133182232" &
"${WPE[@]}" --fps 120 --screen-root DP-2     --bg "$WP_DIR/1888636115" &
"${WPE[@]}" --fps 75  --screen-root HDMI-A-1 --bg "$WP_DIR/2083162856" &
