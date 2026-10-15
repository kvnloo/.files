#!/usr/bin/env bash
# Install passd for this user; custody units are opt-in and never started here.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src=${PASSD_SRC:-$HOME/workspace/oss/passd}
plan=false
custody=false

usage() {
  cat <<'HELP'
Usage: passd-install.sh [--plan] [--custody] [--help]
Install passd with uv. PASSD_SRC defaults to ~/workspace/oss/passd.
--plan     Print actions without installing or changing files.
--custody  Link user units on the custody host; print enable commands.
HELP
}

for arg in "$@"; do
  case "$arg" in
    --plan) plan=true ;;
    --custody) custody=true ;;
    --help|-h) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n' "$arg" >&2; usage >&2; exit 2 ;;
  esac
done

run() {
  if "$plan"; then
    printf 'Would run:'; printf ' %q' "$@"; printf '\n'
  else
    "$@"
  fi
}

if [[ ! -d "$src" ]]; then
  run mkdir -p -- "$(dirname -- "$src")"
  run git clone https://github.com/kvnloo/passd.git "$src"
fi
run uv tool install --force --editable "$src"

if "$custody"; then
  run mkdir -p -- "$HOME/.config/systemd/user"
  for unit in passd.service passd-gateway.service; do
    destination="$HOME/.config/systemd/user/$unit"
    source="$repo/config/systemd/user/$unit"
    if [[ -L "$destination" && $(readlink -- "$destination") == "$source" ]]; then
      continue
    fi
    if [[ -d "$destination" && ! -L "$destination" ]]; then
      printf 'Refusing to replace directory: %s\n' "$destination" >&2
      exit 1
    fi
    if [[ -e "$destination" && ! -L "$destination" ]]; then
      if "$plan"; then
        printf 'Would back up %s beside the original file.\n' "$destination"
      else
        backup=$(mktemp "${destination}.bak.XXXXXX")
        mv -- "$destination" "$backup"
        printf 'Backed up %s to %s\n' "$destination" "$backup"
      fi
    fi
    run ln -sfn -- "$source" "$destination"
  done
  cat <<'NEXT'
After initializing passd and storing the master password on groot, run:
  systemctl --user daemon-reload
  systemctl --user enable --now passd.service passd-gateway.service
NEXT
fi
