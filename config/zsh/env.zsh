# ==============================================================================
# ENVIRONMENT VARIABLES & PATH
# ==============================================================================
# Quick access for frequent modifications (tool installations, etc.)
# Most frequently modified section - kept at top for easy access

# Core Environment
export EDITOR='vim'
export KEYTIMEOUT=1

# PATH Configuration (consolidated from scattered locations)
# Each addition is documented with its purpose
export PATH="/usr/local/sbin:$PATH"              # Local system binaries
export PATH="$HOME/.local/bin:$PATH"              # User-local binaries
export PATH="~/.npm-global/bin:$PATH"             # Global npm packages
export PATH="$PATH:$HOME/.rvm/bin"                # Ruby Version Manager

# Language-Specific Paths
# Note: NVM, Cargo, and other runtime managers are loaded in external.zsh
# to avoid conflicts with their initialization scripts

# Android SDK (idempotent - won't duplicate PATH entries)
export ANDROID_HOME=$HOME/android/sdk
export NDK_HOME=$ANDROID_HOME/ndk/25.2.9519653
[[ ":$PATH:" != *":$ANDROID_HOME/cmdline-tools/latest/bin:"* ]] && export PATH="$PATH:$ANDROID_HOME/cmdline-tools/latest/bin"
[[ ":$PATH:" != *":$ANDROID_HOME/platform-tools:"* ]] && export PATH="$PATH:$ANDROID_HOME/platform-tools"
[[ ":$PATH:" != *":$ANDROID_HOME/emulator:"* ]] && export PATH="$PATH:$ANDROID_HOME/emulator"
[[ ":$PATH:" != *":$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin:"* ]] && export PATH="$PATH:$NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin"
