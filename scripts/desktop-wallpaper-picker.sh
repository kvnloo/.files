#!/usr/bin/env bash
set -euo pipefail

root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)

if command -v qs >/dev/null 2>&1 &&
   qs -c noctalia-shell ipc call wallpaper toggle >/dev/null 2>&1; then
  exit 0
fi

exec "$root/scripts/theme-switcher.sh" menu
