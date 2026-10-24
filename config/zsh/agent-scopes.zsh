# Agent CLIs start in their own scope under agent.slice (scripts/agent-launch).
# Sourced from ~/.zshrc.local on hosts that run the desktop admission install.
if command -v agent-launch >/dev/null 2>&1; then
  for _agent_cli in omp claude codex pi opencode hermes; do
    eval "${_agent_cli}() { agent-launch ${_agent_cli} command ${_agent_cli} \"\$@\"; }"
  done
  unset _agent_cli
fi
