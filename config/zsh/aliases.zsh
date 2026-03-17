# ==============================================================================
# ALIASES
# ==============================================================================
# Command shortcuts and overrides

# ──────────────────────────────────────────────────────────────────────────────
# Modern CLI Replacements
# ──────────────────────────────────────────────────────────────────────────────
# eza → ls (icons, git status, tree view)
if (( $+commands[eza] )); then
  alias ls='eza --color=always --group-directories-first --icons'
  alias la='eza -la --color=always --group-directories-first --icons'
  alias ll='eza -l --color=always --group-directories-first --icons'
  alias lt='eza -aT --color=always --group-directories-first --icons'
fi

# bat → cat (syntax highlighting, line numbers)
if (( $+commands[bat] )); then
  alias cat='bat --paging=never'
fi

# ──────────────────────────────────────────────────────────────────────────────
# Python Environment
# ──────────────────────────────────────────────────────────────────────────────
alias python='python3'                            # Default to Python 3
alias pip='pip3'                                  # Default to pip3

# ──────────────────────────────────────────────────────────────────────────────
# Config File Shortcuts
# ──────────────────────────────────────────────────────────────────────────────
alias zshconfig="vim ~/.zshrc"
alias vimconfig="vim ~/.vimrc"
alias gitconfig="vim ~/.gitconfig"

# ──────────────────────────────────────────────────────────────────────────────
# Navigation
# ──────────────────────────────────────────────────────────────────────────────
alias c='z'                                       # Jump around (requires: zoxide)

# Directory Shortcuts (customize paths for your setup)
alias cdrepos="cd ~/workspace"
alias cdprojects="cd ~/workspace"

# ──────────────────────────────────────────────────────────────────────────────
# Convenience Commands
# ──────────────────────────────────────────────────────────────────────────────
alias timon='la | lolcat'                         # Colorful file listing (requires: lolcat)
alias sl='sl | lolcat'                            # Colorful steam locomotive (requires: sl, lolcat)
alias gits="find . -name '.git'"                  # Find all git repositories
alias reloadzsh="source ~/.zshrc"                 # Reload zsh configuration

# ──────────────────────────────────────────────────────────────────────────────
# macOS-specific (guarded)
# ──────────────────────────────────────────────────────────────────────────────
if [[ "$OSTYPE" == darwin* ]]; then
  alias chrome="/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"
  alias chrome-canary="/Applications/Google\ Chrome\ Canary.app/Contents/MacOS/Google\ Chrome\ Canary"
  alias rekwm='brew services restart kwm'          # Restart kwm window manager
  alias rechunk='brew services restart chunkwm'    # Restart chunkwm window manager
fi

# ──────────────────────────────────────────────────────────────────────────────
# Claude Code (separate work/home configs)
# ──────────────────────────────────────────────────────────────────────────────
alias claude-work='CLAUDE_CONFIG_DIR=$HOME/.claude-work claude'
alias claude-home='CLAUDE_CONFIG_DIR=$HOME/.claude-home claude'
alias claude-mem='bun "/Users/kvn/.claude-work/plugins/cache/thedotmack/claude-mem/10.5.6/scripts/worker-service.cjs"'
