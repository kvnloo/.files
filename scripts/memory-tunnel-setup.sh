#!/usr/bin/env bash
# Only non-secret configuration belongs in memory-tunnel.env.
set -euo pipefail
set +x
umask 077
mode="${1:-init}"
case "$mode" in init|run|doctor) ;; *) echo 'Usage: memory-tunnel-setup.sh {init|run|doctor}' >&2; exit 2;; esac
: "${TUNNEL_ID:?Set TUNNEL_ID in the non-secret configuration}"
: "${Z0INT_WORKTREE:?Set Z0INT_WORKTREE to the reviewed z0int checkout}"
: "${MEMORY_PYTHON:?Set MEMORY_PYTHON to its absolute Python executable}"
[[ "$Z0INT_WORKTREE" = /* && -d "$Z0INT_WORKTREE" && "$MEMORY_PYTHON" = /* && -x "$MEMORY_PYTHON" ]] || { echo 'Invalid worktree or Python executable' >&2; exit 1; }
export PYTHONPATH="$Z0INT_WORKTREE"
export PYTHONDONTWRITEBYTECODE=1
state="${XDG_STATE_HOME:-$HOME/.local/state}/memory-tunnel"
export TUNNEL_CLIENT_PROFILE_DIR="$state/profiles"
mkdir -p "$TUNNEL_CLIENT_PROFILE_DIR" "$state/audit"
# The MCP child must have an independently reviewed, deny-by-default policy.
: "${Z0INT_MEMORY_MCP_POLICY:?Set the reviewed memory MCP policy file}"
export Z0INT_MEMORY_MCP_POLICY
export Z0INT_MEMORY_MCP_STATE="$state/audit"
if [[ -n "${CREDENTIALS_DIRECTORY:-}" && -r "$CREDENTIALS_DIRECTORY/control-plane-api-key" ]]; then
  CONTROL_PLANE_API_KEY="$(<"$CREDENTIALS_DIRECTORY/control-plane-api-key")"
elif [[ -n "${BWS_SECRET_ID:-}" ]]; then
  # BWS_ACCESS_TOKEN is supplied at runtime, never stored by this script.
  : "${BWS_ACCESS_TOKEN:?Provide BWS_ACCESS_TOKEN through the runtime credential environment}"
  CONTROL_PLANE_API_KEY="$(bws secret get "$BWS_SECRET_ID" --output json 2>/dev/null | jq -er '.value | select(type == "string" and length > 0)')"
else
  echo 'Provide systemd credential control-plane-api-key or BWS_SECRET_ID and runtime BWS_ACCESS_TOKEN' >&2
  exit 1
fi
[[ -n "$CONTROL_PLANE_API_KEY" ]] || { echo 'Runtime credential is empty' >&2; exit 1; }
export CONTROL_PLANE_API_KEY
unset BWS_ACCESS_TOKEN
client="$HOME/.local/bin/tunnel-client"
if [[ "$mode" = init ]]; then
  # Only the environment reference, never the value, is serialized in YAML.
  exec "$client" init --sample sample_mcp_stdio_local --profile memory \
    --profile-dir "$TUNNEL_CLIENT_PROFILE_DIR" --tunnel-id "$TUNNEL_ID" \
    --mcp-command "$MEMORY_PYTHON -m z0int.memory_mcp" \
    --control-plane-api-key-ref env:CONTROL_PLANE_API_KEY \
    --health-listen-addr 127.0.0.1:8789
elif [[ "$mode" = doctor ]]; then
  exec "$client" doctor --profile memory --explain
else
  exec "$client" run --profile memory --health.listen-addr 127.0.0.1:8789 \
    --log.level warn --admin-ui.log-buffer-events 1
fi
