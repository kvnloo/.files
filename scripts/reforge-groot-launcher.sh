#!/usr/bin/env bash
set -euo pipefail

if command -v qs >/dev/null 2>&1 &&
   qs -c noctalia-shell ipc --any-display call plugin:reforge-groot toggle >/dev/null 2>&1; then
  exit 0
fi

exec alacritty --class reforge-groot -e /workspace/.files/scripts/update-all.sh
