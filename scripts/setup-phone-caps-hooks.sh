#!/bin/sh
# Activate tracked O10 hooks without replacing an existing custom hook policy.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
current=$(git -C "$root" config --get core.hooksPath || true)
case "$current" in ''|.githooks|"$root/.githooks") ;; *) echo "Refusing to replace existing hooksPath: $current" >&2; exit 1 ;; esac
command -v z0-guard >/dev/null 2>&1 || { echo 'Install z0-guard before activating O10 hooks' >&2; exit 1; }
git -C "$root" config core.hooksPath "$root/.githooks"
printf '%s\n' 'O10 pre-commit and pre-push hooks enabled'
