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

# Start tmux with a writable runtime directory and explicit socket path.
tmuxr() {
  local runtime_dir="" socket_file="" stale dir rc
  local -a candidate_dirs=(/tmp "/run/user/$UID" "${XDG_RUNTIME_DIR:-}" "${TMPDIR:-}" "$HOME/.tmux")

  for dir in $candidate_dirs; do
    [[ -z "$dir" ]] && continue
    [[ -d "$dir" ]] || continue
    [[ -w "$dir" ]] || continue

    mkdir -p "$dir"
    runtime_dir="$dir"
    socket_file="$runtime_dir/tmux-repair-$$-socket"

    for stale in "$runtime_dir"/tmux-repair*(N); do
      [[ -S "$stale" ]] && rm -f -- "$stale"
    done

    if (( $# > 0 )); then
      TMUX_TMPDIR="$runtime_dir" XDG_RUNTIME_DIR="$runtime_dir" \
        command tmux -S "$socket_file" "$@"
    else
      TMUX_TMPDIR="$runtime_dir" XDG_RUNTIME_DIR="$runtime_dir" \
        command tmux -S "$socket_file" new-session
    fi
    rc=$?
    if (( rc == 0 )); then
      return 0
    fi
    print -u2 "tmuxr: socket in ${runtime_dir} failed (exit $rc), trying next candidate"
  done

  print -u2 "tmuxr: no writable runtime directory worked"
  return 1
}

tmux() {
  if [[ -n "${TMUX:-}" ]]; then
    command tmux "$@"
    return $?
  fi

  command tmux "$@" && return 0

  TMUX_RECOVERY_MODE=1 tmuxr "$@" && return 0

  print -u2 "tmux: recovery with default runtime failed; retrying plain tmux"
  TMUX_RECOVERY_MODE=1 command tmux "$@"
}
