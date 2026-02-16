# ==============================================================================
# OH-MY-ZSH FRAMEWORK
# ==============================================================================
# Core framework configuration - must load before plugins

# Framework Paths
# Arch: use system oh-my-zsh if available, else user install
if [[ -d /usr/share/oh-my-zsh ]]; then
  export ZSH=/usr/share/oh-my-zsh
else
  export ZSH=~/.oh-my-zsh
fi
fpath=(/usr/share/zsh/site-functions $fpath)

# Theme Configuration
# Powerlevel10k is sourced directly from system package (not via ZSH_THEME)
# Run `p10k configure` to customize, config saved to ~/.p10k.zsh
ZSH_THEME=""

# Framework Behavior
ZSH_DISABLE_COMPFIX=true                # Disable insecure directory warnings
HYPHEN_INSENSITIVE="true"               # Treat hyphens and underscores as equivalent
ENABLE_CORRECTION="true"                # Enable command auto-correction
COMPLETION_WAITING_DOTS="true"          # Display red dots while waiting for completion

# Plugins
# ADD WISELY! Too many plugins slow down shell startup
plugins=(
  git                      # Git aliases and functions
  bgnotify                 # Desktop notification when long commands finish
  extract                  # `extract file.tar.gz` — auto-detects archive format
  sudo                     # Press Esc twice to prepend sudo
  copypath                 # Copy current directory path to clipboard
  copybuffer               # Ctrl-O copies current command line to clipboard
  docker                   # Docker completions and aliases
  npm                      # npm completions and aliases
  rust                     # Cargo/rustup completions
)

# Initialize Oh-My-Zsh (runs compinit)
source $ZSH/oh-my-zsh.sh

# ──────────────────────────────────────────────────────────────────────────────
# fzf-tab: fuzzy tab completion (must load AFTER compinit, BEFORE autosuggestions)
# ──────────────────────────────────────────────────────────────────────────────
[[ -f ~/.zsh/fzf-tab/fzf-tab.plugin.zsh ]] && source ~/.zsh/fzf-tab/fzf-tab.plugin.zsh

# fzf-tab styles
zstyle ':fzf-tab:complete:cd:*' fzf-preview 'eza -1 --color=always --icons $realpath 2>/dev/null'
zstyle ':fzf-tab:complete:ls:*' fzf-preview 'eza -1 --color=always --icons $realpath 2>/dev/null'
zstyle ':fzf-tab:*' switch-group '<' '>'

# ──────────────────────────────────────────────────────────────────────────────
# Syntax Highlighting (fast-syntax-highlighting replaces zsh-syntax-highlighting)
# ──────────────────────────────────────────────────────────────────────────────
if [[ -f ~/.zsh/fast-syntax-highlighting/fast-syntax-highlighting.plugin.zsh ]]; then
  source ~/.zsh/fast-syntax-highlighting/fast-syntax-highlighting.plugin.zsh
elif [[ -f /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh ]]; then
  source /usr/share/zsh/plugins/zsh-syntax-highlighting/zsh-syntax-highlighting.zsh
fi

# ──────────────────────────────────────────────────────────────────────────────
# Powerlevel10k theme (system package)
# ──────────────────────────────────────────────────────────────────────────────
source /usr/share/zsh-theme-powerlevel10k/powerlevel10k.zsh-theme
[[ -f ~/.p10k.zsh ]] && source ~/.p10k.zsh
