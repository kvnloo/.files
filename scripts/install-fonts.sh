#!/usr/bin/env bash
# Install the Nerd Fonts and base families declared in packages/packages.toml.
# Desktop configs require JetBrainsMono Nerd Font and Roboto Mono.
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd -- "$SCRIPT_DIR/.." && pwd)"
FONT_DIR="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/dotfiles-nerd"
PRINT_ONLY=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --print) PRINT_ONLY=1 ;;
    -h|--help)
      printf 'usage: %s [--print]\n' "$0"
      exit 0
      ;;
    *)
      printf 'unknown arg: %s\n' "$1" >&2
      exit 2
      ;;
  esac
  shift
done

mapfile -t PACKAGES < <(python3 - "$REPO_ROOT/packages/packages.toml" <<'PY'
import sys
import tomllib
from pathlib import Path

data = tomllib.loads(Path(sys.argv[1]).read_text())
base_families = {"ttf-roboto-mono", "ttf-jetbrains-mono"}
for name in data["fonts"]["packages"]:
    if "nerd" in name or name in base_families:
        print(name)
PY
)

if [[ "$PRINT_ONLY" -eq 1 ]]; then
  printf '%s\n' "${PACKAGES[@]}"
  exit 0
fi

required_families=(
  "JetBrainsMono Nerd Font"
  "Roboto Mono"
  "FiraCode Nerd Font"
  "Iosevka Nerd Font"
)

family_present() {
  fc-list : family 2>/dev/null | grep -F -- "$1" >/dev/null
}

missing_pkgs=()
if command -v pacman >/dev/null 2>&1; then
  for pkg in "${PACKAGES[@]}"; do
    if ! pacman -Q "$pkg" >/dev/null 2>&1; then
      missing_pkgs+=("$pkg")
    fi
  done
else
  missing_pkgs=("${PACKAGES[@]}")
fi

install_user_fonts() {
  local tmp url pkg
  tmp="$(mktemp -d)"
  mkdir -p "$FONT_DIR" "$tmp/extract"
  mapfile -t urls < <(pacman -Sp "${missing_pkgs[@]}")
  for url in "${urls[@]}"; do
    curl -fsSL -o "$tmp/$(basename "$url")" "$url"
  done
  for pkg in "$tmp"/*.pkg.tar.zst; do
    tar --zstd -xf "$pkg" -C "$tmp/extract"
  done
  find "$tmp/extract" -type f \( -name '*.ttf' -o -name '*.otf' \) -exec cp -n {} "$FONT_DIR/" \;
  rm -rf "$tmp"
  fc-cache -f "$FONT_DIR"
}

if [[ ${#missing_pkgs[@]} -gt 0 ]]; then
  if command -v pacman >/dev/null 2>&1 && sudo -n true 2>/dev/null; then
    sudo pacman -S --needed --noconfirm "${missing_pkgs[@]}"
  else
    need_files=0
    for family in "${required_families[@]}"; do
      if ! family_present "$family"; then
        need_files=1
      fi
    done
    if [[ "$need_files" -eq 1 ]]; then
      if ! command -v pacman >/dev/null 2>&1; then
        printf 'pacman is required to resolve font packages\n' >&2
        exit 1
      fi
      printf 'no passwordless root; installing font files for this user\n'
      install_user_fonts
    else
      printf 'font families already visible to fontconfig; system packages not recorded (sudo unavailable)\n'
    fi
  fi
fi

missing_families=0
for family in "${required_families[@]}"; do
  if family_present "$family"; then
    printf 'ok   %s\n' "$family"
  else
    printf 'miss %s\n' "$family" >&2
    missing_families=1
  fi
done
exit "$missing_families"
