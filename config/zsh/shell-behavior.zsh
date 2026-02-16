# ==============================================================================
# SHELL BEHAVIOR & OPTIONS
# ==============================================================================
# Interactive shell appearance and behavior customization

# ──────────────────────────────────────────────────────────────────────────────
# History Options
# ──────────────────────────────────────────────────────────────────────────────
# oh-my-zsh sets HISTSIZE=50000, SAVEHIST=10000, share_history, etc.
# These are additional options not covered by oh-my-zsh:
setopt inc_append_history       # Write to history immediately, not on shell exit
setopt hist_ignore_all_dups     # Remove older duplicate entries from history
setopt hist_reduce_blanks       # Remove superfluous blanks from history entries
setopt hist_find_no_dups        # Don't show duplicates when searching history

# ──────────────────────────────────────────────────────────────────────────────
# Completion Styles
# ──────────────────────────────────────────────────────────────────────────────
# Arrow-key driven interactive menu for completions
zstyle ':completion:*' menu select

# Case-insensitive and partial-word matching (git co → git commit/checkout)
zstyle ':completion:*' matcher-list 'm:{a-zA-Z}={A-Za-z}' 'r:|[._-]=* r:|=*' 'l:|=* r:|=*'

# Color completion results like ls
zstyle ':completion:*' list-colors "${(s.:.)LS_COLORS}"

# Group completions by type with labeled headers
zstyle ':completion:*' group-name ''
zstyle ':completion:*:descriptions' format '%F{yellow}-- %d --%f'
zstyle ':completion:*:warnings' format '%F{red}-- no matches found --%f'

# Completers: expand, complete, correct typos, approximate matches
zstyle ':completion:*' completer _expand _complete _correct _approximate

# Slash squeezing: /u/s/b → /usr/share/bin
zstyle ':completion:*' squeeze-slashes true

# Process completion shows user's processes
zstyle ':completion:*:*:*:*:processes' command "ps -u $USER -o pid,user,comm -w"

# ──────────────────────────────────────────────────────────────────────────────
# Autosuggestions
# ──────────────────────────────────────────────────────────────────────────────
# Fish-like autosuggestions from history AND the completion system
# Arch: use system package, fallback to manual install
if [[ -f /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
  source /usr/share/zsh/plugins/zsh-autosuggestions/zsh-autosuggestions.zsh
elif [[ -f ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh ]]; then
  source ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh
fi
ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE="fg=3"
ZSH_AUTOSUGGEST_STRATEGY=(history completion)

# ──────────────────────────────────────────────────────────────────────────────
# Autopair - auto-close brackets, quotes, backticks
# ──────────────────────────────────────────────────────────────────────────────
if [[ -f ~/.zsh/zsh-autopair/autopair.zsh ]]; then
  source ~/.zsh/zsh-autopair/autopair.zsh
  autopair-init
fi

# ──────────────────────────────────────────────────────────────────────────────
# System Clipboard - sync vi-mode yank/paste with Wayland clipboard
# ──────────────────────────────────────────────────────────────────────────────
if [[ -f ~/.zsh/zsh-system-clipboard/zsh-system-clipboard.zsh ]]; then
  source ~/.zsh/zsh-system-clipboard/zsh-system-clipboard.zsh
fi
