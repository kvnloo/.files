#!/usr/bin/env bash
# Install shared research tools for every agent harness (Agent Reach, yt-dlp, mcporter).
# Prefer: ./scripts/onboard run agent-tools   or   ./install
# Docs: docs/SETUP.md
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
mcporter_config="${repo_root}/config/mcporter/mcporter.json"
agent_tools_dir="${HOME}/.agent-reach/tools"
user_bin_dir="${HOME}/.local/bin"

if ! command -v pipx >/dev/null 2>&1; then
  printf '%s\n' "pipx is required to install the shared agent tools." >&2
  exit 1
fi

if ! command -v agent-reach >/dev/null 2>&1; then
  pipx install https://github.com/Panniantong/agent-reach/archive/main.zip
fi

agent-reach install --env=auto

if ! command -v yt-dlp >/dev/null 2>&1; then
  pipx install yt-dlp
fi

if ! command -v mcporter >/dev/null 2>&1; then
  mkdir -p "${agent_tools_dir}/mcporter" "${user_bin_dir}"
  npm install --prefix "${agent_tools_dir}/mcporter" mcporter
  ln -s "${agent_tools_dir}/mcporter/node_modules/.bin/mcporter" "${user_bin_dir}/mcporter"
fi

mkdir -p "${HOME}/.mcporter"
global_mcporter_config="${HOME}/.mcporter/mcporter.json"

if [[ -L "${global_mcporter_config}" ]]; then
  ln -sfn "${mcporter_config}" "${global_mcporter_config}"
elif [[ -e "${global_mcporter_config}" ]]; then
  printf '%s\n' \
    "Existing ${global_mcporter_config} was not overwritten." \
    "Merge it into ${mcporter_config}, then replace it with a symlink."
else
  ln -s "${mcporter_config}" "${global_mcporter_config}"
fi

printf '%s\n' \
  "" \
  "Shared agent tooling is installed." \
  "Agent Reach state and secrets: ${HOME}/.agent-reach (not tracked)" \
  "Global MCP configuration: ${mcporter_config} (tracked in .files)" \
  "Harness skills: installed globally by Agent Reach for supported agents"

agent-reach doctor
