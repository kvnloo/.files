#!/usr/bin/env bash
# Sync provider API keys into CodexBar config from secrets.env / Crush / env.
set -euo pipefail

SCRIPT_DIR="$(CDPATH= cd -- "$(dirname -- "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
# shellcheck disable=SC1091
source "$SCRIPT_DIR/codexbar-env.sh"

CODEXBAR="${CODEXBAR_BIN:-$(command -v codexbar || true)}"
if [[ -z "$CODEXBAR" ]]; then
  CODEXBAR="$HOME/.local/bin/codexbar"
fi

SECRETS_FILE="${CODEXBAR_SECRETS_FILE:-${XDG_CONFIG_HOME:-$HOME/.config}/codexbar/secrets.env}"
EXAMPLE_FILE="$SCRIPT_DIR/../config/codexbar/secrets.env.example"

declare -A PROVIDER_ENV=(
  [openrouter]=OPENROUTER_API_KEY
  [groq]=GROQ_API_KEY
  [cerebras]=CEREBRAS_API_KEY
  [vercel]=VERCEL_AI_GW_KEY
  [nous]=NOUS_API_KEY
)

mkdir -p "$(dirname "$SECRETS_FILE")"
if [[ ! -f "$SECRETS_FILE" && -f "$EXAMPLE_FILE" ]]; then
  cp "$EXAMPLE_FILE" "$SECRETS_FILE"
  chmod 600 "$SECRETS_FILE"
  echo "Created $SECRETS_FILE from example. Fill in your API keys, then re-run."
fi

if [[ -f "$SECRETS_FILE" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "$SECRETS_FILE"
  set +a
fi

synced=0
missing=()
for provider in "${!PROVIDER_ENV[@]}"; do
  env_name="${PROVIDER_ENV[$provider]}"
  value="${!env_name:-}"
  if [[ -z "$value" ]]; then
    missing+=("$provider ($env_name)")
    continue
  fi
  printf '%s' "$value" | "$CODEXBAR" config set-api-key --provider "$provider" --stdin --no-enable >/dev/null
  "$CODEXBAR" config enable --provider "$provider" >/dev/null
  synced=$((synced + 1))
  echo "synced $provider"
done

echo "Synced $synced provider key(s) into CodexBar config."
if ((${#missing[@]} > 0)); then
  echo "Still missing:"
  printf '  - %s\n' "${missing[@]}"
  echo "Add them to $SECRETS_FILE"
fi
