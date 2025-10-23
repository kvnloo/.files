# ==============================================================================
# OH-MY-ZSH FRAMEWORK
# ==============================================================================
# Core framework configuration - must load before plugins

# Framework Paths
export ZSH=~/.oh-my-zsh
fpath=(/usr/local/share/zsh-completions $fpath)

# Theme Configuration
ZSH_THEME="robbyrussell"
# Alternative themes to try:
# ZSH_THEME="agnoster"
# export TERM="xterm-256color"  # Uncomment for agnoster theme

# Framework Behavior
ZSH_DISABLE_COMPFIX=true                # Disable insecure directory warnings
HYPHEN_INSENSITIVE="true"               # Treat hyphens and underscores as equivalent
ENABLE_CORRECTION="true"                # Enable command auto-correction
COMPLETION_WAITING_DOTS="true"          # Display red dots while waiting for completion

# Optional Settings (currently disabled)
# CASE_SENSITIVE="true"                 # Use case-sensitive completion
# DISABLE_AUTO_UPDATE="true"            # Disable bi-weekly auto-update checks
# export UPDATE_ZSH_DAYS=13             # Change auto-update frequency (days)
# DISABLE_LS_COLORS="true"              # Disable colors in ls
# DISABLE_AUTO_TITLE="true"             # Disable auto-setting terminal title
# HIST_STAMPS="mm/dd/yyyy"              # History timestamp format
# DISABLE_UNTRACKED_FILES_DIRTY="true"  # Faster status checks for large repos

# Plugins
# ADD WISELY! Too many plugins slow down shell startup
plugins=(
  git                      # Git aliases and functions
  zsh-syntax-highlighting  # Fish-like syntax highlighting
)

# Initialize Oh-My-Zsh
source $ZSH/oh-my-zsh.sh
