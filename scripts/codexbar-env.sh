#!/usr/bin/env bash
# Load CodexBar provider credentials for the Linux CLI wrapper.
# Priority: existing env > ~/.config/codexbar/secrets.env > Crush provider refs.

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

unset _secrets_file _crush_file
