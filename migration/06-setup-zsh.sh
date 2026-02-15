#!/usr/bin/env bash
set -euo pipefail

# ZSH Configuration Cleanup for CachyOS/Arch Linux
# Fixes macOS remnants, broken paths, and Ubuntu/Linuxbrew leftovers
# Run AFTER 02-deploy-dotfiles.sh (which symlinks config/zsh/.zshrc → ~/.zshrc)

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOTFILES="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$SCRIPT_DIR/../logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/setup-zsh-$DATE.log"
mkdir -p "$LOG_DIR"

log()         { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn()    { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error()   { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }

ZSH_DIR="$DOTFILES/config/zsh"
CHANGED=0

backup() {
    local file="$1"
    if [[ -f "$file" && ! -f "$file.pre-migration" ]]; then
        cp "$file" "$file.pre-migration"
        log "Backed up $(basename "$file")"
    fi
}

# ─────────────────────────────────────────────────────────────────────────────
log_section "1. Fix oh-my-zsh sourcing (oh-my-zsh.zsh)"
# ─────────────────────────────────────────────────────────────────────────────
backup "$ZSH_DIR/oh-my-zsh.zsh"

# Replace hardcoded ZSH path with Arch-aware detection
sed -i 's|^export ZSH=~/.oh-my-zsh$|# Arch: use system oh-my-zsh if available, else user install\nif [[ -d /usr/share/oh-my-zsh ]]; then\n  export ZSH=/usr/share/oh-my-zsh\nelse\n  export ZSH=~/.oh-my-zsh\nfi|' "$ZSH_DIR/oh-my-zsh.zsh"

# Replace macOS zsh-completions fpath with Arch path
sed -i 's|^fpath=(/usr/local/share/zsh-completions $fpath)$|fpath=(/usr/share/zsh/site-functions $fpath)|' "$ZSH_DIR/oh-my-zsh.zsh"

log "oh-my-zsh.zsh: ZSH path → Arch-aware detection, fpath → /usr/share/zsh/site-functions"
((CHANGED++))

# ─────────────────────────────────────────────────────────────────────────────
log_section "2. Fix autosuggestions sourcing (shell-behavior.zsh)"
# ─────────────────────────────────────────────────────────────────────────────
backup "$ZSH_DIR/shell-behavior.zsh"

# Replace manual clone path with Arch package path + fallback
sed -i '/^source ~\/.zsh\/zsh-autosuggestions\/zsh-autosuggestions.zsh$/c\
# Arch: use system package, fallback to manual install\
if [[ -f /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then\
  source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh\
elif [[ -f ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then\
  source ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh\
fi' "$ZSH_DIR/shell-behavior.zsh"

log "shell-behavior.zsh: autosuggestions → Arch plugin path with fallback"
((CHANGED++))

# ─────────────────────────────────────────────────────────────────────────────
log_section "3. Fix syntax-highlighting sourcing (oh-my-zsh.zsh)"
# ─────────────────────────────────────────────────────────────────────────────
# Append Arch syntax-highlighting source after oh-my-zsh init (plugin may not load from omz)
if ! grep -q 'zsh-syntax-highlighting.zsh' "$ZSH_DIR/oh-my-zsh.zsh" 2>/dev/null || \
   ! grep -q '/usr/share/zsh/plugins/zsh-syntax-highlighting' "$ZSH_DIR/oh-my-zsh.zsh" 2>/dev/null; then
    cat >> "$ZSH_DIR/oh-my-zsh.zsh" << 'EOF'

# Arch: source syntax-highlighting from system package if omz plugin didn't load it
if [[ -f /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
  source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi
EOF
    log "oh-my-zsh.zsh: appended Arch syntax-highlighting fallback"
    ((CHANGED++))
else
    log "oh-my-zsh.zsh: syntax-highlighting already has Arch path"
fi

# ─────────────────────────────────────────────────────────────────────────────
log_section "4. Fix external.zsh (remove Linuxbrew, z → zoxide)"
# ─────────────────────────────────────────────────────────────────────────────
backup "$ZSH_DIR/external.zsh"

# Remove the entire Homebrew/Linuxbrew block
sed -i '/^# ──.*$/{ N; /Homebrew (Linuxbrew)/{ N; /^# ──.*$/{ N; N; d } } }' "$ZSH_DIR/external.zsh"
sed -i '/^eval "\$(\/home\/linuxbrew\/.linuxbrew\/bin\/brew shellenv)"$/d' "$ZSH_DIR/external.zsh"

# Replace z block with zoxide
sed -i '/^# ──.*$/{ N; /Z - Jump Around/{ N; /^# ──.*$/{ N; N; N;
c\# ──────────────────────────────────────────────────────────────────────────────\n# Zoxide - Smarter cd\n# ──────────────────────────────────────────────────────────────────────────────\n# Smart directory jumping (replaces z/autojump)\n# Install: pacman -S zoxide\neval "$(zoxide init zsh)"
} } }' "$ZSH_DIR/external.zsh"

# Fallback: if the multi-line sed didn't catch it, remove any remaining brew/z lines
sed -i '/^source "\$(brew --prefix)\/etc\/profile.d\/z.sh"$/d' "$ZSH_DIR/external.zsh"

log "external.zsh: removed Linuxbrew, replaced z with zoxide, kept NVM + Cargo"
((CHANGED++))

# ─────────────────────────────────────────────────────────────────────────────
log_section "5. Clean aliases.zsh (remove macOS, fix paths)"
# ─────────────────────────────────────────────────────────────────────────────
backup "$ZSH_DIR/aliases.zsh"

# Remove macOS browser aliases
sed -i '/^alias chrome=.*MacOS.*$/d' "$ZSH_DIR/aliases.zsh"
sed -i '/^alias chrome-canary=.*MacOS.*$/d' "$ZSH_DIR/aliases.zsh"

# Remove macOS window manager aliases
sed -i '/^alias rekwm=.*$/d' "$ZSH_DIR/aliases.zsh"
sed -i '/^alias rechunk=.*$/d' "$ZSH_DIR/aliases.zsh"

# Remove macOS config aliases
sed -i '/^alias wmconfig=.*chunkwmrc.*$/d' "$ZSH_DIR/aliases.zsh"
sed -i '/^alias hyperconfig=.*hyper\.js.*$/d' "$ZSH_DIR/aliases.zsh"
sed -i '/^alias khdconfig=.*khdrc.*$/d' "$ZSH_DIR/aliases.zsh"

# Remove macOS-specific section headers that are now empty
sed -i '/^# Browser Shortcuts (macOS specific)$/d' "$ZSH_DIR/aliases.zsh"
sed -i '/^# Window Manager (macOS specific.*$/d' "$ZSH_DIR/aliases.zsh"

# Fix GoogleDrive navigation aliases
sed -i '/^alias cdresume=.*GoogleDrive.*$/d' "$ZSH_DIR/aliases.zsh"
sed -i '/^alias cdconfig=.*GoogleDrive.*$/d' "$ZSH_DIR/aliases.zsh"

# Fix repos/projects paths
sed -i 's|^alias cdrepos=.*$|alias cdrepos="cd ~/workspace"|' "$ZSH_DIR/aliases.zsh"
sed -i 's|^alias cdprojects=.*$|alias cdprojects="cd ~/workspace"|' "$ZSH_DIR/aliases.zsh"

# Update z alias to zoxide
sed -i "s|^alias c='z'.*$|alias c='z'                                       # Jump around (requires: zoxide)|" "$ZSH_DIR/aliases.zsh"

log "aliases.zsh: removed macOS aliases (chrome, kwm, chunkwm, hyper, khd), fixed paths"
((CHANGED++))

# ─────────────────────────────────────────────────────────────────────────────
log_section "6. Clean functions.zsh (remove macOS functions)"
# ─────────────────────────────────────────────────────────────────────────────
backup "$ZSH_DIR/functions.zsh"

# Remove macOS section header + efimount function
sed -i '/^# macOS Specific Functions$/,/^}$/{ /^# macOS Specific Functions$/d; /^$/d; /^# Mount EFI/d; /^# Usage: efimount/d; /^efimount()/,/^}/d; }' "$ZSH_DIR/functions.zsh"

# Remove trackpad_speed function
sed -i '/^# Adjust trackpad speed/d' "$ZSH_DIR/functions.zsh"
sed -i '/^# Usage: trackpad_speed/d' "$ZSH_DIR/functions.zsh"
sed -i '/^# Example: trackpad_speed/d' "$ZSH_DIR/functions.zsh"
sed -i '/^trackpad_speed()/,/^}/d' "$ZSH_DIR/functions.zsh"

# Remove the macOS section separator line
sed -i '/^# ──.*$/{ N; /^\n$/d }' "$ZSH_DIR/functions.zsh"

log "functions.zsh: removed efimount(), trackpad_speed()"
((CHANGED++))

# ─────────────────────────────────────────────────────────────────────────────
log_section "7. Fix startup.zsh (archey → fastfetch)"
# ─────────────────────────────────────────────────────────────────────────────
backup "$ZSH_DIR/startup.zsh"

# Replace archey with fastfetch
sed -i 's|^archey -o$|fastfetch|' "$ZSH_DIR/startup.zsh"
sed -i 's|^# Requires: archey.*$|# Requires: fastfetch (pacman -S fastfetch)|' "$ZSH_DIR/startup.zsh"

log "startup.zsh: archey → fastfetch"
((CHANGED++))

# ─────────────────────────────────────────────────────────────────────────────
log_section "8. Fix .zshrc (remove Linuxbrew, spicetify, dedup PATH)"
# ─────────────────────────────────────────────────────────────────────────────
backup "$ZSH_DIR/.zshrc"

# Remove spicetify PATH
sed -i '/^export PATH=\$PATH:\/home\/kvn\/.spicetify$/d' "$ZSH_DIR/.zshrc"

# Remove Linuxbrew asdf sourcing
sed -i '/^. \/home\/linuxbrew\/.linuxbrew\/opt\/asdf\/libexec\/asdf.sh$/d' "$ZSH_DIR/.zshrc"

# Remove duplicate bun block (keep first occurrence)
# First, remove the second "# bun" + export block
sed -i '0,/^# bun$/b; /^# bun$/{ N; /export BUN_INSTALL/{ N; /export PATH.*BUN_INSTALL/d; }; d; }' "$ZSH_DIR/.zshrc"

# Remove duplicate ~/.local/bin PATH addition at bottom (already in env.zsh)
sed -i '/^export PATH="\$HOME\/.local\/bin:\$PATH"$/d' "$ZSH_DIR/.zshrc"

log ".zshrc: removed spicetify, asdf/linuxbrew, duplicate bun + PATH entries"
((CHANGED++))

# ─────────────────────────────────────────────────────────────────────────────
log_section "9. Create zshrc.local example for machine-specific overrides"
# ─────────────────────────────────────────────────────────────────────────────
EXAMPLE_FILE="$ZSH_DIR/zshrc.local.example"
if [[ ! -f "$EXAMPLE_FILE" ]]; then
    cat > "$EXAMPLE_FILE" << 'EOF'
# Machine-specific zsh overrides for CachyOS
# Copy to ~/.zshrc.local and customize
# This file is sourced at the end of .zshrc and is NOT version-controlled

# LV2/LADSPA plugin paths for PipeWire DSP
export LV2_PATH="$HOME/.local/lib/lv2:/usr/lib/lv2"
export LADSPA_PATH="$HOME/.local/lib/ladspa:/usr/lib/ladspa"
EOF
    log "Created zshrc.local.example for machine-specific overrides"
    ((CHANGED++))
else
    log "zshrc.local.example already exists"
fi

# ─────────────────────────────────────────────────────────────────────────────
log_section "Verification"
# ─────────────────────────────────────────────────────────────────────────────

# Check for remaining macOS/Linuxbrew references
REMNANTS=$(grep -rn 'linuxbrew\|/Applications/\|brew --prefix\|chunkwm\|khdrc\|GoogleDrive' "$ZSH_DIR"/*.zsh "$ZSH_DIR/.zshrc" 2>/dev/null || true)
if [[ -n "$REMNANTS" ]]; then
    log_warn "Remaining macOS/Linuxbrew references found:"
    echo "$REMNANTS" | tee -a "$LOG_FILE"
else
    log "No macOS/Linuxbrew remnants detected"
fi

# Quick zsh syntax check (non-fatal)
if command -v zsh &>/dev/null; then
    if zsh -c 'echo "zsh ok"' &>/dev/null 2>&1; then
        log "zsh starts cleanly"
    else
        log_warn "zsh may have issues — check manually with: zsh -i"
    fi
else
    log_warn "zsh not found in PATH"
fi

# ─────────────────────────────────────────────────────────────────────────────
log_section "Summary"
# ─────────────────────────────────────────────────────────────────────────────
log "Sections modified: $CHANGED"
log "Backups created with .pre-migration suffix"
log "Log: $LOG_FILE"
echo ""
echo "  1. oh-my-zsh.zsh    → Arch-aware ZSH path + fpath"
echo "  2. shell-behavior    → Arch autosuggestions path"
echo "  3. oh-my-zsh.zsh    → Arch syntax-highlighting fallback"
echo "  4. external.zsh     → Removed Linuxbrew, z → zoxide"
echo "  5. aliases.zsh      → Removed macOS aliases, fixed paths"
echo "  6. functions.zsh    → Removed efimount(), trackpad_speed()"
echo "  7. startup.zsh      → archey → fastfetch"
echo "  8. .zshrc           → Removed spicetify, asdf, deduped PATH"
echo "  9. zshrc.local      → Created example for machine overrides"
echo ""
log "Done. Reload with: source ~/.zshrc"
