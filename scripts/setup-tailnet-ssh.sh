#!/usr/bin/env bash
set -euo pipefail

if [[ "$(uname -s)" != "Linux" ]]; then
  printf '%s\n' "Tailnet SSH onboarding currently supports Linux only."
  exit 0
fi

missing=()
command -v tailscale >/dev/null 2>&1 || missing+=(tailscale)
command -v sshd >/dev/null 2>&1 || missing+=(openssh)

if ((${#missing[@]})); then
  printf 'Install the missing package(s) first: %s\n' "${missing[*]}" >&2
  if command -v pacman >/dev/null 2>&1; then
    printf 'On CachyOS/Arch: sudo pacman -S --needed %s\n' "${missing[*]}" >&2
  fi
  exit 1
fi

printf '%s\n' \
  "" \
  "Tailnet remote access" \
  "---------------------" \
  "This enables Tailscale, Tailscale SSH, and OpenSSH now and at every boot." \
  "SSH will use your normal Linux account; run sudo after login when needed."

sudo systemctl enable --now tailscaled.service sshd.service

if ! tailscale status --self >/dev/null 2>&1; then
  printf '%s\n' "Tailscale is not connected. Follow the login URL below and select your existing tailnet."
  sudo tailscale up
else
  printf '%s\n' "Tailscale is already connected."
fi

sudo tailscale set --ssh
if ! tailscale debug prefs 2>/dev/null | grep -q '"RunSSH": true'; then
  printf '%s\n' "Tailscale SSH did not report as enabled." >&2
  exit 1
fi

tailnet_ip="$(tailscale ip -4 | head -n 1)"
tailnet_name="$(tailscale status --self --json 2>/dev/null | sed -n 's/.*"DNSName":"\([^"]*\)".*/\1/p' | sed 's/\.$//' || true)"

printf '%s\n' \
  "" \
  "Remote access is ready and will survive reboots." \
  "From another device signed into the same tailnet, connect with:"

if [[ -n "$tailnet_name" ]]; then
  printf '  tailscale ssh %s@%s\n' "$USER" "${tailnet_name%%.*}"
  printf '  ssh %s@%s\n' "$USER" "$tailnet_name"
fi
printf '  ssh %s@%s\n' "$USER" "$tailnet_ip"
printf '%s\n' "Then use 'sudo <command>' or 'sudo -i' only when needed."

if command -v portless >/dev/null 2>&1; then
  printf '%s\n' \
    "" \
    "Portless is installed. To share a development app privately with the tailnet:" \
    "  portless <app-name> --tailscale <dev-command>" \
    "Example: portless dashboard --tailscale npm run dev" \
    "Avoid --funnel unless you intentionally want a public internet URL."
fi
