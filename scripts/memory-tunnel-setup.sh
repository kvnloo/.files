#!/usr/bin/env bash
# Runtime secrets come exclusively from systemd's decrypted credential directory.
set -euo pipefail
set +x
umask 077
fail() { printf '%s\n' 'memory-tunnel: configuration or prerequisite rejected' >&2; exit 1; }
trap fail ERR
mode="${1:-init}"
case "$mode" in init|run|doctor|validate|preflight) ;; *) fail;; esac
: "${TUNNEL_ID:?Set TUNNEL_ID}"
: "${Z0INT_WORKTREE:?Set Z0INT_WORKTREE to an installed pinned copy}"
: "${MEMORY_PYTHON:?Set MEMORY_PYTHON}"
: "${Z0INT_MEMORY_MCP_POLICY:?Set reviewed policy}"
: "${Z0INT_COMMIT:?Set reviewed commit}"
[[ "$Z0INT_WORKTREE" = /* && "$MEMORY_PYTHON" = /* && -x "$MEMORY_PYTHON" ]] || fail
# A pinned detached deployment, not a changing development branch.
[[ "$(git -C "$Z0INT_WORKTREE" rev-parse HEAD)" = "$Z0INT_COMMIT" ]] || fail
[[ -z "$(git -C "$Z0INT_WORKTREE" status --porcelain --untracked-files=all)" ]] || fail
[[ -z "$(git -C "$Z0INT_WORKTREE" symbolic-ref -q HEAD || true)" ]] || fail
export PYTHONPATH="$Z0INT_WORKTREE" PYTHONDONTWRITEBYTECODE=1
export SSH_AUTH_SOCK=
unset BWS_ACCESS_TOKEN BWS_SECRET_ID OPENAI_API_KEY CONTROL_PLANE_API_KEY
state="${XDG_STATE_HOME:-$HOME/.local/state}/memory-tunnel"
export TUNNEL_CLIENT_PROFILE_DIR="$state/profiles"
export Z0INT_MEMORY_MCP_STATE="$state/audit" Z0INT_MEMORY_MCP_POLICY
mkdir -p "$TUNNEL_CLIENT_PROFILE_DIR" "$state/audit" "$state/empty"
cd "$state/empty"
# env -i prevents transport secrets and unrelated provider credentials reaching MCP.
# Paths/config are shell-quoted for the client's command parser; prohibit quotes
# and whitespace in deployment paths rather than permit ambiguous parsing.
for value in "$MEMORY_PYTHON" "$Z0INT_WORKTREE" "$Z0INT_MEMORY_MCP_POLICY" "$state" "$HOME"; do
  [[ "$value" =~ ^/[a-zA-Z0-9_./-]+$ ]] || fail
done
command="/usr/bin/env -i HOME=$HOME PATH=/usr/local/bin:/usr/bin PYTHONPATH=$Z0INT_WORKTREE PYTHONDONTWRITEBYTECODE=1 Z0INT_MEMORY_MCP_POLICY=$Z0INT_MEMORY_MCP_POLICY Z0INT_MEMORY_MCP_STATE=$state/audit $MEMORY_PYTHON -P -m z0int.memory_mcp"
export MEMORY_MCP_EXPECTED_COMMAND="$command"
validate() {
  "$MEMORY_PYTHON" -I "$HOME/.files/scripts/memory-tunnel-validate.py" "$TUNNEL_CLIENT_PROFILE_DIR/memory.yaml"
}
if [[ "$mode" = validate ]]; then validate; exit; fi
if [[ "$mode" = preflight ]]; then
  validate
  # Require explicit kernel rejection, not an offline/timeout/refused connection.
  # The localhost probe also detects missing port-level egress controls.
  "$MEMORY_PYTHON" -I "$HOME/.files/scripts/memory-tunnel-validate.py" --egress
  exit
fi
: "${CREDENTIALS_DIRECTORY:?systemd encrypted credential required}"
[[ -r "$CREDENTIALS_DIRECTORY/control-plane-api-key" ]] || fail
CONTROL_PLANE_API_KEY="$(<"$CREDENTIALS_DIRECTORY/control-plane-api-key")"
[[ -n "$CONTROL_PLANE_API_KEY" ]] || fail
export CONTROL_PLANE_API_KEY
client="$HOME/.local/bin/tunnel-client"
if [[ "$mode" = init ]]; then
  "$client" init --sample sample_mcp_stdio_local --profile memory \
    --profile-dir "$TUNNEL_CLIENT_PROFILE_DIR" --tunnel-id "$TUNNEL_ID" \
    --mcp-command "$command" --control-plane-api-key-ref env:CONTROL_PLANE_API_KEY \
    --health-listen-addr 127.0.0.1:8789
  validate
elif [[ "$mode" = doctor ]]; then
  validate
  exec "$client" doctor --profile memory --explain
else
  validate
  for name in $(compgen -e); do
    case "$name" in HOME|PATH|CONTROL_PLANE_API_KEY|TUNNEL_CLIENT_PROFILE_DIR) ;; *) unset "$name";; esac
  done
  exec "$client" run --profile memory --profile-dir "$TUNNEL_CLIENT_PROFILE_DIR" \
    --health.listen-addr 127.0.0.1:8789 --log.level warn --admin-ui.log-buffer-events 1 2>/dev/null
fi
