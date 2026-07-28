#!/usr/bin/env bash
set -euo pipefail

cache_root=${XDG_CACHE_HOME:-$HOME/.cache}
cache_file=${CODEXBAR_CACHE_FILE:-$cache_root/codexbar-waybar/last.json}
wrapper=${CODEXBAR_WAYBAR_WRAPPER:-$HOME/.config/waybar/scripts/codexbar.sh}

if [[ ${1:-read} == refresh ]]; then
  if [[ ! -x $wrapper ]]; then
    printf 'CodexBar adapter is not executable: %s\n' "$wrapper" >&2
    exit 1
  fi
  "$wrapper" >/dev/null
fi

if [[ ! -r $cache_file ]]; then
  printf '[]\n'
  exit 0
fi

jq -c '
  if type != "array" then [] else map({
    provider,
    source,
    stale,
    error,
    usage: ((.usage // {}) | {
      updatedAt,
      identity,
      accountEmail,
      loginMethod,
      planName,
      plan,
      subscription,
      tier,
      accountType,
      primary,
      secondary,
      tertiary,
      extraRateWindows,
      extraUsage,
      extra,
      cost,
      costs
    }),
    extraUsage,
    cost,
    credits
  }) end
' "$cache_file"
