#!/bin/sh
# Activate tracked O10 hooks without replacing an existing custom hook policy.
set -eu
root=$(CDPATH='' cd -- "$(dirname -- "$0")/.." && pwd)
current=$(git -C "$root" config --get core.hooksPath || true)
case "$current" in ''|.githooks|"$root/.githooks"|"$HOME/.local/lib/files-hooks/"*) ;; *) echo "Refusing to replace existing hooksPath: $current" >&2; exit 1 ;; esac
command -v z0-guard >/dev/null 2>&1 || { echo 'Install z0-guard before activating O10 hooks' >&2; exit 1; }
stamp=$(cat "$root/.githooks/pre-commit" "$root/.githooks/pre-push" | sha256sum)
stamp=${stamp%% *}
dest="$HOME/.local/lib/files-hooks/$stamp"
install -Dm755 "$root/.githooks/pre-commit" "$dest/pre-commit"
install -Dm755 "$root/.githooks/pre-push" "$dest/pre-push"
git -C "$root" config core.hooksPath "$dest"
printf 'O10 hooks enabled at %s\n' "$dest"
