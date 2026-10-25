# Agent CLIs start in their own scope under agent.slice (scripts/agent-launch).
# Sourced from ~/.zshrc.local on hosts that run the desktop admission install.
if command -v agent-launch >/dev/null 2>&1; then
  for _agent_cli in omp claude codex pi opencode hermes; do
    eval "${_agent_cli}() { local exe=\${commands[${_agent_cli}]}; [[ -n \$exe ]] || return 127; agent-launch ${_agent_cli} \"\$exe\" \"\$@\"; }"
  done
  unset _agent_cli
fi
