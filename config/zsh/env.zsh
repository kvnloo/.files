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
