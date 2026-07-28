# ==============================================================================
# KEYBINDINGS
# ==============================================================================
# Custom key mappings for terminal interaction

bindkey -v                                        # Enable Vi mode

# Navigation
bindkey '^P' up-history                           # Ctrl-P: Previous command
bindkey '^N' down-history                         # Ctrl-N: Next command

# Text manipulation
bindkey '^?' backward-delete-char                 # Backspace: Delete character
bindkey '^h' backward-delete-char                 # Ctrl-H: Delete character
bindkey '^w' backward-kill-word                   # Ctrl-W: Delete word backward

# History substring search (type partial command, then Up/Down to filter)
# Requires: zsh-history-substring-search (sourced in external.zsh)
bindkey '^[[A' history-substring-search-up        # Up arrow: Search history up
bindkey '^[[B' history-substring-search-down      # Down arrow: Search history down
bindkey -M vicmd 'k' history-substring-search-up  # Vi normal: k to search up
bindkey -M vicmd 'j' history-substring-search-down # Vi normal: j to search down

# Note: Ctrl-R (fuzzy history search) is provided by Atuin
# Note: Ctrl-T (fuzzy file finder) is provided by fzf
# Note: Alt-C (fuzzy cd) is provided by fzf
# Note: Ctrl-G (interactive cheatsheet) is provided by navi
# Note: Ctrl-O (copy command to clipboard) is provided by omz copybuffer
# Note: Esc Esc (prepend sudo) is provided by omz sudo plugin
