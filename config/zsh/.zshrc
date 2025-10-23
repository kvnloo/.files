# ==============================================================================
# ZSH CONFIGURATION - MODULAR STRUCTURE
# ==============================================================================
#
# This configuration is organized into modular files for better maintainability.
# Each section is stored in a separate file and sourced below.
#
# ORGANIZATION HIERARCHY:
# ┌─────────────────────────────────────────────────────────────────┐
# │ 1. ENVIRONMENT VARIABLES & PATH          → env.zsh              │
# │    (Most frequently modified - easy access at top)              │
# ├─────────────────────────────────────────────────────────────────┤
# │ 2. OH-MY-ZSH CORE CONFIGURATION          → oh-my-zsh.zsh        │
# │    (Framework initialization - must run early)                  │
# ├─────────────────────────────────────────────────────────────────┤
# │ 3. SHELL BEHAVIOR & OPTIONS              → shell-behavior.zsh   │
# │    (Interactive shell settings)                                 │
# ├─────────────────────────────────────────────────────────────────┤
# │ 4. KEYBINDINGS                           → keybindings.zsh      │
# │    (User interaction - frequently referenced)                   │
# ├─────────────────────────────────────────────────────────────────┤
# │ 5. ALIASES                               → aliases.zsh          │
# │    (Command shortcuts - frequently modified)                    │
# ├─────────────────────────────────────────────────────────────────┤
# │ 6. FUNCTIONS                             → functions.zsh        │
# │    (Custom shell functions)                                     │
# ├─────────────────────────────────────────────────────────────────┤
# │ 7. EXTERNAL INTEGRATIONS                 → external.zsh         │
# │    (Third-party tools: nvm, z, brew, cargo)                     │
# ├─────────────────────────────────────────────────────────────────┤
# │ 8. STARTUP PROGRAMS                      → startup.zsh          │
# │    (Visual programs - run last to avoid blocking)               │
# └─────────────────────────────────────────────────────────────────┘
#
# USAGE:
# - Edit individual files in config/zsh/ to modify specific sections
# - Changes take effect after running: source ~/.zshrc
# - Or use the alias: reloadzsh
#
# SYMLINK SETUP:
# Create a symlink from your home directory to this file:
#   ln -sf ~/path/to/.files/config/zsh/.zshrc ~/.zshrc
#
# ==============================================================================

# Get the directory where this .zshrc file is located
ZSHRC_DIR="${0:A:h}"

# Source modular configuration files in dependency order
source "$ZSHRC_DIR/env.zsh"             # 1. Environment variables & PATH
source "$ZSHRC_DIR/oh-my-zsh.zsh"       # 2. Oh-My-Zsh framework
source "$ZSHRC_DIR/shell-behavior.zsh"  # 3. Shell behavior & prompt
source "$ZSHRC_DIR/keybindings.zsh"     # 4. Key mappings
source "$ZSHRC_DIR/aliases.zsh"         # 5. Command aliases
source "$ZSHRC_DIR/functions.zsh"       # 6. Custom functions
source "$ZSHRC_DIR/external.zsh"        # 7. External tool integrations
source "$ZSHRC_DIR/startup.zsh"         # 8. Startup programs (last)

# ==============================================================================
# LOCAL OVERRIDES (OPTIONAL)
# ==============================================================================
# For machine-specific configuration that shouldn't be version-controlled,
# create a ~/.zshrc.local file with your custom settings
[ -f ~/.zshrc.local ] && source ~/.zshrc.local
