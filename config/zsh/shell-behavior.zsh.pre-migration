# ==============================================================================
# SHELL BEHAVIOR & OPTIONS
# ==============================================================================
# Interactive shell appearance and behavior customization

# Custom Prompt (ZLE - Zsh Line Editor)
# Displays VIM mode indicator in right prompt
precmd() { RPROMPT="" }

function zle-line-init zle-keymap-select {
  VIM_PROMPT="%{$fg_bold[yellow]%} [% NORMAL]%  %{$reset_color%}"
  RPS1="${${KEYMAP/vicmd/$VIM_PROMPT}/(main|viins)/} $EPS1"
  zle reset-prompt
}

zle -N zle-line-init
zle -N zle-keymap-select

# Autosuggestions (Fish-like autosuggestions from history)
# Requires: zsh-autosuggestions (install via: git clone https://github.com/zsh-users/zsh-autosuggestions ~/.zsh/zsh-autosuggestions)
source ~/.zsh/zsh-autosuggestions/zsh-autosuggestions.zsh
export ZSH_AUTOSUGGEST_HIGHLIGHT_STYLE="fg=3"    # Suggestion text color (yellow)
