#!/usr/bin/env bash
set -euo pipefail

# Hyprland Desktop Setup
# Generates Hyprland, hyprlock, hypridle, and Waybar configs
# Run AFTER 02-deploy-dotfiles.sh (which creates the symlinks)

SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOTFILES="$(dirname "$SCRIPT_DIR")"

# Colors and logging
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

log()  { echo -e "${GREEN}[OK]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
err()  { echo -e "${RED}[ERR]${NC} $1"; }

echo "=== Hyprland Desktop Setup ==="
echo ""

# -------------------------------------------------------
# 1. Verify required packages
# -------------------------------------------------------
echo "[1/5] Verifying Hyprland packages..."

REQUIRED_PKGS=(
    hyprland waybar rofi-wayland dunst
    grim slurp wl-clipboard cliphist
    hyprlock hypridle swww
    python-pywal brightnessctl playerctl
    polkit-gnome
)
MISSING=()

for pkg in "${REQUIRED_PKGS[@]}"; do
    if ! pacman -Qi "$pkg" &>/dev/null; then
        MISSING+=("$pkg")
    fi
done

if [[ ${#MISSING[@]} -gt 0 ]]; then
    err "Missing packages: ${MISSING[*]}"
    echo "    Install with: paru -S --needed ${MISSING[*]}"
    exit 1
fi
log "All required packages installed"

# -------------------------------------------------------
# 2. Create config directories
# -------------------------------------------------------
echo "[2/5] Creating config directories..."
mkdir -p "$DOTFILES/config/hyprland"
mkdir -p "$DOTFILES/config/waybar"
mkdir -p "$HOME/.config/hypr"
mkdir -p "$HOME/.config/waybar"
mkdir -p "$HOME/Pictures/screenshots"
log "Directories created"

# -------------------------------------------------------
# 3. Note about symlinks
# -------------------------------------------------------
echo "[3/5] Config file generation..."
echo "    Note: 02-deploy-dotfiles.sh already created symlinks:"
echo "      ~/.config/hypr/hyprland.conf -> $DOTFILES/config/hyprland/hyprland.conf"
echo "      ~/.config/hypr/hyprlock.conf -> $DOTFILES/config/hyprland/hyprlock.conf"
echo "      ~/.config/hypr/hypridle.conf -> $DOTFILES/config/hyprland/hypridle.conf"
echo "      ~/.config/waybar/            -> $DOTFILES/config/waybar/"
echo "    This script generates the actual config files in the dotfiles repo."

# -------------------------------------------------------
# 4. Verify configs exist (they should be written already)
# -------------------------------------------------------
echo "[4/5] Verifying generated configs..."

CONFIGS=(
    "$DOTFILES/config/hyprland/hyprland.conf"
    "$DOTFILES/config/hyprland/hyprlock.conf"
    "$DOTFILES/config/hyprland/hypridle.conf"
    "$DOTFILES/config/waybar/config.jsonc"
    "$DOTFILES/config/waybar/style.css"
)

for cfg in "${CONFIGS[@]}"; do
    if [[ -f "$cfg" ]]; then
        log "Found: $(basename "$cfg")"
    else
        warn "Missing: $cfg (check dotfiles repo)"
    fi
done

# -------------------------------------------------------
# 5. Set pywal wallpaper
# -------------------------------------------------------
echo "[5/5] Setting wallpaper with pywal..."
if [[ -d "$HOME/Pictures/wallpapers" ]]; then
    # Find first image (wallpapers may be in resolution subdirectories)
    local first_img
    first_img=$(find "$HOME/Pictures/wallpapers" -type f \( -name '*.jpg' -o -name '*.png' -o -name '*.jpeg' \) | head -1)
    if [[ -n "$first_img" ]]; then
        wal -i "$first_img" -n
        log "Pywal color scheme generated from $first_img"
    else
        warn "No image files found in ~/Pictures/wallpapers/ — skipping pywal"
    fi
else
    warn "~/Pictures/wallpapers/ not found -- skipping pywal"
    echo "    Create the directory and add wallpapers, then run: wal -i ~/Pictures/wallpapers/"
fi

echo ""
echo "=== Hyprland Setup Complete ==="
echo ""
echo "Configured: hyprland.conf, hyprlock.conf, hypridle.conf, waybar"
echo ""
echo "To start Hyprland:"
echo "  1. Log out of current session"
echo "  2. Select 'Hyprland' from your display manager"
echo "  3. Or run 'Hyprland' from a TTY"
echo ""
echo "Verify monitors with: hyprctl monitors"
echo "Reload config with:   SUPER+SHIFT+C"
