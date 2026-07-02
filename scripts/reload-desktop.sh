#!/usr/bin/env bash
# Reload Hyprland config, restart waybar, and respawn linux-wallpaperengine on each monitor.

WPE_ASSETS=/workspace/SteamLibrary/steamapps/common/wallpaper_engine/assets
WP_DIR=/workspace/SteamLibrary/steamapps/workshop/content/431960
WPE=(env SDL_AUDIODRIVER=dummy linux-wallpaperengine --silent --no-audio-processing --assets-dir "$WPE_ASSETS")

hyprctl reload
killall waybar linux-wallpaperengine 2>/dev/null
sleep 0.3

waybar &
"${WPE[@]}" --fps 120 --screen-root DP-1     --bg "$WP_DIR/2133182232" &
"${WPE[@]}" --fps 120 --screen-root DP-2     --bg "$WP_DIR/1888636115" &
"${WPE[@]}" --fps 75  --screen-root HDMI-A-1 --bg "$WP_DIR/2083162856" &
