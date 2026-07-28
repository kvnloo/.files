# ==============================================================================
# CUSTOM FUNCTIONS
# ==============================================================================
# Shell functions for extended functionality

# ──────────────────────────────────────────────────────────────────────────────
# Display all terminal color combinations
all_colors() {
  for x in {0..8}; do
    for i in {30..37}; do
      for a in {40..47}; do
        echo -ne "\e[$x;$i;$a""m\\\e[$x;$i;$a""m\e[0;37;40m "
      done
      echo
    done
  done
  echo ""
}

# Display quick color palette reference
colors() {
  echo "\n\u001b[0m\u001b[31m\u001b[41m   \u001b[0m\u001b[31m\u001b[41m   \u001b[0m\u001b[32m\u001b[42m   \u001b[0m\u001b[32m\u001b[42m   \u001b[0m\u001b[33m\u001b[43m   \u001b[0m\u001b[33m\u001b[43m   \u001b[0m\u001b[34m\u001b[44m   \u001b[0m\u001b[34m\u001b[44m   \u001b[0m\u001b[35m\u001b[45m   \u001b[0m\u001b[35m\u001b[45m   \u001b[0m\u001b[36m\u001b[46m   \u001b[0m\u001b[36m\u001b[46m   \u001b[0m\u001b[37m\u001b[47m   \u001b[0m\u001b[37m\u001b[47m   \n"
}

# ──────────────────────────────────────────────────────────────────────────────


# Attach to (or create) a tmux session named after the current project dir.
# Continuum restores saved sessions at login; agent panes resume in their
# original project directories.
tm() {
  local raw_name="${1:-${PWD:t}}"
  local name="${raw_name//[^A-Za-z0-9_-]/-}"
  [[ -n "$name" ]] || name="main"

  if [[ -n "$TMUX" ]]; then
    if tmux has-session -t "=$name" 2>/dev/null; then
      tmux switch-client -t "=$name"
    else
      tmux new-session -d -s "$name" -c "$PWD"
      tmux switch-client -t "=$name"
    fi
  else
    tmux new-session -A -s "$name" -c "$PWD"
  fi
}
