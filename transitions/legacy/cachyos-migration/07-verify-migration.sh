#!/bin/bash
# 07-verify-migration.sh - Comprehensive migration verification
# Verifies all aspects of the Ubuntu → CachyOS/Hyprland/NVMe migration
#
# Run after all migration steps are complete.
# 9 test categories, ~66 tests covering system, disk, GPU, desktop,
# audio, dev tools, shell, services, and system tuning.

set -uo pipefail  # no -e, we want to continue on test failures

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOTFILES="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$DOTFILES/logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/verify-migration-$DATE.log"
REPORT_FILE="$LOG_DIR/verify-report-$DATE.txt"
mkdir -p "$LOG_DIR"

TOTAL_TESTS=0; PASSED_TESTS=0; FAILED_TESTS=0; WARNING_TESTS=0
FAILURES=()
WARNINGS=()

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }

test_result() {
    local status="$1" test_name="$2" details="${3:-}"
    ((TOTAL_TESTS++))
    case "$status" in
        pass) ((PASSED_TESTS++)); echo -e "  ${GREEN}PASS${NC} $test_name" | tee -a "$LOG_FILE" ;;
        fail) ((FAILED_TESTS++)); echo -e "  ${RED}FAIL${NC} $test_name" | tee -a "$LOG_FILE"; FAILURES+=("$test_name") ;;
        warn) ((WARNING_TESTS++)); echo -e "  ${YELLOW}WARN${NC} $test_name" | tee -a "$LOG_FILE"; WARNINGS+=("$test_name") ;;
    esac
    [[ -n "$details" ]] && echo -e "         $details" | tee -a "$LOG_FILE"
}

# ===================================================================
# 1. SYSTEM BASICS
# ===================================================================
verify_system_basics() {
    log_section "1. System Basics"

    # CachyOS detected (check os-release, fallback to cachyos-release)
    if grep -qi "cachyos" /etc/os-release 2>/dev/null || [[ -f /etc/cachyos-release ]]; then
        test_result pass "CachyOS detected" "$(grep PRETTY_NAME /etc/os-release 2>/dev/null | cut -d= -f2 | tr -d '"')"
    elif [[ -f /etc/arch-release ]]; then
        test_result warn "Arch-based detected but not CachyOS" ""
    else
        test_result fail "CachyOS/Arch not detected" ""
    fi

    # Hostname
    local hostname
    hostname=$(hostnamectl hostname 2>/dev/null || hostname)
    if [[ "$hostname" == "groot" ]]; then
        test_result pass "Hostname is 'groot'" ""
    else
        test_result fail "Hostname mismatch" "Expected 'groot', got '$hostname'"
    fi

    # User
    if [[ "$(whoami)" == "kvn" ]]; then
        test_result pass "Running as user 'kvn'" ""
    else
        test_result fail "User mismatch" "Expected 'kvn', got '$(whoami)'"
    fi

    # Timezone
    local tz
    tz=$(timedatectl show -p Timezone --value 2>/dev/null || readlink /etc/localtime | sed 's|.*/zoneinfo/||')
    if [[ "$tz" == "America/Chicago" ]]; then
        test_result pass "Timezone is America/Chicago" ""
    else
        test_result fail "Timezone mismatch" "Expected America/Chicago, got '$tz'"
    fi

    # Locale
    local locale
    locale=$(locale 2>/dev/null | grep "^LANG=" | cut -d= -f2)
    if [[ "$locale" == "en_US.UTF-8" ]]; then
        test_result pass "Locale is en_US.UTF-8" ""
    else
        test_result fail "Locale mismatch" "Expected en_US.UTF-8, got '$locale'"
    fi

    # Kernel
    local kernel
    kernel=$(uname -r)
    if echo "$kernel" | grep -qi "cachyos"; then
        test_result pass "CachyOS kernel" "$kernel"
    else
        test_result warn "Non-CachyOS kernel" "$kernel (expected linux-cachyos)"
    fi

    # systemd-boot (bootctl needs root for /boot, fallback to EFI check)
    if bootctl is-installed &>/dev/null || \
       efibootmgr 2>/dev/null | grep -qi "systemd-boot"; then
        test_result pass "systemd-boot is active bootloader" ""
    else
        test_result fail "systemd-boot not detected" "Expected systemd-boot as bootloader"
    fi

    # NVMe root
    local root_dev
    root_dev=$(findmnt -n -o SOURCE / 2>/dev/null)
    if echo "$root_dev" | grep -q "nvme"; then
        test_result pass "Root mounted on NVMe" "$root_dev"
    else
        test_result fail "Root not on NVMe" "Got: $root_dev"
    fi
}

# ===================================================================
# 2. DISK & FILESYSTEM
# ===================================================================
verify_disk_filesystem() {
    log_section "2. Disk & Filesystem"

    # Root is XFS on NVMe
    local root_fs root_dev
    root_fs=$(findmnt -n -o FSTYPE / 2>/dev/null)
    root_dev=$(findmnt -n -o SOURCE / 2>/dev/null)
    if [[ "$root_fs" == "xfs" ]] && echo "$root_dev" | grep -q "nvme"; then
        test_result pass "Root (/) is XFS on NVMe" "$root_dev ($root_fs)"
    else
        test_result fail "Root filesystem unexpected" "$root_dev ($root_fs) — expected XFS on NVMe"
    fi

    # /workspace is XFS on NVMe (or part of root)
    if mountpoint -q /workspace 2>/dev/null; then
        local ws_fs ws_dev
        ws_fs=$(findmnt -n -o FSTYPE /workspace 2>/dev/null)
        ws_dev=$(findmnt -n -o SOURCE /workspace 2>/dev/null)
        if [[ "$ws_fs" == "xfs" ]] && echo "$ws_dev" | grep -q "nvme"; then
            test_result pass "/workspace is XFS on NVMe" "$ws_dev ($ws_fs)"
        else
            test_result warn "/workspace filesystem unexpected" "$ws_dev ($ws_fs)"
        fi
    elif [[ -d /workspace ]]; then
        test_result pass "/workspace exists (part of root)" "Not a separate mount"
    else
        test_result warn "/workspace directory not found" "May be under home or not yet created"
    fi

    # Swap active
    if swapon --show --noheadings 2>/dev/null | grep -q .; then
        local swap_size
        swap_size=$(swapon --show --noheadings 2>/dev/null | awk '{print $3}' | head -1)
        test_result pass "Swap is active" "Size: $swap_size"

        # Swap size >= 30GB
        local swap_bytes
        swap_bytes=$(swapon --show=SIZE --bytes --noheadings 2>/dev/null | awk '{sum+=$1} END {print sum}')
        local swap_gb=$(( ${swap_bytes:-0} / 1073741824 ))
        if [[ $swap_gb -ge 30 ]]; then
            test_result pass "Swap size >= 30GB" "${swap_gb}GB"
        else
            test_result warn "Swap size < 30GB" "${swap_gb}GB (recommended >= 30GB for 64GB RAM)"
        fi
    else
        test_result fail "No swap active" "Run 'swapon --show' to debug"
        test_result fail "Swap size check skipped" "No swap detected"
    fi

    # Root disk usage < 80%
    local root_usage
    root_usage=$(df / --output=pcent | tail -1 | tr -d '% ')
    if [[ $root_usage -lt 80 ]]; then
        test_result pass "Root disk usage < 80%" "${root_usage}% used"
    else
        test_result warn "Root disk usage high" "${root_usage}% used (threshold: 80%)"
    fi

    # EFI partition (CachyOS mounts at /boot, Ubuntu at /boot/efi)
    local efi_mount=""
    for mp in /boot /boot/efi /efi; do
        if mountpoint -q "$mp" 2>/dev/null; then
            local fs
            fs=$(findmnt -n -o FSTYPE "$mp" 2>/dev/null)
            if [[ "$fs" == "vfat" ]]; then
                efi_mount="$mp"
                break
            fi
        fi
    done
    if [[ -n "$efi_mount" ]]; then
        test_result pass "EFI partition mounted at $efi_mount (FAT32)" ""
    else
        test_result warn "EFI partition mount not detected" "Check /boot, /boot/efi, or /efi"
    fi
}

# ===================================================================
# 3. NVIDIA & DISPLAY
# ===================================================================
verify_nvidia_display() {
    log_section "3. NVIDIA & Display"

    # NVIDIA driver package (CachyOS uses pre-built modules, not DKMS)
    if pacman -Q linux-cachyos-nvidia-open &>/dev/null || \
       pacman -Q linux-cachyos-lts-nvidia-open &>/dev/null; then
        local nv_ver
        nv_ver=$(pacman -Q nvidia-utils 2>/dev/null | awk '{print $2}')
        test_result pass "CachyOS NVIDIA driver installed" "Version: $nv_ver"
    elif pacman -Q nvidia-open-dkms &>/dev/null; then
        local nv_ver
        nv_ver=$(pacman -Q nvidia-open-dkms 2>/dev/null | awk '{print $2}')
        test_result pass "nvidia-open-dkms installed" "Version: $nv_ver"
    elif pacman -Q nvidia-dkms &>/dev/null; then
        test_result warn "nvidia-dkms installed (not open)" "Consider nvidia-open-dkms"
    else
        test_result fail "No NVIDIA driver package found" "Install nvidia-utils"
    fi

    # nvidia kernel module loaded
    if lsmod | grep -q "^nvidia "; then
        test_result pass "NVIDIA kernel module loaded" ""
    else
        test_result fail "NVIDIA kernel module not loaded" "Check dkms build and modprobe"
    fi

    # 3 monitors detected (Hyprland only)
    if pgrep -x Hyprland &>/dev/null; then
        local mon_count
        mon_count=$(hyprctl monitors -j 2>/dev/null | grep -c '"id"' || echo "0")
        if [[ $mon_count -ge 3 ]]; then
            test_result pass "3+ monitors detected" "$mon_count monitors via Hyprland"
        elif [[ $mon_count -ge 1 ]]; then
            test_result warn "Only $mon_count monitor(s) detected" "Expected 3 monitors"
        else
            test_result fail "No monitors detected via Hyprland" "hyprctl monitors returned nothing"
        fi
    else
        local drm_count
        drm_count=$(ls /sys/class/drm/card*-*/status 2>/dev/null | wc -l)
        test_result warn "Hyprland not running, skipping monitor check" "$drm_count DRM connectors found"
    fi

    # NVIDIA modprobe options (modeset=1)
    local modeset_found=false
    if [[ -f /etc/modprobe.d/nvidia.conf ]]; then
        if grep -q "modeset=1" /etc/modprobe.d/nvidia.conf 2>/dev/null; then
            modeset_found=true
        fi
    fi
    if [[ -f /sys/module/nvidia_drm/parameters/modeset ]]; then
        local drm_modeset
        drm_modeset=$(cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null)
        if [[ "$drm_modeset" == "Y" ]] || [[ "$drm_modeset" == "1" ]]; then
            modeset_found=true
        fi
    fi
    if $modeset_found; then
        test_result pass "NVIDIA modeset=1 enabled" ""
    else
        test_result fail "NVIDIA modeset not enabled" "Add 'options nvidia_drm modeset=1' to modprobe.d"
    fi

    # Xwayland
    if command -v Xwayland &>/dev/null; then
        test_result pass "Xwayland available" ""
    else
        test_result warn "Xwayland not found" "Some X11 apps may not work"
    fi

    # DRM modeset enabled (kernel cmdline, module param, or modprobe.d config)
    if grep -q "nvidia_drm.modeset=1" /proc/cmdline 2>/dev/null; then
        test_result pass "DRM modeset in kernel cmdline" ""
    elif [[ -f /sys/module/nvidia_drm/parameters/modeset ]]; then
        local val
        val=$(cat /sys/module/nvidia_drm/parameters/modeset 2>/dev/null)
        if [[ "$val" == "Y" ]] || [[ "$val" == "1" ]]; then
            test_result pass "DRM modeset enabled via module parameter" ""
        else
            # sysfs may report empty — check modprobe.d as fallback
            if grep -rq "modeset=1" /etc/modprobe.d/nvidia*.conf 2>/dev/null; then
                test_result pass "DRM modeset configured via modprobe.d" ""
            else
                test_result warn "DRM modeset parameter is '$val'" "Expected Y or 1"
            fi
        fi
    elif grep -rq "modeset=1" /etc/modprobe.d/nvidia*.conf 2>/dev/null; then
        test_result pass "DRM modeset configured via modprobe.d" ""
    else
        test_result warn "Cannot verify DRM modeset" "Module parameter file not found"
    fi
}

# ===================================================================
# 4. DESKTOP ENVIRONMENT
# ===================================================================
verify_desktop_environment() {
    log_section "4. Desktop Environment"

    # Hyprland
    if command -v Hyprland &>/dev/null; then
        local hypr_ver
        hypr_ver=$(Hyprland --version 2>/dev/null | head -1 || echo "unknown")
        test_result pass "Hyprland installed" "$hypr_ver"
    else
        test_result fail "Hyprland not installed" ""
    fi

    # Waybar
    if command -v waybar &>/dev/null; then
        test_result pass "Waybar installed" ""
    else
        test_result fail "Waybar not installed" ""
    fi

    # Rofi-wayland
    if command -v rofi &>/dev/null; then
        local rofi_ver
        rofi_ver=$(rofi -version 2>/dev/null | head -1 || echo "unknown")
        if echo "$rofi_ver" | grep -qi "wayland"; then
            test_result pass "Rofi (Wayland) installed" "$rofi_ver"
        else
            test_result pass "Rofi installed" "$rofi_ver (verify it is wayland build)"
        fi
    else
        test_result fail "Rofi not installed" "Install rofi-wayland"
    fi

    # Dunst
    if command -v dunst &>/dev/null; then
        test_result pass "Dunst installed" ""
    else
        test_result fail "Dunst not installed" ""
    fi

    # Screenshot tools: grim + slurp
    local ss_ok=true
    if command -v grim &>/dev/null; then
        test_result pass "grim installed (screenshot capture)" ""
    else
        test_result fail "grim not installed" ""; ss_ok=false
    fi
    if command -v slurp &>/dev/null; then
        test_result pass "slurp installed (region selection)" ""
    else
        test_result fail "slurp not installed" ""; ss_ok=false
    fi

    # wl-clipboard
    if command -v wl-copy &>/dev/null && command -v wl-paste &>/dev/null; then
        test_result pass "wl-clipboard installed" ""
    else
        test_result fail "wl-clipboard not installed" "Need wl-copy and wl-paste"
    fi

    # hyprlock + hypridle
    if command -v hyprlock &>/dev/null; then
        test_result pass "hyprlock installed" ""
    else
        test_result fail "hyprlock not installed" ""
    fi
    if command -v hypridle &>/dev/null; then
        test_result pass "hypridle installed" ""
    else
        test_result fail "hypridle not installed" ""
    fi

    # Config files exist
    if [[ -f "$HOME/.config/hypr/hyprland.conf" ]]; then
        test_result pass "hyprland.conf exists" "$HOME/.config/hypr/hyprland.conf"
    else
        test_result fail "hyprland.conf missing" "Expected at ~/.config/hypr/hyprland.conf"
    fi

    if [[ -f "$HOME/.config/waybar/config.jsonc" ]] || [[ -f "$HOME/.config/waybar/config" ]]; then
        test_result pass "Waybar config exists" ""
    else
        test_result fail "Waybar config missing" "Expected at ~/.config/waybar/config.jsonc"
    fi
}

# ===================================================================
# 5. AUDIO STACK
# ===================================================================
verify_audio_stack() {
    log_section "5. Audio Stack (PipeWire)"

    # PipeWire service
    if systemctl --user is-active pipewire &>/dev/null; then
        test_result pass "PipeWire service active" ""
    else
        test_result fail "PipeWire service not active" "Run: systemctl --user start pipewire"
    fi

    # WirePlumber service
    if systemctl --user is-active wireplumber &>/dev/null; then
        test_result pass "WirePlumber service active" ""
    else
        test_result fail "WirePlumber service not active" "Run: systemctl --user start wireplumber"
    fi

    # pipewire-pulse (may be socket-activated, check both service and socket)
    if systemctl --user is-active pipewire-pulse &>/dev/null || \
       systemctl --user is-active pipewire-pulse.socket &>/dev/null; then
        test_result pass "pipewire-pulse active" ""
    else
        test_result fail "pipewire-pulse not active" "PulseAudio compatibility layer missing"
    fi

    # PipeWire config symlink
    local pw_conf="$HOME/.config/pipewire/pipewire.conf"
    if [[ -f "$pw_conf" ]] || [[ -L "$pw_conf" ]]; then
        test_result pass "PipeWire config exists" "$pw_conf"
    else
        test_result fail "PipeWire config missing" "Expected $pw_conf"
    fi

    # DSP filter config
    local dsp_conf="$HOME/.config/pipewire/pipewire.conf.d/10-headphone-dsp.conf"
    if [[ -f "$dsp_conf" ]] || [[ -L "$dsp_conf" ]]; then
        test_result pass "DSP filter config exists" "10-headphone-dsp.conf"
    else
        test_result warn "DSP filter config missing" "No headphone DSP: $dsp_conf"
    fi

    # WirePlumber config (Lua or 0.5 format)
    if [[ -d "$HOME/.config/wireplumber/main.lua.d" ]] || \
       [[ -d "$HOME/.config/wireplumber/wireplumber.conf.d" ]] || \
       [[ -f "$HOME/.config/wireplumber/wireplumber.conf" ]]; then
        test_result pass "WirePlumber config exists" ""
    else
        test_result warn "WirePlumber config not found" "Using system defaults"
    fi

    # lsp-plugins-lv2
    if pacman -Q lsp-plugins-lv2 &>/dev/null; then
        test_result pass "lsp-plugins-lv2 installed" ""
    else
        test_result warn "lsp-plugins-lv2 not installed" "Needed for parametric EQ DSP"
    fi

    # zam-plugins
    if pacman -Q zam-plugins &>/dev/null; then
        test_result pass "zam-plugins installed" ""
    else
        test_result warn "zam-plugins not installed" "Needed for limiter DSP"
    fi

    # User in realtime group
    if id | grep -q "realtime"; then
        test_result pass "User in realtime group" ""
    elif id | grep -q "audio"; then
        test_result warn "User in audio group but not realtime" "Add to realtime for low-latency"
    else
        test_result fail "User not in realtime or audio group" "Run: sudo usermod -aG realtime kvn"
    fi

    # headphone-switch.sh
    if [[ -x "$DOTFILES/config/pipewire/headphone-switch.sh" ]]; then
        test_result pass "headphone-switch.sh is executable" ""
    elif [[ -f "$DOTFILES/config/pipewire/headphone-switch.sh" ]]; then
        test_result warn "headphone-switch.sh exists but not executable" "Run: chmod +x"
    else
        test_result warn "headphone-switch.sh not found" ""
    fi

    # Topping DX5 detection (warn only — DAC may not be plugged in)
    if command -v wpctl &>/dev/null; then
        if wpctl status 2>/dev/null | grep -qi "topping\|DX5"; then
            test_result pass "Topping DX5 DAC detected" ""
        else
            test_result warn "Topping DX5 not detected" "DAC may not be connected"
        fi
    else
        test_result warn "wpctl not available" "Cannot check audio devices"
    fi
}

# ===================================================================
# 6. DEVELOPMENT TOOLS
# ===================================================================
verify_dev_tools() {
    log_section "6. Development Tools"

    # Git installed and configured
    if command -v git &>/dev/null; then
        local git_user
        git_user=$(git config --global user.name 2>/dev/null || echo "")
        if [[ -n "$git_user" ]]; then
            test_result pass "Git installed and configured" "user.name: $git_user"
        else
            test_result warn "Git installed but user.name not set" ""
        fi
    else
        test_result fail "Git not installed" ""
    fi

    # Node.js
    if command -v node &>/dev/null; then
        test_result pass "Node.js available" "$(node --version 2>/dev/null)"
    else
        test_result fail "Node.js not available" ""
    fi

    # npm or pnpm
    if command -v pnpm &>/dev/null; then
        test_result pass "pnpm available" "$(pnpm --version 2>/dev/null)"
    elif command -v npm &>/dev/null; then
        test_result pass "npm available" "$(npm --version 2>/dev/null)"
    else
        test_result fail "No npm/pnpm found" ""
    fi

    # Rust toolchain (rustup installs to ~/.cargo/bin which may not be in PATH)
    local rustc_cmd=""
    if command -v rustc &>/dev/null; then
        rustc_cmd="rustc"
    elif [[ -x "$HOME/.cargo/bin/rustc" ]]; then
        rustc_cmd="$HOME/.cargo/bin/rustc"
    fi
    if [[ -n "$rustc_cmd" ]]; then
        test_result pass "Rust toolchain available" "$($rustc_cmd --version 2>/dev/null)"
    else
        test_result warn "Rust toolchain not found" "Install via rustup if needed"
    fi

    # Python 3.12+
    if command -v python3 &>/dev/null; then
        local py_ver
        py_ver=$(python3 --version 2>/dev/null | awk '{print $2}')
        local py_major py_minor
        py_major=$(echo "$py_ver" | cut -d. -f1)
        py_minor=$(echo "$py_ver" | cut -d. -f2)
        if [[ "$py_major" -ge 3 ]] && [[ "$py_minor" -ge 12 ]]; then
            test_result pass "Python 3.12+ available" "Python $py_ver"
        else
            test_result warn "Python version < 3.12" "Python $py_ver"
        fi
    else
        test_result fail "Python 3 not found" ""
    fi

    # Docker
    if systemctl is-active docker &>/dev/null; then
        test_result pass "Docker service active" ""
    elif command -v docker &>/dev/null; then
        test_result warn "Docker installed but service not active" "Run: sudo systemctl enable --now docker"
    else
        test_result warn "Docker not installed" ""
    fi

    # User in docker group
    if id -nG 2>/dev/null | grep -qw docker; then
        test_result pass "User in docker group" ""
    else
        test_result warn "User not in docker group" "Run: sudo usermod -aG docker kvn"
    fi

    # VS Code or Cursor
    if command -v code &>/dev/null; then
        test_result pass "VS Code installed" ""
    elif command -v cursor &>/dev/null; then
        test_result pass "Cursor installed" ""
    else
        test_result warn "No VS Code or Cursor found" ""
    fi

    # tmux
    if command -v tmux &>/dev/null; then
        test_result pass "tmux installed" ""
    else
        test_result warn "tmux not installed" ""
    fi

    # neovim
    if command -v nvim &>/dev/null; then
        test_result pass "Neovim installed" "$(nvim --version 2>/dev/null | head -1)"
    else
        test_result warn "Neovim not installed" ""
    fi
}

# ===================================================================
# 7. SHELL & TERMINAL
# ===================================================================
verify_shell_terminal() {
    log_section "7. Shell & Terminal"

    # Zsh is default shell
    local user_shell
    user_shell=$(getent passwd "$(whoami)" | cut -d: -f7)
    if [[ "$user_shell" == *"zsh"* ]]; then
        test_result pass "Zsh is default shell" "$user_shell"
    else
        test_result fail "Zsh is not default shell" "Got: $user_shell"
    fi

    # Oh-my-zsh
    if [[ -d /usr/share/oh-my-zsh ]] || [[ -d "$HOME/.oh-my-zsh" ]]; then
        test_result pass "Oh-my-zsh exists" ""
    else
        test_result warn "Oh-my-zsh not found" "Check /usr/share/oh-my-zsh or ~/.oh-my-zsh"
    fi

    # Zsh-autosuggestions
    if [[ -d /usr/share/zsh/plugins/zsh-autosuggestions ]] || \
       [[ -d "$HOME/.oh-my-zsh/custom/plugins/zsh-autosuggestions" ]] || \
       pacman -Q zsh-autosuggestions &>/dev/null; then
        test_result pass "zsh-autosuggestions available" ""
    else
        test_result warn "zsh-autosuggestions not found" ""
    fi

    # Zsh-syntax-highlighting
    if [[ -d /usr/share/zsh/plugins/zsh-syntax-highlighting ]] || \
       [[ -d "$HOME/.oh-my-zsh/custom/plugins/zsh-syntax-highlighting" ]] || \
       pacman -Q zsh-syntax-highlighting &>/dev/null; then
        test_result pass "zsh-syntax-highlighting available" ""
    else
        test_result warn "zsh-syntax-highlighting not found" ""
    fi

    # fastfetch
    if command -v fastfetch &>/dev/null; then
        test_result pass "fastfetch installed" ""
    else
        test_result warn "fastfetch not installed" "Optional system info display"
    fi

    # .zshrc symlink
    if [[ -L "$HOME/.zshrc" ]] || [[ -L "$HOME/.config/zsh/.zshrc" ]]; then
        test_result pass ".zshrc symlink exists" ""
    elif [[ -f "$HOME/.zshrc" ]]; then
        test_result warn ".zshrc exists but is not a symlink" "Consider symlinking to dotfiles"
    else
        test_result fail ".zshrc not found" ""
    fi
}

# ===================================================================
# 8. SERVICES & NETWORK
# ===================================================================
verify_services_network() {
    log_section "8. Services & Network"

    # NetworkManager
    if systemctl is-active NetworkManager &>/dev/null; then
        test_result pass "NetworkManager active" ""
    else
        test_result fail "NetworkManager not active" ""
    fi

    # Tailscale installed
    if command -v tailscale &>/dev/null; then
        test_result pass "Tailscale installed" ""
    else
        test_result warn "Tailscale not installed" ""
    fi

    # Tailscale service
    if systemctl is-active tailscaled &>/dev/null; then
        test_result pass "Tailscale service active" ""
    elif command -v tailscale &>/dev/null; then
        test_result warn "Tailscale installed but service not running" ""
    else
        test_result warn "Tailscale service check skipped" "Not installed"
    fi

    # Ollama
    if command -v ollama &>/dev/null; then
        if systemctl is-active ollama &>/dev/null; then
            test_result pass "Ollama installed and service active" ""
        else
            test_result warn "Ollama installed but service not active" ""
        fi
    else
        test_result warn "Ollama not installed" "Optional: local LLM inference"
    fi

    # cronie
    if systemctl is-active cronie &>/dev/null; then
        test_result pass "cronie service active" ""
    else
        test_result warn "cronie not active" "Cron jobs will not run"
    fi

    # DNS resolution
    if host google.com &>/dev/null; then
        test_result pass "DNS resolution working" ""
    elif ping -c 1 -W 3 8.8.8.8 &>/dev/null; then
        test_result warn "Network works but DNS resolution failed" "Check /etc/resolv.conf"
    else
        test_result fail "DNS resolution failed" "No network connectivity"
    fi
}

# ===================================================================
# 9. SYSTEM TUNING
# ===================================================================
verify_system_tuning() {
    log_section "9. System Tuning"

    # fs.file-max >= 2097152
    local file_max
    file_max=$(sysctl -n fs.file-max 2>/dev/null || echo "0")
    if [[ $file_max -ge 2097152 ]]; then
        test_result pass "fs.file-max >= 2097152" "Value: $file_max"
    else
        test_result warn "fs.file-max too low" "Value: $file_max (recommended >= 2097152)"
    fi

    # vm.swappiness (zram-aware check)
    local swappiness
    swappiness=$(sysctl -n vm.swappiness 2>/dev/null || echo "60")
    if [[ -e /sys/block/zram0 ]]; then
        if [[ $swappiness -ge 100 ]]; then
            test_result pass "vm.swappiness >= 100 (zram)" "Value: $swappiness"
        else
            test_result warn "vm.swappiness low for zram" "Value: $swappiness (recommended >= 100 with zram)"
        fi
    else
        if [[ $swappiness -le 10 ]]; then
            test_result pass "vm.swappiness <= 10" "Value: $swappiness"
        else
            test_result warn "vm.swappiness too high" "Value: $swappiness (recommended <= 10 without zram)"
        fi
    fi

    # NVMe I/O scheduler is "none"
    local nvme_sched_ok=true nvme_checked=false
    for dev in /sys/block/nvme*; do
        if [[ -d "$dev" ]]; then
            nvme_checked=true
            local device scheduler
            device=$(basename "$dev")
            scheduler=$(cat "$dev/queue/scheduler" 2>/dev/null | grep -oP '\[\K[^\]]+' || echo "unknown")
            if [[ "$scheduler" != "none" ]]; then
                nvme_sched_ok=false
                test_result warn "NVMe $device scheduler is '$scheduler'" "Expected 'none'"
            fi
        fi
    done
    if $nvme_checked && $nvme_sched_ok; then
        test_result pass "NVMe I/O scheduler is 'none'" ""
    elif ! $nvme_checked; then
        test_result warn "No NVMe devices found in /sys/block" ""
    fi

    # inotify watches >= 524288
    local inotify_max
    inotify_max=$(sysctl -n fs.inotify.max_user_watches 2>/dev/null || echo "0")
    if [[ $inotify_max -ge 524288 ]]; then
        test_result pass "inotify max_user_watches >= 524288" "Value: $inotify_max"
    else
        test_result warn "inotify watches too low" "Value: $inotify_max (recommended >= 524288)"
    fi

    # Custom limits config
    if [[ -f /etc/security/limits.d/99-custom.conf ]] || \
       [[ -f /etc/security/limits.d/99-pipewire.conf ]]; then
        test_result pass "Custom limits config exists" ""
    else
        test_result warn "No custom limits config" "Expected /etc/security/limits.d/99-*.conf"
    fi

    # I/O scheduler udev rule
    if [[ -f /etc/udev/rules.d/60-io-scheduler.rules ]] || \
       [[ -f /etc/udev/rules.d/60-ioschedulers.rules ]]; then
        test_result pass "I/O scheduler udev rule exists" ""
    else
        test_result warn "No I/O scheduler udev rule" "Expected /etc/udev/rules.d/60-io-scheduler.rules"
    fi
}

# ===================================================================
# SUMMARY & REPORT
# ===================================================================
generate_report() {
    log_section "VERIFICATION SUMMARY"

    local success_rate=0
    if [[ $TOTAL_TESTS -gt 0 ]]; then
        success_rate=$(( (PASSED_TESTS * 100) / TOTAL_TESTS ))
    fi

    # Console summary
    echo -e "" | tee -a "$LOG_FILE"
    echo -e "  Total tests:   $TOTAL_TESTS" | tee -a "$LOG_FILE"
    echo -e "  ${GREEN}Passed:${NC}        $PASSED_TESTS" | tee -a "$LOG_FILE"
    echo -e "  ${RED}Failed:${NC}        $FAILED_TESTS" | tee -a "$LOG_FILE"
    echo -e "  ${YELLOW}Warnings:${NC}      $WARNING_TESTS" | tee -a "$LOG_FILE"
    echo -e "  Success rate:  ${success_rate}%" | tee -a "$LOG_FILE"
    echo -e "" | tee -a "$LOG_FILE"

    if [[ $success_rate -ge 90 ]]; then
        echo -e "  ${GREEN}Migration verification: EXCELLENT${NC}" | tee -a "$LOG_FILE"
    elif [[ $success_rate -ge 75 ]]; then
        echo -e "  ${YELLOW}Migration verification: GOOD (some issues)${NC}" | tee -a "$LOG_FILE"
    elif [[ $success_rate -ge 50 ]]; then
        echo -e "  ${YELLOW}Migration verification: FAIR (needs attention)${NC}" | tee -a "$LOG_FILE"
    else
        echo -e "  ${RED}Migration verification: POOR (significant issues)${NC}" | tee -a "$LOG_FILE"
    fi

    # Write report file
    {
        echo "============================================"
        echo "  Migration Verification Report"
        echo "  Generated: $(date +'%Y-%m-%d %H:%M:%S')"
        echo "  Host: $(hostname)"
        echo "  Kernel: $(uname -r)"
        echo "============================================"
        echo ""
        echo "RESULTS"
        echo "-------"
        echo "  Total tests:   $TOTAL_TESTS"
        echo "  Passed:        $PASSED_TESTS"
        echo "  Failed:        $FAILED_TESTS"
        echo "  Warnings:      $WARNING_TESTS"
        echo "  Success rate:  ${success_rate}%"
        echo ""

        if [[ ${#FAILURES[@]} -gt 0 ]]; then
            echo "FAILURES (${#FAILURES[@]})"
            echo "--------"
            for f in "${FAILURES[@]}"; do
                echo "  [FAIL] $f"
            done
            echo ""
        fi

        if [[ ${#WARNINGS[@]} -gt 0 ]]; then
            echo "WARNINGS (${#WARNINGS[@]})"
            echo "--------"
            for w in "${WARNINGS[@]}"; do
                echo "  [WARN] $w"
            done
            echo ""
        fi

        echo "RECOMMENDATIONS"
        echo "---------------"
        if [[ $FAILED_TESTS -gt 0 ]]; then
            echo "  - Address all FAIL items before considering migration complete"
        fi
        if [[ $WARNING_TESTS -gt 0 ]]; then
            echo "  - Review WARN items — some may be expected (e.g., DAC unplugged)"
        fi
        if [[ $FAILED_TESTS -eq 0 ]] && [[ $WARNING_TESTS -eq 0 ]]; then
            echo "  - All tests passed. Migration verified successfully."
        fi
        echo "  - Re-run this script after fixing issues: $0"
        echo "  - Full log: $LOG_FILE"
        echo ""
        echo "============================================"
    } > "$REPORT_FILE"

    echo -e "" | tee -a "$LOG_FILE"
    log "Full log:    $LOG_FILE"
    log "Report file: $REPORT_FILE"
}

# ===================================================================
# MAIN
# ===================================================================
main() {
    echo -e "${BLUE}"
    echo "  ┌───────────────────────────────────────────┐"
    echo "  │   CachyOS Migration Verification Suite    │"
    echo "  │   9 categories · ~66 tests                │"
    echo "  └───────────────────────────────────────────┘"
    echo -e "${NC}"
    log "Starting migration verification..."
    log "Dotfiles directory: $DOTFILES"
    echo ""

    verify_system_basics
    verify_disk_filesystem
    verify_nvidia_display
    verify_desktop_environment
    verify_audio_stack
    verify_dev_tools
    verify_shell_terminal
    verify_services_network
    verify_system_tuning

    generate_report

    # Exit code based on failures
    if [[ $FAILED_TESTS -gt 0 ]]; then
        exit 1
    fi
    exit 0
}

main "$@"
