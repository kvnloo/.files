#!/usr/bin/env bash
# ============================================================================
# 03-setup-audio.sh — Deploy PipeWire Audiophile DSP Stack
#
# Run AFTER 02-deploy-dotfiles.sh (which creates symlinks for configs).
# This script installs audio packages, deploys system-level configs,
# generates WirePlumber 0.5 config, and activates all PipeWire services.
#
# Audio stack:
#   PipeWire filter-chain DSP (convolver + loudness comp + limiter)
#   WirePlumber session management (Topping DX5 bit-perfect)
#   AutoEQ impulse responses (HD800S / Monarch MKII)
#   BRIR room simulation
#   Browser bypass DSP service
#   Headphone switching script
# ============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOTFILES="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$DOTFILES/logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/setup-audio-$DATE.log"
mkdir -p "$LOG_DIR"
log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }

# Track what we deployed for the final summary
DEPLOYED=()
WARNINGS=()
SKIPPED=()

# -------------------------------------------------------
# Helper: check if a pacman package is installed
# -------------------------------------------------------
pkg_installed() { pacman -Qi "$1" &>/dev/null; }

# -------------------------------------------------------
# 1. Verify core PipeWire packages
# -------------------------------------------------------
log_section "1/14  Verify PipeWire core packages"

PIPEWIRE_PKGS=(pipewire wireplumber pipewire-alsa pipewire-pulse)
MISSING_CORE=()

for pkg in "${PIPEWIRE_PKGS[@]}"; do
    if pkg_installed "$pkg"; then
        log "$pkg is installed"
    else
        MISSING_CORE+=("$pkg")
        log_warn "$pkg is NOT installed"
    fi
done

if (( ${#MISSING_CORE[@]} > 0 )); then
    log "Installing missing core packages: ${MISSING_CORE[*]}"
    sudo pacman -S --needed --noconfirm "${MISSING_CORE[@]}"
    DEPLOYED+=("pipewire-core: ${MISSING_CORE[*]}")
else
    log "All core PipeWire packages present"
    SKIPPED+=("pipewire-core (already installed)")
fi

# -------------------------------------------------------
# 2. Install audio DSP plugins
# -------------------------------------------------------
log_section "2/14  Install audio DSP plugins"

PLUGIN_PKGS=(lsp-plugins-lv2 zam-plugins)
MISSING_PLUGINS=()

for pkg in "${PLUGIN_PKGS[@]}"; do
    if pkg_installed "$pkg"; then
        log "$pkg is installed"
    else
        MISSING_PLUGINS+=("$pkg")
    fi
done

if (( ${#MISSING_PLUGINS[@]} > 0 )); then
    log "Installing plugins: ${MISSING_PLUGINS[*]}"
    sudo pacman -S --needed --noconfirm "${MISSING_PLUGINS[@]}"
    DEPLOYED+=("plugins: ${MISSING_PLUGINS[*]}")
else
    SKIPPED+=("plugins (already installed)")
fi

# bs2b is typically in AUR
if pkg_installed ladspa-bs2b; then
    log "bs2b already installed"
    SKIPPED+=("bs2b (already installed)")
else
    if command -v paru &>/dev/null; then
        log "Installing bs2b from AUR via paru..."
        paru -S --needed --noconfirm ladspa-bs2b
        DEPLOYED+=("bs2b (AUR)")
    else
        log_warn "paru not found — install ladspa-bs2b manually: paru -S ladspa-bs2b"
        WARNINGS+=("bs2b not installed (no AUR helper)")
    fi
fi

# -------------------------------------------------------
# 3. Install audio tools
# -------------------------------------------------------
log_section "3/14  Install audio tools"

TOOL_PKGS=(pavucontrol helvum qpwgraph playerctl pulsemixer sox cava)
MISSING_TOOLS=()

for pkg in "${TOOL_PKGS[@]}"; do
    if pkg_installed "$pkg"; then
        log "$pkg is installed"
    else
        MISSING_TOOLS+=("$pkg")
    fi
done

if (( ${#MISSING_TOOLS[@]} > 0 )); then
    log "Installing tools: ${MISSING_TOOLS[*]}"
    sudo pacman -S --needed --noconfirm "${MISSING_TOOLS[@]}"
    DEPLOYED+=("tools: ${MISSING_TOOLS[*]}")
else
    SKIPPED+=("audio tools (already installed)")
fi

# Verify jq is installed (needed by browser-bypass-dsp.sh)
if ! command -v jq &>/dev/null; then
    log "Installing jq (required by browser-bypass-dsp.sh)..."
    sudo pacman -S --needed --noconfirm jq &>>"$LOG_FILE"
    DEPLOYED+=("jq")
fi

# -------------------------------------------------------
# 4. Add user to realtime-privileges group
# -------------------------------------------------------
log_section "4/14  Realtime privileges"

if groups "$USER" | grep -qw realtime; then
    log "User $USER already in realtime group"
    SKIPPED+=("realtime group (already member)")
else
    # CachyOS uses the 'realtime' group from realtime-privileges package
    if ! getent group realtime &>/dev/null; then
        log_warn "realtime group does not exist — installing realtime-privileges"
        sudo pacman -S --needed --noconfirm realtime-privileges
    fi
    sudo usermod -aG realtime "$USER"
    log "Added $USER to realtime group (effective after re-login)"
    DEPLOYED+=("realtime group membership")
    WARNINGS+=("Re-login required for realtime group to take effect")
fi

# -------------------------------------------------------
# 5. Deploy system-level RT priority limits
# -------------------------------------------------------
log_section "5/14  Deploy system RT priority limits"

LIMITS_SRC="$DOTFILES/config/system/security/limits.d/99-pipewire.conf"
LIMITS_DST="/etc/security/limits.d/99-pipewire.conf"

if [[ -f "$LIMITS_SRC" ]]; then
    if [[ -f "$LIMITS_DST" ]] && diff -q "$LIMITS_SRC" "$LIMITS_DST" &>/dev/null; then
        log "RT limits already deployed and up to date"
        SKIPPED+=("RT limits (already deployed)")
    else
        sudo cp "$LIMITS_SRC" "$LIMITS_DST"
        log "Deployed $LIMITS_DST"
        DEPLOYED+=("RT limits: $LIMITS_DST")
    fi
else
    log_error "Source file not found: $LIMITS_SRC"
    WARNINGS+=("RT limits source missing")
fi

# -------------------------------------------------------
# 6. Set LV2_PATH and LADSPA_PATH environment variables
# -------------------------------------------------------
log_section "6/14  Audio plugin environment variables"

ZSHRC_LOCAL="$HOME/.zshrc.local"
ENV_BLOCK='# Audio plugin paths (PipeWire filter-chain DSP)
export LV2_PATH="/usr/lib/lv2:/usr/local/lib/lv2:$HOME/.lv2"
export LADSPA_PATH="/usr/lib/ladspa:/usr/local/lib/ladspa"'

if [[ -f "$ZSHRC_LOCAL" ]] && grep -q "LV2_PATH" "$ZSHRC_LOCAL"; then
    log "LV2_PATH already set in $ZSHRC_LOCAL"
    SKIPPED+=("env vars (already set)")
else
    echo "" >> "$ZSHRC_LOCAL"
    echo "$ENV_BLOCK" >> "$ZSHRC_LOCAL"
    log "Added LV2_PATH and LADSPA_PATH to $ZSHRC_LOCAL"
    DEPLOYED+=("env vars: LV2_PATH, LADSPA_PATH")
fi

# Also export for the current session
export LV2_PATH="/usr/lib/lv2:/usr/local/lib/lv2:$HOME/.lv2"
export LADSPA_PATH="/usr/lib/ladspa:/usr/local/lib/ladspa"

# -------------------------------------------------------
# 7. Generate WirePlumber 0.5 config from old Lua format
# -------------------------------------------------------
log_section "7/14  Generate WirePlumber 0.5 config"

WP05_DIR="$DOTFILES/config/wireplumber/wireplumber.conf.d"
WP05_CONF="$WP05_DIR/51-topping-dx5.conf"
mkdir -p "$WP05_DIR"

if [[ -f "$WP05_CONF" ]]; then
    log "WirePlumber 0.5 config already exists: $WP05_CONF"
    SKIPPED+=("WirePlumber 0.5 config (already exists)")
else
    log "Generating WirePlumber 0.5 config from Lua source..."
    cat > "$WP05_CONF" << 'WP05EOF'
# WirePlumber 0.5 config for Topping DX5 Bit-Perfect Audio
# Generated from: main.lua.d/51-topping-dx5-bitperfect.lua
#
# WirePlumber 0.5+ uses JSON-like SPA-JSON syntax instead of Lua.
# Place in: ~/.config/wireplumber/wireplumber.conf.d/

monitor.alsa.rules = [
  {
    matches = [
      {
        node.name = "~alsa_output.usb-Topping_DX5*"
      }
    ]
    actions = {
      update-props = {
        # Session priority: DX5 is the preferred output
        priority.session        = 2000

        # Node description (shown in audio apps)
        node.description        = "Topping DX5 (Bit-Perfect)"

        # Force S32LE output — PipeWire 1.4+ uses 25-bit precision F32<->S32 path
        audio.format            = "S32LE"

        # Best-quality resampler (longest sinc filter, minimal aliasing)
        resample.quality        = 14

        # ALSA buffer: start delay for DAC clock-lock
        api.alsa.start-delay    = 12288
        api.alsa.period-size    = 1024
        api.alsa.headroom       = 0

        # Disable software volume/mixing — passthrough to hardware
        channelmix.normalize    = false

        # Never suspend: avoids reopening delays on USB DAC
        session.suspend-timeout-seconds = 0

        # Keep ALSA reservation active
        api.alsa.disable-reserve = false

        # Memory-mapped I/O and batch mode for efficiency
        api.alsa.disable-mmap   = false
        api.alsa.disable-batch  = false
      }
    }
  }
]
WP05EOF
    log "Created $WP05_CONF"
    DEPLOYED+=("WirePlumber 0.5 config: $WP05_CONF")

    # Also symlink to user config dir
    WP_USER_DIR="$HOME/.config/wireplumber/wireplumber.conf.d"
    mkdir -p "$WP_USER_DIR"
    if [[ ! -L "$WP_USER_DIR/51-topping-dx5.conf" ]]; then
        ln -sf "$WP05_CONF" "$WP_USER_DIR/51-topping-dx5.conf"
        log "Symlinked to $WP_USER_DIR/51-topping-dx5.conf"
    fi
fi

# -------------------------------------------------------
# 8. Verify AutoEQ active symlinks
# -------------------------------------------------------
log_section "8/14  Verify AutoEQ active symlinks"

AUTOEQ_DIR="$DOTFILES/config/autoeq"
SAMPLE_RATES=(44100 48000 96000 192000 384000)
AUTOEQ_OK=true

for rate in "${SAMPLE_RATES[@]}"; do
    link_path="$AUTOEQ_DIR/active_${rate}Hz.wav"
    if [[ -L "$link_path" ]]; then
        target=$(readlink "$link_path")
        log "active_${rate}Hz.wav -> $target"
    else
        log_warn "Missing active symlink: active_${rate}Hz.wav"
        AUTOEQ_OK=false
    fi
done

if $AUTOEQ_OK; then
    log "All AutoEQ active symlinks present"
    SKIPPED+=("AutoEQ symlinks (already set)")
else
    log_warn "Some AutoEQ symlinks missing — run: headphone-switch eq monarch"
    WARNINGS+=("AutoEQ symlinks incomplete — set with headphone-switch")
fi

# -------------------------------------------------------
# 9. Create systemd user service for browser-bypass-dsp
# -------------------------------------------------------
log_section "9/14  Browser bypass DSP service"

SERVICE_DIR="$HOME/.config/systemd/user"
SERVICE_FILE="$SERVICE_DIR/browser-bypass-dsp.service"
mkdir -p "$SERVICE_DIR"

if [[ -f "$SERVICE_FILE" ]]; then
    log "browser-bypass-dsp.service already exists"
    SKIPPED+=("browser-bypass service (already exists)")
else
    cat > "$SERVICE_FILE" << EOF
[Unit]
Description=Browser Bypass DSP — route browser audio directly to DAC
After=pipewire.service wireplumber.service
Requires=pipewire.service wireplumber.service

[Service]
Type=simple
ExecStart=$DOTFILES/config/pipewire/browser-bypass-dsp.sh
Restart=on-failure
RestartSec=5

[Install]
WantedBy=default.target
EOF
    log "Created $SERVICE_FILE"
    systemctl --user daemon-reload
    systemctl --user enable browser-bypass-dsp.service
    log "Enabled browser-bypass-dsp.service"
    DEPLOYED+=("systemd: browser-bypass-dsp.service")
fi

# -------------------------------------------------------
# 10. Enable and start PipeWire services
# -------------------------------------------------------
log_section "10/14  Enable PipeWire services"

PW_SERVICES=(pipewire pipewire-pulse wireplumber)

for svc in "${PW_SERVICES[@]}"; do
    if systemctl --user is-active --quiet "$svc"; then
        log "$svc is already running"
    else
        systemctl --user enable --now "$svc"
        log "Enabled and started $svc"
        DEPLOYED+=("service: $svc")
    fi
done

# Enable socket activation for auto-start on login
for sock in pipewire.socket pipewire-pulse.socket; do
    if ! systemctl --user is-enabled --quiet "$sock" 2>/dev/null; then
        systemctl --user enable "$sock"
        log "Enabled $sock for auto-activation"
    fi
done

# Start browser bypass if not running
if systemctl --user is-active --quiet browser-bypass-dsp.service; then
    log "browser-bypass-dsp is already running"
else
    systemctl --user start browser-bypass-dsp.service || \
        log_warn "browser-bypass-dsp failed to start (DAC may not be connected)"
fi

# -------------------------------------------------------
# 11. Make audio scripts executable
# -------------------------------------------------------
log_section "11/14  Make audio scripts executable"

SCRIPTS=(
    "$DOTFILES/config/pipewire/headphone-switch.sh"
    "$DOTFILES/config/pipewire/browser-bypass-dsp.sh"
    "$DOTFILES/scripts/verify-bitperfect-audio.sh"
)

for script in "${SCRIPTS[@]}"; do
    if [[ -f "$script" ]]; then
        chmod +x "$script"
        log "chmod +x $(basename "$script")"
    else
        log_warn "Script not found: $script"
    fi
done
DEPLOYED+=("executable: headphone-switch.sh, browser-bypass-dsp.sh, verify-bitperfect-audio.sh")

# -------------------------------------------------------
# 12. Create ~/.local/bin/headphone-switch symlink
# -------------------------------------------------------
log_section "12/14  Create headphone-switch symlink"

LOCAL_BIN="$HOME/.local/bin"
HS_LINK="$LOCAL_BIN/headphone-switch"
HS_TARGET="$DOTFILES/config/pipewire/headphone-switch.sh"
mkdir -p "$LOCAL_BIN"

if [[ -L "$HS_LINK" ]]; then
    log "headphone-switch symlink already exists"
    SKIPPED+=("headphone-switch symlink (already exists)")
elif [[ -f "$HS_TARGET" ]]; then
    ln -sf "$HS_TARGET" "$HS_LINK"
    log "Created $HS_LINK -> $HS_TARGET"
    DEPLOYED+=("symlink: ~/.local/bin/headphone-switch")
else
    log_error "headphone-switch.sh not found at $HS_TARGET"
    WARNINGS+=("headphone-switch symlink not created")
fi

# -------------------------------------------------------
# 13. Run verification (non-fatal)
# -------------------------------------------------------
log_section "13/14  Run audio verification"

VERIFY_SCRIPT="$DOTFILES/scripts/verify-bitperfect-audio.sh"

if [[ -x "$VERIFY_SCRIPT" ]]; then
    log "Running verify-bitperfect-audio.sh..."
    if "$VERIFY_SCRIPT" 2>&1 | tee -a "$LOG_FILE"; then
        log "Verification passed"
    else
        log_warn "Verification had issues (DAC may not be connected)"
        WARNINGS+=("Audio verification incomplete — connect DAC and re-run")
    fi
else
    log_warn "Verification script not found or not executable"
    WARNINGS+=("Verification script missing")
fi

# -------------------------------------------------------
# 14. Summary
# -------------------------------------------------------
log_section "14/14  Deployment Summary"

echo -e "${GREEN}PipeWire Audiophile DSP Stack — Setup Complete${NC}" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"

if (( ${#DEPLOYED[@]} > 0 )); then
    echo -e "${GREEN}Deployed:${NC}" | tee -a "$LOG_FILE"
    for item in "${DEPLOYED[@]}"; do
        echo -e "  ${GREEN}+${NC} $item" | tee -a "$LOG_FILE"
    done
    echo "" | tee -a "$LOG_FILE"
fi

if (( ${#SKIPPED[@]} > 0 )); then
    echo -e "${BLUE}Skipped (already configured):${NC}" | tee -a "$LOG_FILE"
    for item in "${SKIPPED[@]}"; do
        echo -e "  ${BLUE}-${NC} $item" | tee -a "$LOG_FILE"
    done
    echo "" | tee -a "$LOG_FILE"
fi

if (( ${#WARNINGS[@]} > 0 )); then
    echo -e "${YELLOW}Warnings:${NC}" | tee -a "$LOG_FILE"
    for item in "${WARNINGS[@]}"; do
        echo -e "  ${YELLOW}!${NC} $item" | tee -a "$LOG_FILE"
    done
    echo "" | tee -a "$LOG_FILE"
fi

echo -e "${BLUE}Audio stack layout:${NC}" | tee -a "$LOG_FILE"
echo "  PipeWire daemon       ~/.config/pipewire/pipewire.conf (192kHz default)" | tee -a "$LOG_FILE"
echo "  Filter-chain DSP      ~/.config/pipewire/pipewire.conf.d/10-headphone-dsp.conf" | tee -a "$LOG_FILE"
echo "  WirePlumber (0.5)     ~/.config/wireplumber/wireplumber.conf.d/51-topping-dx5.conf (active)" | tee -a "$LOG_FILE"
echo "  WirePlumber (legacy)  main.lua.d/ format deprecated on WP 0.5+ — not deployed" | tee -a "$LOG_FILE"
echo "  AutoEQ IRs            $DOTFILES/config/autoeq/active_*Hz.wav" | tee -a "$LOG_FILE"
echo "  BRIR room IRs         $DOTFILES/config/brir/BRIR_R*_True_Stereo.wav" | tee -a "$LOG_FILE"
echo "  RT limits             /etc/security/limits.d/99-pipewire.conf" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo -e "${BLUE}Commands:${NC}" | tee -a "$LOG_FILE"
echo "  headphone-switch clean      Switch to EQ-only sink (no spatial)" | tee -a "$LOG_FILE"
echo "  headphone-switch crossfeed  Switch to bs2b crossfeed sink" | tee -a "$LOG_FILE"
echo "  headphone-switch room       Switch to BRIR room simulation sink" | tee -a "$LOG_FILE"
echo "  headphone-switch eq monarch Switch EQ profile to Monarch MKII" | tee -a "$LOG_FILE"
echo "  headphone-switch eq hd800s  Switch EQ profile to HD800S" | tee -a "$LOG_FILE"
echo "" | tee -a "$LOG_FILE"
echo -e "Log file: ${BLUE}$LOG_FILE${NC}" | tee -a "$LOG_FILE"
