#!/usr/bin/env bash
set -euo pipefail

# CachyOS Dotfiles Deployment
# Creates all symlinks from the dotfiles repo to their proper locations

DOTFILES="$HOME/workspace/.files"

echo "=== Dotfiles Deployment ==="
echo "Source: $DOTFILES"
echo ""

# Helper: create symlink with backup
link() {
    local src="$1"
    local dst="$2"
    local dst_dir
    dst_dir=$(dirname "$dst")

    mkdir -p "$dst_dir"

    if [[ -L "$dst" ]]; then
        rm "$dst"
    elif [[ -e "$dst" ]]; then
        echo "  Backing up existing: $dst -> ${dst}.bak"
        mv "$dst" "${dst}.bak"
    fi

    ln -sf "$src" "$dst"
    echo "  $dst -> $src"
}

# -------------------------------------------------------
# 1. Shell configs
# -------------------------------------------------------
echo "[1/8] Shell configuration..."
link "$DOTFILES/config/zsh/.zshrc" "$HOME/.zshrc"
link "$DOTFILES/.gitconfig" "$HOME/.gitconfig"
link "$DOTFILES/config/.tmux.conf" "$HOME/.tmux.conf"

# -------------------------------------------------------
# 2. Hyprland + Wayland desktop
# -------------------------------------------------------
echo "[2/8] Hyprland and desktop..."
link "$DOTFILES/config/hyprland/hyprland.conf" "$HOME/.config/hypr/hyprland.conf"
link "$DOTFILES/config/hyprland/hyprlock.conf" "$HOME/.config/hypr/hyprlock.conf"
link "$DOTFILES/config/hyprland/hypridle.conf" "$HOME/.config/hypr/hypridle.conf"
link "$DOTFILES/config/waybar" "$HOME/.config/waybar"
link "$DOTFILES/config/rofi" "$HOME/.config/rofi"
link "$DOTFILES/config/dunst" "$HOME/.config/dunst"

# Keep i3/picom for X11 fallback
link "$DOTFILES/config/i3" "$HOME/.config/i3"
link "$DOTFILES/config/picom" "$HOME/.config/picom"
link "$DOTFILES/config/polybar" "$HOME/.config/polybar"

# -------------------------------------------------------
# 3. PipeWire audio stack
# -------------------------------------------------------
echo "[3/8] PipeWire audio configuration..."
mkdir -p "$HOME/.config/pipewire/pipewire.conf.d"
mkdir -p "$HOME/.config/wireplumber/wireplumber.conf.d"

link "$DOTFILES/config/pipewire/pipewire.conf" "$HOME/.config/pipewire/pipewire.conf"
link "$DOTFILES/config/pipewire/pipewire.conf.d/10-headphone-dsp.conf" \
     "$HOME/.config/pipewire/pipewire.conf.d/10-headphone-dsp.conf"

# WirePlumber 0.5 format (new config deployed by setup-audio.sh)
# The old Lua config is also linked as fallback
link "$DOTFILES/config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua" \
     "$HOME/.config/wireplumber/main.lua.d/51-topping-dx5-bitperfect.lua"

# -------------------------------------------------------
# 4. Audio scripts (make executable)
# -------------------------------------------------------
echo "[4/8] Audio scripts..."
chmod +x "$DOTFILES/config/pipewire/headphone-switch.sh" 2>/dev/null || true
chmod +x "$DOTFILES/config/pipewire/browser-bypass-dsp.sh" 2>/dev/null || true
chmod +x "$DOTFILES/scripts/"*.sh 2>/dev/null || true

# Add headphone-switch to PATH
link "$DOTFILES/config/pipewire/headphone-switch.sh" "$HOME/.local/bin/headphone-switch"

# -------------------------------------------------------
# 5. Systemd user services
# -------------------------------------------------------
echo "[5/8] Systemd user services..."
mkdir -p "$HOME/.config/systemd/user"

link "$DOTFILES/config/systemd/user/easyeffects.service" \
     "$HOME/.config/systemd/user/easyeffects.service"
link "$DOTFILES/config/systemd/user/easyeffects-ir-switcher.service" \
     "$HOME/.config/systemd/user/easyeffects-ir-switcher.service"

# Browser bypass DSP service
cat > "$HOME/.config/systemd/user/browser-bypass-dsp.service" << 'EOF'
[Unit]
Description=Browser Audio DSP Bypass
After=pipewire.service wireplumber.service
Requires=pipewire.service wireplumber.service

[Service]
Type=simple
ExecStart=%h/workspace/.files/config/pipewire/browser-bypass-dsp.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF

# -------------------------------------------------------
# 6. Font configuration
# -------------------------------------------------------
echo "[6/8] Font configuration..."
if [[ -d "$DOTFILES/config/fontconfig" ]]; then
    link "$DOTFILES/config/fontconfig" "$HOME/.config/fontconfig"
fi

# Copy i3 custom fonts if they exist
if [[ -d "$DOTFILES/config/i3/.fonts" ]]; then
    mkdir -p "$HOME/.local/share/fonts"
    cp -n "$DOTFILES/config/i3/.fonts/"* "$HOME/.local/share/fonts/" 2>/dev/null || true
    fc-cache -f 2>/dev/null || true
fi

# -------------------------------------------------------
# 7. System-level configs (requires sudo)
# -------------------------------------------------------
echo "[7/8] System-level configs (sudo required)..."

# PipeWire realtime limits
if [[ -f "$DOTFILES/config/system/security/limits.d/99-pipewire.conf" ]]; then
    sudo cp "$DOTFILES/config/system/security/limits.d/99-pipewire.conf" \
         /etc/security/limits.d/99-pipewire.conf
    echo "  /etc/security/limits.d/99-pipewire.conf"
fi

# Sysctl tuning
sudo tee /etc/sysctl.d/99-custom.conf > /dev/null << 'EOF'
# Preserved from Ubuntu setup
fs.inotify.max_user_watches = 524288
vm.max_map_count = 1048576
vm.swappiness = 10
net.ipv4.conf.all.rp_filter = 2
net.ipv4.conf.default.rp_filter = 2
EOF
sudo sysctl --system > /dev/null 2>&1
echo "  /etc/sysctl.d/99-custom.conf"

# NVIDIA modprobe
sudo tee /etc/modprobe.d/nvidia.conf > /dev/null << 'EOF'
options nvidia_drm modeset=1
options nvidia NVreg_PreserveVideoMemoryAllocations=1
EOF
echo "  /etc/modprobe.d/nvidia.conf"

# -------------------------------------------------------
# 8. Wallpapers
# -------------------------------------------------------
echo "[8/8] Wallpapers..."
if [[ -d "$DOTFILES/background" ]]; then
    link "$DOTFILES/background" "$HOME/Pictures/wallpapers"
fi

echo ""
echo "=== Dotfiles Deployment Complete ==="
echo ""
echo "Deployed: shell, hyprland, audio, services, fonts, sysctl, wallpapers"
echo ""
echo "Next: ./migration/03-setup-audio.sh"
