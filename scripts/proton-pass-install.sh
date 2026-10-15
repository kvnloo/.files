#!/usr/bin/env bash
# Install the Proton Pass wrapper and an entitlement-preserving source build.
set -euo pipefail

repo=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
src=${PASS_CLI_SRC:-$HOME/workspace/oss/pass-cli-main}
plan=false
skip_build=false

usage() {
  cat <<'HELP'
Usage: proton-pass-install.sh [--plan] [--skip-build] [--help]
Install user links and build pass-cli unless /usr/bin/pass-cli exists.
--plan        Print actions without changing files or running the CLI.
--skip-build  Install links only; report the version if a binary exists.
PASS_CLI_SRC defaults to ~/workspace/oss/pass-cli-main.
CARGO_TARGET_DIR defaults to ~/.cache/pass-cli-target.
RUSTUP_TOOLCHAIN defaults to 1.97.1-x86_64-unknown-linux-gnu.
HELP
}

for arg in "$@"; do
  case "$arg" in
    --plan) plan=true ;;
    --skip-build) skip_build=true ;;
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

link_file() {
  local source=$1 destination=$2 backup
  if [[ -L "$destination" && $(readlink -- "$destination") == "$source" ]]; then
    return
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
}

run mkdir -p -- "$HOME/.config/proton-pass" "$HOME/.local/bin"
link_file "$repo/config/proton-pass/env" "$HOME/.config/proton-pass/env"
link_file "$repo/scripts/pass-cli-wrapper" "$HOME/.local/bin/pass-cli"

if [[ -e /usr/bin/pass-cli ]]; then
  printf 'Using the installed /usr/bin/pass-cli; skipping build.\n'
elif "$skip_build"; then
  printf 'Skipping build as requested.\n'
else
  export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-$HOME/.cache/pass-cli-target}
  [[ "$CARGO_TARGET_DIR" == /* ]] || export CARGO_TARGET_DIR="$PWD/$CARGO_TARGET_DIR"
  export RUSTUP_TOOLCHAIN=${RUSTUP_TOOLCHAIN:-1.97.1-x86_64-unknown-linux-gnu}
  export PATH="$PATH:$HOME/.cargo/bin"
  if [[ ! -d "$src" ]]; then
    run mkdir -p -- "$(dirname -- "$src")"
    run git clone --branch main https://github.com/kvnloo/pass-cli.git "$src"
  fi
  # Default features only: never enable no-login-restriction.
  # The build keeps Proton's account entitlement check.
  if "$plan"; then
    printf 'Would build in %s with target %s and toolchain %s.\n' \
      "$src" "$CARGO_TARGET_DIR" "$RUSTUP_TOOLCHAIN"
    run cargo build --release -p pass-cli
  else
    (cd -- "$src" && cargo build --release -p pass-cli)
  fi
  run mkdir -p -- "$HOME/.local/lib/proton-pass"
  run install -m0755 -- "$CARGO_TARGET_DIR/release/pass-cli" "$HOME/.local/lib/proton-pass/pass-cli"
fi

if "$plan"; then
  run "$HOME/.local/bin/pass-cli" --version
elif [[ -x "$HOME/.local/lib/proton-pass/pass-cli" || -x /usr/bin/pass-cli || -x ${PASS_CLI_REAL:-/nonexistent} ]]; then
  "$HOME/.local/bin/pass-cli" --version
else
  printf 'Links installed; no binary available for a version check.\n'
fi
