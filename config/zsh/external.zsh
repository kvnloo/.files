# ==============================================================================
# EXTERNAL INTEGRATIONS
# ==============================================================================
# Third-party tool initializations (load after core configuration)

# ──────────────────────────────────────────────────────────────────────────────
# evalcache - cache eval init calls for faster startup
# ──────────────────────────────────────────────────────────────────────────────
# Wraps `eval "$(tool init zsh)"` so output is cached to file (~1-2ms vs ~20-50ms)
# Run `_evalcache_clear` after updating tools to refresh cache
[[ -f ~/.zsh/evalcache/evalcache.plugin.zsh ]] && source ~/.zsh/evalcache/evalcache.plugin.zsh

# ──────────────────────────────────────────────────────────────────────────────
# fzf - Fuzzy Finder
# ──────────────────────────────────────────────────────────────────────────────
# Ctrl-T: fuzzy file finder, Alt-C: fuzzy cd
# Note: Ctrl-R is handled by Atuin below (superior history search)
export FZF_BASE=/usr/share/fzf
[[ -f /usr/share/fzf/completion.zsh ]] && source /usr/share/fzf/completion.zsh
[[ -f /usr/share/fzf/key-bindings.zsh ]] && source /usr/share/fzf/key-bindings.zsh

# ──────────────────────────────────────────────────────────────────────────────
# History Substring Search
# ──────────────────────────────────────────────────────────────────────────────
# Type partial command, then Up/Down to cycle through matching history
# Install: pacman -S zsh-history-substring-search
[[ -f /usr/share/zsh/plugins/zsh-history-substring-search/zsh-history-substring-search.zsh ]] && \
  source /usr/share/zsh/plugins/zsh-history-substring-search/zsh-history-substring-search.zsh

# ──────────────────────────────────────────────────────────────────────────────
# You Should Use - alias reminder
# ──────────────────────────────────────────────────────────────────────────────
# Reminds you of existing aliases for commands you just typed
# Install: paru -S zsh-you-should-use
[[ -f /usr/share/zsh/plugins/zsh-you-should-use/you-should-use.plugin.zsh ]] && \
  source /usr/share/zsh/plugins/zsh-you-should-use/you-should-use.plugin.zsh

# ──────────────────────────────────────────────────────────────────────────────
# fnm - Fast Node Manager (replaces NVM)
# ──────────────────────────────────────────────────────────────────────────────
# Rust-based, ~5ms vs NVM's ~300-500ms startup
# Install: pacman -S fnm
if command -v fnm &>/dev/null; then
  _evalcache fnm env --use-on-cd --shell zsh
elif [[ -d "$HOME/.nvm" ]]; then
  # Fallback to NVM if fnm not yet installed
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
  [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Cargo - Rust Package Manager
# ──────────────────────────────────────────────────────────────────────────────
[[ -f "$HOME/.cargo/env" ]] && . "$HOME/.cargo/env"

# ──────────────────────────────────────────────────────────────────────────────
# Zoxide - Smarter cd
# ──────────────────────────────────────────────────────────────────────────────
if command -v zoxide &>/dev/null; then
  _evalcache zoxide init zsh
fi

# ──────────────────────────────────────────────────────────────────────────────
# Atuin - Magical shell history (SQLite-backed, fuzzy search, sync)
# ──────────────────────────────────────────────────────────────────────────────
# Overrides Ctrl-R with superior history search (after fzf so it takes priority)
# Install: pacman -S atuin
if command -v atuin &>/dev/null; then
  _evalcache atuin init zsh
fi

# ──────────────────────────────────────────────────────────────────────────────
# direnv - per-project environment variables via .envrc
# ──────────────────────────────────────────────────────────────────────────────
# Install: pacman -S direnv
if command -v direnv &>/dev/null; then
  _evalcache direnv hook zsh
fi

# ──────────────────────────────────────────────────────────────────────────────
# navi - interactive cheatsheet (Ctrl-G)
# ──────────────────────────────────────────────────────────────────────────────
# Install: pacman -S navi
if command -v navi &>/dev/null; then
  _evalcache navi widget zsh
fi
