# ==============================================================================
# ALIASES
# ==============================================================================
# Command shortcuts and overrides

# ──────────────────────────────────────────────────────────────────────────────
# Modern CLI Replacements
# ──────────────────────────────────────────────────────────────────────────────
# eza → ls (icons, git status, tree view)
alias ls='eza --color=always --group-directories-first --icons'
alias la='eza -la --color=always --group-directories-first --icons'
alias ll='eza -l --color=always --group-directories-first --icons'
alias lt='eza -aT --color=always --group-directories-first --icons'

# bat → cat (syntax highlighting, line numbers)
alias cat='bat --paging=never'

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
