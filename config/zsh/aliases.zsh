# ==============================================================================
# ALIASES
# ==============================================================================
# Command shortcuts and overrides

# ──────────────────────────────────────────────────────────────────────────────
# Safety & Utilities
# ──────────────────────────────────────────────────────────────────────────────
alias rm='rmtrash'                                # Safer deletion (requires: brew install rmtrash)

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
alias wmconfig="vim ~/.chunkwmrc"
alias hyperconfig="vim ~/.hyper.js"
alias khdconfig="vim ~/.khdrc"

# ──────────────────────────────────────────────────────────────────────────────
# Navigation
# ──────────────────────────────────────────────────────────────────────────────
alias c='z'                                       # Jump around (requires: z)

# Directory Shortcuts (customize paths for your setup)
alias cdresume="cd ~/GoogleDrive/Jobs/resume"
alias cdrepos="cd ~/Desktop/repos"
alias cdprojects="cd ~/Desktop/Projects"
alias cdconfig="cd ~/GoogleDrive/Projects/.files"

# ──────────────────────────────────────────────────────────────────────────────
# Convenience Commands
# ──────────────────────────────────────────────────────────────────────────────
alias la='ls -al'                                 # List all files with details
alias timon='la | lolcat'                         # Colorful file listing (requires: lolcat)
alias sl='sl | lolcat'                            # Colorful steam locomotive (requires: sl, lolcat)
alias gits="find . -name '.git'"                  # Find all git repositories
alias reloadzsh="source ~/.zshrc"                 # Reload zsh configuration

# ──────────────────────────────────────────────────────────────────────────────
# Browser Shortcuts (macOS specific)
# ──────────────────────────────────────────────────────────────────────────────
alias chrome="/Applications/Google\ Chrome.app/Contents/MacOS/Google\ Chrome"
alias chrome-canary="/Applications/Google\ Chrome\ Canary.app/Contents/MacOS/Google\ Chrome\ Canary"

# ──────────────────────────────────────────────────────────────────────────────
# Window Manager (macOS specific - requires kwm/chunkwm)
# ──────────────────────────────────────────────────────────────────────────────
alias rekwm='brew services restart kwm'          # Restart kwm window manager
alias rechunk='brew services restart chunkwm'    # Restart chunkwm window manager
