# ==============================================================================
# ENVIRONMENT VARIABLES & PATH
# ==============================================================================
# Quick access for frequent modifications (tool installations, etc.)
# Most frequently modified section - kept at top for easy access

# Core Environment
export EDITOR='vim'
export KEYTIMEOUT=1
export BROWSER='google-chrome-stable'
export TERMINAL='kitty'
export MAIL='thunderbird'

# Desktop toolkit theming
export QT_QPA_PLATFORMTHEME='qt5ct'
export GTK2_RC_FILES="$HOME/.gtkrc-2.0"

# PATH Configuration (consolidated from scattered locations)
# Each addition is documented with its purpose
export PATH="/usr/local/sbin:$PATH"              # Local system binaries
export PATH="$HOME/.local/bin:$PATH"              # User-local binaries
export PATH="~/.npm-global/bin:$PATH"             # Global npm packages
export PATH="$PATH:$HOME/.rvm/bin"                # Ruby Version Manager
export PATH="$HOME/Library/Python/3.9/bin:$PATH"  # Python 3.9 user packages

# Language-Specific Paths
# Note: fnm, Cargo, and other runtime managers are loaded in external.zsh
# to avoid conflicts with their initialization scripts

# Android SDK (idempotent - won't duplicate PATH entries)
export ANDROID_HOME=$HOME/android/sdk
export NDK_HOME=$ANDROID_HOME/ndk/25.2.9519653
[[ ":$PATH:" != *":$ANDROID_HOME/cmdline-tools/latest/bin:"* ]] && export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin"
[[ ":$PATH:" != *":$ANDROID_HOME/platform-tools:"* ]] && export PATH="$PATH:$ANDROID_HOME/platform-tools"
[[ ":$PATH:" != *":$ANDROID_HOME/emulator:"* ]] && export PATH="$PATH:$ANDROID_HOME/emulator"
[[ ":$PATH:" != *":$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin:"* ]] && export PATH="$PATH:$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin"

# spicetify
[ -d "$HOME/.spicetify" ] && export PATH="$PATH:$HOME/.spicetify"

# bun
export BUN_INSTALL="$HOME/.bun"
[ -d "$BUN_INSTALL/bin" ] && export PATH="$BUN_INSTALL/bin:$PATH"

# duckdb
[ -d "$HOME/.duckdb/cli/latest" ] && export PATH="$HOME/.duckdb/cli/latest:$PATH"

# Google Cloud SDK (macOS Homebrew)
if command -v brew &>/dev/null; then
  _gcloud_dir="$(brew --prefix 2>/dev/null)/share/google-cloud-sdk"
  [ -d "$_gcloud_dir/bin" ] && export PATH="$_gcloud_dir/bin:$PATH"
  unset _gcloud_dir
fi

# ──────────────────────────────────────────────────────────────────────────────
# fzf - use fd for faster, .gitignore-aware file/directory finding
# ──────────────────────────────────────────────────────────────────────────────
export FZF_DEFAULT_COMMAND='fd --type f --hidden --follow --exclude .git'
export FZF_CTRL_T_COMMAND="$FZF_DEFAULT_COMMAND"
export FZF_ALT_C_COMMAND='fd --type d --hidden --follow --exclude .git'

# ──────────────────────────────────────────────────────────────────────────────
# bat - syntax-highlighted man pages
# ──────────────────────────────────────────────────────────────────────────────
export MANPAGER="sh -c 'col -bx | bat -l man -p'"
export MANROFFOPT="-c"
