#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
nix_dir="${repo_root}/config/nix"
host="${1:-$(hostname)}"
profile="kvn@${host}"

if ! command -v nix >/dev/null 2>&1; then
  sudo pacman -S --needed nix
fi

sudo systemctl enable --now nix-daemon.socket

if getent group nix-users >/dev/null && ! id -nG "${USER}" | tr ' ' '\n' | grep -qx nix-users; then
  sudo usermod --append --groups nix-users "${USER}"
  printf '%s\n' \
    "Added ${USER} to nix-users." \
    "Log out and back in, then run this script again to activate Home Manager."
  exit 0
fi

# Make Nix available immediately when this is run before a fresh login.
if [[ -r /etc/profile.d/nix-daemon.sh ]]; then
  # shellcheck disable=SC1091
  source /etc/profile.d/nix-daemon.sh
fi

export NIX_CONFIG="experimental-features = nix-command flakes"

if [[ ! -f "${nix_dir}/hosts/${host}.nix" ]]; then
  printf 'No Home Manager host module exists for %s\n' "${host}" >&2
  printf 'Create %s/hosts/%s.nix or pass a known host name.\n' "${nix_dir}" "${host}" >&2
  exit 1
fi

nix run github:nix-community/home-manager -- \
  switch --flake "path:${nix_dir}#${profile}" --backup-extension hm-backup

printf 'Activated Home Manager profile %s\n' "${profile}"
