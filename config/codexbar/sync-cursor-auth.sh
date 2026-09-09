#!/usr/bin/env bash
# Sync Cursor auth into CodexBar config for Linux.
# Priority: CURSOR_COOKIE env/secrets.env → Cursor IDE state.vscdb accessToken.
set -euo pipefail

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}/codexbar"
CONFIG_PATH="${CODEXBAR_CONFIG_PATH:-$CONFIG_HOME/config.json}"
SECRETS_PATH="${CODEXBAR_SECRETS_PATH:-$CONFIG_HOME/secrets.env}"
CURSOR_DB="${CURSOR_STATE_DB:-$HOME/.config/Cursor/User/globalStorage/state.vscdb}"

if [[ -f "$SECRETS_PATH" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$SECRETS_PATH" && set +a
fi

cookie="${CURSOR_COOKIE:-}"

if [[ -z "$cookie" && -f "$CURSOR_DB" ]] && command -v sqlite3 >/dev/null 2>&1; then
  token="$(sqlite3 "$CURSOR_DB" "SELECT value FROM ItemTable WHERE key='cursorAuth/accessToken' LIMIT 1;" 2>/dev/null || true)"
  token="${token//$'\0'/}"
  token="$(printf '%s' "$token" | tr -d '\r\n')"
  if [[ -n "$token" ]]; then
    payload="$(printf '%s' "$token" | cut -d. -f2 | tr '_-' '/+')"
    pad=$(( (4 - ${#payload} % 4) % 4 ))
    if (( pad > 0 )); then payload="${payload}$(printf '=%.0s' $(seq 1 "$pad"))"; fi
    sub="$(printf '%s' "$payload" | base64 -d 2>/dev/null | jq -r '.sub // empty' 2>/dev/null || true)"
    user_id="${sub##*|}"
    if [[ -n "$user_id" ]]; then
      cookie="WorkosCursorSessionToken=${user_id}%3A%3A${token}"
    fi
  fi
fi

if [[ -z "$cookie" ]]; then
  echo "cursor-auth: no session (sign into Cursor IDE or set CURSOR_COOKIE in $SECRETS_PATH)" >&2
  exit 1
fi

command -v jq >/dev/null 2>&1 || { echo "cursor-auth: jq required" >&2; exit 1; }

tmp="$(mktemp)"
jq --arg cookie "$cookie" '
  .providers = (.providers | map(
    if .id == "cursor" then
      . + {enabled: true, source: "auto", cookieSource: "manual", cookieHeader: $cookie}
    else . end
  ))
' "$CONFIG_PATH" > "$tmp"
mv "$tmp" "$CONFIG_PATH"
chmod 600 "$CONFIG_PATH" 2>/dev/null || true
echo "cursor-auth: synced cookie into $CONFIG_PATH"
