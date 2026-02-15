#!/usr/bin/env bash
# 01-install-packages.sh - Install all packages on CachyOS
# Merged: current package lists + old repo's logging/error handling/fallback patterns
# Run AFTER first boot into CachyOS

set -euo pipefail

# Colors and logging
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOTFILES="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/install-packages-$DATE.log"
FAILED_LOG="$LOG_DIR/failed-packages-$DATE.txt"

mkdir -p "$LOG_DIR"
> "$FAILED_LOG"

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }
error_exit() { log_error "$1"; exit 1; }

# Verify we're on Arch/CachyOS
[[ -f /etc/arch-release ]] || error_exit "This script must run on Arch Linux / CachyOS"

# Counters
TOTAL_INSTALLED=0; TOTAL_FAILED=0; TOTAL_SKIPPED=0

# Install helper: try pacman first, then paru (AUR)
install_pkg() {
    local pkg="$1"
    if sudo pacman -S --needed --noconfirm "$pkg" &>>"$LOG_FILE"; then
        (( TOTAL_INSTALLED++ )) || true
    elif command -v paru &>/dev/null && paru -S --needed --noconfirm "$pkg" &>>"$LOG_FILE"; then
        (( TOTAL_INSTALLED++ )) || true
    else
        (( TOTAL_FAILED++ )) || true
        log_warn "Failed: $pkg"
        echo "$pkg" >> "$FAILED_LOG"
    fi
}

# Batch install from pacman (fast path for known-good packages)
install_pacman_batch() {
    local desc="$1"; shift
    log "$desc"
    if sudo pacman -S --needed --noconfirm "$@" &>>"$LOG_FILE"; then
        TOTAL_INSTALLED=$(( TOTAL_INSTALLED + $# ))
    else
        log_warn "Batch install had failures, retrying individually..."
        for pkg in "$@"; do
            install_pkg "$pkg"
        done
    fi
}

# Batch install from AUR via paru
install_aur_batch() {
    local desc="$1"; shift
    log "$desc"
    for pkg in "$@"; do
        if paru -S --needed --noconfirm "$pkg" &>>"$LOG_FILE"; then
            (( TOTAL_INSTALLED++ )) || true
        else
            (( TOTAL_FAILED++ )) || true
            log_warn "AUR failed: $pkg"
            echo "$pkg (AUR)" >> "$FAILED_LOG"
        fi
    done
}

# ===================================================================
# MAIN
# ===================================================================

log "Starting CachyOS package installation"
log "Log: $LOG_FILE"

# -------------------------------------------------------
# 1. System update + AUR helper
# -------------------------------------------------------
log_section "System Update & AUR Helper"
sudo pacman -Syu --noconfirm 2>>"$LOG_FILE" || log_warn "System update had warnings"

if ! command -v paru &>/dev/null; then
    log "Installing paru (AUR helper)..."
    sudo pacman -S --needed --noconfirm base-devel git || error_exit "Failed to install base-devel"
    tmpdir=$(mktemp -d)
    git clone https://aur.archlinux.org/paru.git "$tmpdir/paru" || error_exit "Failed to clone paru"
    (cd "$tmpdir/paru" && makepkg -si --noconfirm) || error_exit "Failed to build paru"
    rm -rf "$tmpdir"
    log "paru installed"
else
    log "paru already installed: $(paru --version 2>/dev/null | head -1)"
fi

# -------------------------------------------------------
# 2. Core system packages
# -------------------------------------------------------
log_section "Core System [2/9]"
install_pacman_batch "System base" \
    base-devel linux-headers \
    networkmanager \
    bluez bluez-utils \
    cups \
    udisks2 \
    fwupd \
    man-db man-pages \
    sysstat \
    cronie

# -------------------------------------------------------
# 3. NVIDIA
# -------------------------------------------------------
log_section "NVIDIA Drivers [3/9]"
install_pacman_batch "NVIDIA stack" \
    nvidia-open-dkms \
    nvidia-utils \
    lib32-nvidia-utils \
    nvidia-settings \
    opencl-nvidia \
    libva-nvidia-driver

if ! grep -q "nvidia_drm.modeset=1" /etc/kernel/cmdline 2>/dev/null; then
    log_warn "Ensure nvidia_drm.modeset=1 is in boot parameters"
    log_warn "For systemd-boot: edit /boot/loader/entries/*.conf"
fi

# -------------------------------------------------------
# 4. Hyprland + Wayland desktop
# -------------------------------------------------------
log_section "Hyprland & Wayland [4/9]"
install_pacman_batch "Wayland desktop" \
    hyprland \
    xdg-desktop-portal-hyprland \
    waybar \
    wofi \
    mako \
    swaylock swayidle swaybg \
    grim slurp \
    wl-clipboard \
    cliphist \
    wlr-randr \
    xdg-utils xdg-user-dirs \
    qt5-wayland qt6-wayland \
    polkit-gnome \
    network-manager-applet \
    brightnessctl playerctl pamixer \
    pavucontrol \
    nautilus \
    gnome-keyring seahorse

install_aur_batch "AUR Wayland extras" \
    rofi-wayland \
    hyprpaper \
    hyprlock \
    hypridle \
    swww \
    nwg-look \
    wlogout

# -------------------------------------------------------
# 5. Audio stack
# -------------------------------------------------------
log_section "Audio Stack [5/9]"
install_pacman_batch "PipeWire audio" \
    pipewire \
    pipewire-alsa \
    pipewire-pulse \
    pipewire-jack \
    wireplumber \
    alsa-utils \
    lsp-plugins-lv2 \
    zam-plugins \
    cava \
    realtime-privileges

install_aur_batch "AUR audio" \
    bs2b-ladspa \
    easyeffects

sudo usermod -aG realtime "$USER" 2>/dev/null && log "Added $USER to realtime group" || log_warn "realtime group add failed"

# -------------------------------------------------------
# 6. Development tools
# -------------------------------------------------------
log_section "Development Tools [6/9]"
install_pacman_batch "Dev tools" \
    git github-cli \
    gcc \
    cmake meson ninja make pkg-config \
    python python-pip python-pipx \
    nodejs npm \
    jdk21-openjdk \
    ruby \
    docker docker-compose docker-buildx \
    neovim vim \
    tmux \
    curl wget jq \
    ripgrep fd fzf \
    bat eza zoxide \
    btop htop \
    lazygit \
    stow \
    unzip zip p7zip \
    tree \
    openssh gnupg \
    dnsutils nmap socat

install_aur_batch "AUR dev tools" \
    visual-studio-code-bin \
    cursor-bin \
    pnpm \
    nvm

# -------------------------------------------------------
# 7. Applications
# -------------------------------------------------------
log_section "Applications [7/9]"
install_pacman_batch "User apps" \
    firefox chromium thunderbird \
    mpv gimp blender \
    libreoffice-fresh \
    obsidian steam \
    flatpak \
    ffmpeg imagemagick

install_aur_batch "AUR apps" \
    google-chrome \
    discord \
    slack-desktop \
    zoom \
    spotify \
    figma-linux-bin \
    telegram-desktop \
    alacritty \
    warp-terminal-bin \
    ollama-bin \
    tailscale

# Flatpak apps
log "Installing Flatpak apps..."
flatpak remote-add --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo 2>>"$LOG_FILE" || true
flatpak install -y flathub com.mastermindzh.tidal-hifi 2>>"$LOG_FILE" && { (( TOTAL_INSTALLED++ )) || true; } || { (( TOTAL_FAILED++ )) || true; }
flatpak install -y flathub io.github.nokse22.high-tide 2>>"$LOG_FILE" && { (( TOTAL_INSTALLED++ )) || true; } || { (( TOTAL_FAILED++ )) || true; }

# -------------------------------------------------------
# 8. Shell and terminal
# -------------------------------------------------------
log_section "Shell & Terminal [8/9]"
install_pacman_batch "Shell tools" \
    zsh \
    zsh-completions \
    zsh-syntax-highlighting \
    zsh-autosuggestions \
    cowsay lolcat \
    python-pywal \
    fastfetch \
    starship

install_aur_batch "AUR shell" oh-my-zsh-git

if [[ "$SHELL" != */zsh ]]; then
    chsh -s /usr/bin/zsh && log "Default shell set to zsh" || log_warn "Failed to set zsh as default"
fi

# -------------------------------------------------------
# 9. Fonts and theming
# -------------------------------------------------------
log_section "Fonts & Theming [9/9]"
install_pacman_batch "Fonts" \
    ttf-roboto-mono ttf-roboto-mono-nerd \
    ttf-jetbrains-mono ttf-jetbrains-mono-nerd \
    ttf-firacode-nerd ttf-iosevka-nerd \
    noto-fonts noto-fonts-cjk noto-fonts-emoji \
    papirus-icon-theme adwaita-icon-theme \
    xcursor-breeze \
    ibus ibus-table

install_aur_batch "CJK input" ibus-cangjie

# ===================================================================
# SUMMARY
# ===================================================================

log_section "Installation Summary"

log "Installed: $TOTAL_INSTALLED"
log "Failed:    $TOTAL_FAILED"
log "Skipped:   $TOTAL_SKIPPED"
log ""

if [[ $TOTAL_FAILED -gt 0 ]]; then
    log_warn "Failed packages logged to: $FAILED_LOG"
    log_warn "Contents:"
    while IFS= read -r line; do
        log_warn "  - $line"
    done < "$FAILED_LOG"
fi

# Verify key tools
log ""
log "Verification:"
for cmd in pacman paru node npm python3 rustc docker git hyprctl waybar zsh; do
    if command -v "$cmd" &>/dev/null; then
        log "  $cmd: installed"
    else
        log_warn "  $cmd: NOT FOUND"
    fi
done

log ""
log "Pacman total: $(pacman -Q 2>/dev/null | wc -l) packages"
log ""
log "NOTE: Log out and back in for group changes (realtime, docker)"
log "Next: ./migration/02-deploy-dotfiles.sh"
