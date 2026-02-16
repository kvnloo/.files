# ==============================================================================
# EXTERNAL INTEGRATIONS
# ==============================================================================
# Third-party tool initializations (load after core configuration)

# ──────────────────────────────────────────────────────────────────────────────
# Homebrew (Linuxbrew)
# ──────────────────────────────────────────────────────────────────────────────
eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"

# ──────────────────────────────────────────────────────────────────────────────
# Z - Jump Around
# ──────────────────────────────────────────────────────────────────────────────
# Smart directory jumping based on frecency
# Requires: https://github.com/rupa/z
source "$(brew --prefix)/etc/profile.d/z.sh"

# ──────────────────────────────────────────────────────────────────────────────
# NVM - Node Version Manager
# ──────────────────────────────────────────────────────────────────────────────
# Manages multiple Node.js versions
# Install: https://github.com/nvm-sh/nvm
export NVM_DIR="$HOME/.nvm"
[ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"                    # Load nvm
[ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"  # Load nvm bash_completion

# ──────────────────────────────────────────────────────────────────────────────
# Cargo - Rust Package Manager
# ──────────────────────────────────────────────────────────────────────────────
# Rust toolchain environment
. "$HOME/.cargo/env"
