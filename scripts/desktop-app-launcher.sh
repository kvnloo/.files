#!/usr/bin/env bash
set -euo pipefail

if command -v qs >/dev/null 2>&1 &&
   qs -c noctalia-shell ipc call launcher toggle >/dev/null 2>&1; then
  exit 0
fi

exec rofi -show drun
