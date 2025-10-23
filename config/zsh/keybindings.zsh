# ==============================================================================
# KEYBINDINGS
# ==============================================================================
# Custom key mappings for terminal interaction

bindkey -v                                        # Enable Vi mode
bindkey '^P' up-history                           # Ctrl-P: Previous command
bindkey '^N' down-history                         # Ctrl-N: Next command
bindkey '^?' backward-delete-char                 # Backspace: Delete character
bindkey '^h' backward-delete-char                 # Ctrl-H: Delete character
bindkey '^w' backward-kill-word                   # Ctrl-W: Delete word backward
bindkey '^r' history-incremental-search-backward  # Ctrl-R: Search command history
