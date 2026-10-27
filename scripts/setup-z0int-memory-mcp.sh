#!/usr/bin/env bash
# Deploy only an explicitly approved, already-merged checkout; no client edits.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ ${1:-} == apply && ${2:-} =~ ^[0-9a-f]{40}$ && $# == 2 ]] || {
  printf 'Usage: %s apply MERGED_SHA\n' "$0" >&2
  exit 2
}
(( EUID != 0 )) || { printf 'Run as the groot desktop user, not root.\n' >&2; exit 1; }
[[ $(hostname) == groot || $(hostname) == 0 ]] || { printf 'Run on groot.\n' >&2; exit 1; }
checkout="$HOME/.local/share/z0int-memory-mcp"
[[ $(git -C "$checkout" rev-parse HEAD) == "$2" ]] || {
  printf 'Deployed checkout does not match the approved merged SHA.\n' >&2
  exit 1
}
[[ -f "$checkout/src/z0int/memory_mcp.py" ]]
[[ -f "$checkout/src/z0int/memory_mcp_backends.py" ]]
# Reuse native credentials in place. Never copy, print, or widen them.
[[ $(stat -Lc '%u:%a' "$HOME/.agentsview/config.toml") == "$(id -u):600" ]] || {
  printf 'Existing AgentsView config must be owned by this user with mode 0600.\n' >&2
  exit 1
}
[[ -x /usr/bin/socat ]]
# The stdio transport requires only MCP plus its dependencies, not model weights.
# Match the upstream pyproject.toml runtime pin.
if [[ ! -x "$checkout/.venv/bin/python" ]]; then
  /usr/bin/python3.11 -m venv "$checkout/.venv"
fi
"$checkout/.venv/bin/python" -m pip install --disable-pip-version-check 'mcp==1.26.0'
install -Dm600 "$root/config/z0int/memory-mcp-policy.json" "$HOME/.config/z0int/memory-mcp-policy.json"
install -Dm755 "$root/scripts/z0int-memory-mcp" "$HOME/.local/bin/z0int-memory-mcp"
for unit in z0int-memory-mcp.socket z0int-memory-mcp@.service; do
  install -Dm644 "$root/config/systemd/user/$unit" "$HOME/.config/systemd/user/$unit"
done
systemctl --user daemon-reload
systemctl --user enable --now z0int-memory-mcp.socket
systemctl --user status z0int-memory-mcp.socket --no-pager
printf 'MCP stdio command: %s/.local/bin/z0int-memory-mcp\n' "$HOME"
