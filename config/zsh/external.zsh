# ==============================================================================
# EXTERNAL INTEGRATIONS
# ==============================================================================
# Third-party tool initializations (load after core configuration)

# ──────────────────────────────────────────────────────────────────────────────
# asdf - version manager
# ──────────────────────────────────────────────────────────────────────────────
if [ -f /home/linuxbrew/.linuxbrew/opt/asdf/libexec/asdf.sh ]; then
  . /home/linuxbrew/.linuxbrew/opt/asdf/libexec/asdf.sh
elif [ -f /opt/asdf-vm/asdf.sh ]; then
  . /opt/asdf-vm/asdf.sh
elif command -v brew &>/dev/null && [ -f "$(brew --prefix asdf 2>/dev/null)/libexec/asdf.sh" ]; then
  . "$(brew --prefix asdf)/libexec/asdf.sh"
fi

# ──────────────────────────────────────────────────────────────────────────────
# bun - completions
# ──────────────────────────────────────────────────────────────────────────────
[ -s "${BUN_INSTALL:-$HOME/.bun}/_bun" ] && source "${BUN_INSTALL:-$HOME/.bun}/_bun"

# ──────────────────────────────────────────────────────────────────────────────
# Homebrew
# ──────────────────────────────────────────────────────────────────────────────
if [ -f /home/linuxbrew/.linuxbrew/bin/brew ]; then
  eval "$(/home/linuxbrew/.linuxbrew/bin/brew shellenv)"
elif [ -f /opt/homebrew/bin/brew ]; then
  eval "$(/opt/homebrew/bin/brew shellenv)"
elif [ -f /usr/local/bin/brew ]; then
  eval "$(/usr/local/bin/brew shellenv)"
fi

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
if [[ -f /usr/share/fzf/completion.zsh ]]; then
  # Linux (Arch/CachyOS)
  export FZF_BASE=/usr/share/fzf
  source /usr/share/fzf/completion.zsh
  [[ -f /usr/share/fzf/key-bindings.zsh ]] && source /usr/share/fzf/key-bindings.zsh
elif command -v brew &>/dev/null; then
  # macOS / Linuxbrew
  _fzf_prefix="$(brew --prefix fzf 2>/dev/null)"
  if [[ -n "$_fzf_prefix" && -d "$_fzf_prefix" ]]; then
    [[ -f "$_fzf_prefix/shell/completion.zsh" ]] && source "$_fzf_prefix/shell/completion.zsh"
    [[ -f "$_fzf_prefix/shell/key-bindings.zsh" ]] && source "$_fzf_prefix/shell/key-bindings.zsh"
  fi
  unset _fzf_prefix
fi

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
# Show after command output (P10k transient prompt eats preexec messages)
export YSU_MESSAGE_POSITION="after"
[[ -f /usr/share/zsh/plugins/zsh-you-should-use/you-should-use.plugin.zsh ]] && \
  source /usr/share/zsh/plugins/zsh-you-should-use/you-should-use.plugin.zsh

# ──────────────────────────────────────────────────────────────────────────────
# fnm - Fast Node Manager (replaces NVM)
# ──────────────────────────────────────────────────────────────────────────────
# Rust-based, ~5ms vs NVM's ~300-500ms startup
# Install: pacman -S fnm
if command -v fnm &>/dev/null; then
  if type _evalcache &>/dev/null; then
    _evalcache fnm env --use-on-cd --shell zsh
  else
    eval "$(fnm env --use-on-cd --shell zsh)"
  fi
elif [[ -d "$HOME/.nvm" ]]; then
  # Fallback to NVM if fnm not yet installed
  export NVM_DIR="$HOME/.nvm"
  [ -s "$NVM_DIR/nvm.sh" ] && \. "$NVM_DIR/nvm.sh"
  [ -s "$NVM_DIR/bash_completion" ] && \. "$NVM_DIR/bash_completion"
fi

# ──────────────────────────────────────────────────────────────────────────────
# Cargo - Rust Package Manager
# ──────────────────────────────────────────────────────────────────────────────
# Rust toolchain environment
[[ -f "$HOME/.cargo/env" ]] && . "$HOME/.cargo/env"

# ──────────────────────────────────────────────────────────────────────────────
# Zoxide - Smarter cd
# ──────────────────────────────────────────────────────────────────────────────
# Smart directory jumping based on frecency (replaces z)
# Install: brew install zoxide / pacman -S zoxide
if command -v zoxide &>/dev/null; then
  if type _evalcache &>/dev/null; then
    _evalcache zoxide init zsh
  else
    eval "$(zoxide init zsh)"
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# Atuin - Magical shell history (SQLite-backed, fuzzy search, sync)
# ──────────────────────────────────────────────────────────────────────────────
# Overrides Ctrl-R with superior history search (after fzf so it takes priority)
# Install: pacman -S atuin
if command -v atuin &>/dev/null; then
  if type _evalcache &>/dev/null; then
    _evalcache atuin init zsh
  else
    eval "$(atuin init zsh)"
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# direnv - per-project environment variables via .envrc
# ──────────────────────────────────────────────────────────────────────────────
# Install: pacman -S direnv
if command -v direnv &>/dev/null; then
  if type _evalcache &>/dev/null; then
    _evalcache direnv hook zsh
  else
    eval "$(direnv hook zsh)"
  fi
fi

# ──────────────────────────────────────────────────────────────────────────────
# navi - interactive cheatsheet (Ctrl-G)
# ──────────────────────────────────────────────────────────────────────────────
# Install: pacman -S navi
if command -v navi &>/dev/null; then
  if type _evalcache &>/dev/null; then
    _evalcache navi widget zsh
  else
    eval "$(navi widget zsh)"
  fi
fi
