#!/usr/bin/env bash
# Pull Bitwarden Secrets Manager into local env files. Never prints values.
set -euo pipefail

PROJECT_ID="${HERMES_BWS_PROJECT_ID:-ef35bed4-fc4f-42ab-a21f-b4bf013919b7}"
SERVER_URL="${HERMES_BWS_SERVER_URL:-https://vault.bitwarden.com}"
BOOTSTRAP="${HERMES_KEYRING_BOOTSTRAP:-$HOME/.hermes/bin/hermes-keyring-bootstrap.sh}"
BWS_BIN="${BWS_BIN:-$HOME/.hermes/bin/bws}"
CODEXBAR_SECRETS="${CODEXBAR_SECRETS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/codexbar/secrets.env}"
HERMES_ENV="${HERMES_ENV_FILE:-$HOME/.hermes/.env}"
OMP_ENV="${OMP_ENV_FILE:-$HOME/.omp/agent/.env}"
SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
SYNC_CREDENTIALS="${CODEXBAR_SYNC_CREDENTIALS:-$SCRIPT_DIR/codexbar-sync-credentials.sh}"

if [[ ! -x "$BOOTSTRAP" ]]; then
  echo "missing keyring bootstrap: $BOOTSTRAP" >&2
  exit 1
fi
if [[ ! -x "$BWS_BIN" ]]; then
  echo "missing bws: $BWS_BIN" >&2
  exit 1
fi

# shellcheck disable=SC1090
eval "$("$BOOTSTRAP")"
if [[ -z "${BWS_ACCESS_TOKEN:-}" ]]; then
  echo "BWS token not in GNOME Keyring. Run ~/.hermes/bin/hermes-store-bws-token.sh" >&2
  exit 1
fi

json="$("$BWS_BIN" secret list "$PROJECT_ID" --server-url "$SERVER_URL" --output json)"

python3 - "$json" "$CODEXBAR_SECRETS" "$HERMES_ENV" "$OMP_ENV" <<'PY'
import json
import os
import sys
from pathlib import Path

raw, *paths = sys.argv[1:]
items = json.loads(raw)
if not isinstance(items, list):
    raise SystemExit("unexpected bws list payload")

vault = {}
for item in items:
    if not isinstance(item, dict):
        continue
    key = item.get("key") or item.get("name")
    value = item.get("value")
    if key and isinstance(value, str) and value:
        vault[key] = value

aliases = {
    "AI_GATEWAY_API_KEY": ("AI_GATEWAY_API_KEY", "VERCEL_AI_GW_KEY"),
    "GROQ_API_KEY": ("GROQ_API_KEY",),
    "CEREBRAS_API_KEY": ("CEREBRAS_API_KEY",),
    "HERMES_CUSTOM_API_GROQ_COM_API_KEY": ("HERMES_CUSTOM_API_GROQ_COM_API_KEY",),
    "OPENROUTER_API_KEY": ("OPENROUTER_API_KEY",),
    "OPENCODE_ZEN_API_KEY": ("OPENCODE_ZEN_API_KEY",),
    "GOOGLE_API_KEY": ("GOOGLE_API_KEY",),
    "NVIDIA_API_KEY": ("NVIDIA_API_KEY",),
    "GITHUB_TOKEN": ("GITHUB_TOKEN",),
    "ANTHROPIC_TOKEN": ("ANTHROPIC_TOKEN",),
}

codexbar_keys = {
    "GROQ_API_KEY",
    "OPENROUTER_API_KEY",
    "OPENCODE_ZEN_API_KEY",
    "VERCEL_AI_GW_KEY",
    "AI_GATEWAY_API_KEY",
    "GOOGLE_API_KEY",
    "NVIDIA_API_KEY",
    "CEREBRAS_API_KEY",
}
hermes_keys = set(codexbar_keys) | {
    "HERMES_CUSTOM_API_GROQ_COM_API_KEY",
    "GITHUB_TOKEN",
    "ANTHROPIC_TOKEN",
}
omp_keys = set(codexbar_keys) | {"HERMES_CUSTOM_API_GROQ_COM_API_KEY"}

wanted = {}
for src, dests in aliases.items():
    if src not in vault:
        continue
    for dest in dests:
        wanted[dest] = vault[src]


def upsert(path: Path, allow: set[str]) -> tuple[list[str], list[str], list[str]]:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        text = path.read_text()
        mode = path.stat().st_mode
    else:
        text = ""
        mode = 0o600
    lines = text.splitlines()
    seen: set[str] = set()
    added: list[str] = []
    updated: list[str] = []
    unchanged: list[str] = []
    out: list[str] = []
    for line in lines:
        if not line or line.lstrip().startswith("#") or "=" not in line:
            out.append(line)
            continue
        key, old = line.split("=", 1)
        if key not in allow or key not in wanted:
            out.append(line)
            continue
        seen.add(key)
        new = wanted[key]
        if old == new:
            unchanged.append(key)
            out.append(line)
        else:
            updated.append(key)
            out.append(f"{key}={new}")
    for key in sorted(k for k in wanted if k in allow and k not in seen):
        added.append(key)
        out.append(f"{key}={wanted[key]}")
    body = "\n".join(out)
    if out:
        body += "\n"
    path.write_text(body)
    os.chmod(path, 0o600)
    return added, updated, unchanged


targets = [
    ("codexbar", Path(paths[0]), codexbar_keys),
    ("hermes", Path(paths[1]), hermes_keys),
    ("omp", Path(paths[2]), omp_keys),
]
print(f"vault_secrets {len(vault)}")
print("vault_names " + " ".join(sorted(vault)))
missing = sorted(name for name in aliases if name not in vault)
if missing:
    print("not_in_vault " + " ".join(missing))
for label, path, allow in targets:
    added, updated, unchanged = upsert(path, allow)
    print(
        f"{label} added={','.join(added) or '-'} "
        f"updated={','.join(updated) or '-'} "
        f"same={','.join(unchanged) or '-'}"
    )
PY

if [[ -x "$SYNC_CREDENTIALS" ]]; then
  "$SYNC_CREDENTIALS" || true
fi
