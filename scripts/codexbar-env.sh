#!/usr/bin/env bash
# Load CodexBar provider credentials for the Linux CLI wrapper.
# Priority: existing env > secrets.env > Crush refs > Hermes auth > OMP agent.db
# > Bitwarden Secrets Manager for any of those still unset.
# Vault values stay in this process. Do not write them to secrets.env or config.json.

set -u

_secrets_file="${CODEXBAR_SECRETS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/codexbar/secrets.env}"
if [[ -f "$_secrets_file" ]]; then
  # shellcheck disable=SC1090
  set -a
  source "$_secrets_file"
  set +a
fi

_crush_file="${CODEXBAR_CRUSH_PROVIDERS:-${XDG_DATA_HOME:-$HOME/.local/share}/crush/providers.json}"
if [[ -f "$_crush_file" ]] && command -v python3 >/dev/null 2>&1; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || -z "$value" ]] && continue
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done < <(python3 - "$_crush_file" <<'PY'
import json, os, sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(0)

raw = json.loads(path.read_text())
items = raw if isinstance(raw, list) else list(raw.values())

mapping = {
    "openrouter": "OPENROUTER_API_KEY",
    "groq": "GROQ_API_KEY",
    "cerebras": "CEREBRAS_API_KEY",
    "vercel": "VERCEL_AI_GW_KEY",
    "nous": "NOUS_API_KEY",
    "xai": "XAI_API_KEY",
}

# Crush uses VERCEL_API_KEY; CodexBar extras accept either name.
if not os.environ.get("VERCEL_AI_GW_KEY") and os.environ.get("VERCEL_API_KEY"):
    print(f"VERCEL_AI_GW_KEY={os.environ['VERCEL_API_KEY']}")

for item in items:
    if not isinstance(item, dict):
        continue
    pid = str(item.get("id") or item.get("name") or "").lower()
    env_key = next((env for token, env in mapping.items() if token in pid), None)
    if not env_key or os.environ.get(env_key):
        continue
    api_key = str(item.get("api_key") or item.get("apiKey") or "").strip()
    if not api_key:
        continue
    if api_key.startswith("$"):
        ref = api_key[1:].strip()
        resolved = os.environ.get(ref, "").strip()
        if resolved:
            print(f"{env_key}={resolved}")
        continue
    print(f"{env_key}={api_key}")
PY
  )
fi

_hermes_auth="${CODEXBAR_HERMES_AUTH:-${HERMES_AUTH_FILE:-$HOME/.hermes/auth.json}}"
if [[ -f "$_hermes_auth" ]] && command -v python3 >/dev/null 2>&1; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || -z "$value" ]] && continue
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done < <(python3 - "$_hermes_auth" <<'PY'
import json, os, sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.is_file():
    raise SystemExit(0)

try:
    raw = json.loads(path.read_text())
except Exception:
    raise SystemExit(0)

providers = raw.get("providers") if isinstance(raw, dict) else None
if not isinstance(providers, dict):
    raise SystemExit(0)

nous = providers.get("nous")
if isinstance(nous, dict) and not os.environ.get("NOUS_API_KEY"):
    token = str(nous.get("access_token") or nous.get("agent_key") or "").strip()
    if token:
        print(f"NOUS_API_KEY={token}")
        portal = str(nous.get("portal_base_url") or "").strip()
        if portal and not os.environ.get("NOUS_PORTAL_URL"):
            print(f"NOUS_PORTAL_URL={portal}")
        base = str(nous.get("inference_base_url") or "").strip()
        if base and not os.environ.get("NOUS_API_URL"):
            print(f"NOUS_API_URL={base}")
PY
  )
fi

_script_dir="$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
_omp_loader="${CODEXBAR_OMP_LOADER:-$_script_dir/codexbar_credentials.py}"
if [[ -f "$_omp_loader" ]] && command -v python3 >/dev/null 2>&1; then
  while IFS='=' read -r key value; do
    [[ -z "$key" || -z "$value" ]] && continue
    if [[ -z "${!key:-}" ]]; then
      export "$key=$value"
    fi
  done < <(python3 "$_omp_loader")
fi

# Fill provider keys the local stores do not have. The Vercel gateway secret is
# stored as AI_GATEWAY_API_KEY; CodexBar's extra fetcher reads VERCEL_AI_GW_KEY.
_bws_bootstrap="${HERMES_KEYRING_BOOTSTRAP:-$HOME/.hermes/bin/hermes-keyring-bootstrap.sh}"
_bws_bin="${BWS_BIN:-$HOME/.hermes/bin/bws}"
if [[ -x "$_bws_bootstrap" && -x "$_bws_bin" ]] && {
  [[ -z "${GROQ_API_KEY:-}" ]] || [[ -z "${CEREBRAS_API_KEY:-}" ]] || {
    [[ -z "${VERCEL_AI_GW_KEY:-}" ]] && [[ -z "${VERCEL_API_KEY:-}" ]]
  }
}; then
  while IFS= read -r _bws_line; do
    [[ "$_bws_line" == *=* ]] || continue
    _bws_key="${_bws_line%%=*}"
    _bws_value="${_bws_line#*=}"
    [[ -n "$_bws_key" && -n "$_bws_value" ]] || continue
    if [[ -z "${!_bws_key:-}" ]]; then
      export "${_bws_key}=${_bws_value}"
    fi
  done < <(
    eval "$("$_bws_bootstrap" 2>/dev/null || true)"
    [[ -n "${BWS_ACCESS_TOKEN:-}" ]] || exit 0
    "$_bws_bin" secret list \
      "${HERMES_BWS_PROJECT_ID:-ef35bed4-fc4f-42ab-a21f-b4bf013919b7}" \
      --server-url "${HERMES_BWS_SERVER_URL:-https://vault.bitwarden.com}" \
      --output json 2>/dev/null | python3 -c '
import json, sys
try:
    items = json.loads(sys.stdin.read() or "[]")
except Exception:
    raise SystemExit(0)
vault = {}
for item in items if isinstance(items, list) else []:
    if not isinstance(item, dict):
        continue
    key = item.get("key") or item.get("name")
    value = item.get("value")
    if key and isinstance(value, str) and value.strip() and "\n" not in value and "\r" not in value:
        vault[key] = value.strip()
aliases = (
    ("GROQ_API_KEY", "GROQ_API_KEY"),
    ("CEREBRAS_API_KEY", "CEREBRAS_API_KEY"),
    ("AI_GATEWAY_API_KEY", "VERCEL_AI_GW_KEY"),
    ("VERCEL_AI_GW_KEY", "VERCEL_AI_GW_KEY"),
    ("VERCEL_API_KEY", "VERCEL_AI_GW_KEY"),
)
emitted = set()
for src, dest in aliases:
    if dest in emitted or src not in vault:
        continue
    emitted.add(dest)
    print(f"{dest}={vault[src]}")
'
  )
fi
unset _bws_bootstrap _bws_bin _bws_line _bws_key _bws_value
unset _secrets_file _crush_file _hermes_auth _script_dir _omp_loader
