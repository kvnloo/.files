#!/usr/bin/env bash
# Update all installed apps across every package manager on the system.
# Skips any manager that isn't installed.

set -u

BOLD=$'\033[1m'
DIM=$'\033[2m'
GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
RESET=$'\033[0m'

failures=()
skipped=()

section() {
    printf '\n%s==>%s %s%s%s\n' "$GREEN" "$RESET" "$BOLD" "$1" "$RESET"
}

skip() {
    printf '%s--%s %s (not installed)%s\n' "$DIM" "$RESET" "$1" "$RESET"
    skipped+=("$1")
}

run() {
    local label="$1"; shift
    if "$@"; then
        return 0
    else
        printf '%s!!%s %s failed (exit %d)%s\n' "$RED" "$RESET" "$label" "$?" "$RESET"
        failures+=("$label")
        return 1
    fi
}

have() { command -v "$1" >/dev/null 2>&1; }

# Prime sudo credentials up front so paru (and pacman) don't stall mid-run.
# Skipped if there's no TTY (script being run non-interactively).
if [ -t 0 ] && have sudo; then
    sudo -v || { printf '%s!! sudo prime failed%s\n' "$RED" "$RESET"; exit 1; }
fi

# Arch + AUR (paru covers both)
if have paru; then
    section "paru — official repos + AUR"
    run "paru" paru -Syu
elif have yay; then
    section "yay — official repos + AUR"
    run "yay" yay -Syu
elif have pacman; then
    section "pacman — official repos only"
    run "pacman" sudo pacman -Syu
else
    skip "pacman/paru/yay"
fi

# Flatpak
if have flatpak; then
    section "flatpak"
    run "flatpak" flatpak update -y
else
    skip "flatpak"
fi

# Firmware
if have fwupdmgr; then
    section "fwupd — firmware"
    fwupdmgr refresh --force >/dev/null 2>&1 || true
    run "fwupd" fwupdmgr update -y
else
    skip "fwupd"
fi

# Rust toolchain
if have rustup; then
    section "rustup"
    run "rustup self" rustup self update
    run "rustup toolchains" rustup update
else
    skip "rustup"
fi

# Cargo-installed binaries (requires cargo-update)
if have cargo; then
    if cargo install-update --version >/dev/null 2>&1; then
        section "cargo install-update"
        run "cargo binaries" cargo install-update -a
    else
        skip "cargo-update (install with: paru -S cargo-update)"
    fi
fi

# pipx-installed Python apps
if have pipx; then
    section "pipx"
    run "pipx" pipx upgrade-all
else
    skip "pipx"
fi

# npm global packages
if have npm; then
    section "npm — global packages"
    npm_prefix=$(npm config get prefix 2>/dev/null)
    if [ -n "$npm_prefix" ] && [ ! -w "$npm_prefix/lib/node_modules" ] 2>/dev/null; then
        printf '%s-- npm prefix %s is not user-writable; skipping.%s\n' "$YELLOW" "$npm_prefix" "$RESET"
        printf '%s   Fix: npm config set prefix ~/.npm-global  (and add ~/.npm-global/bin to PATH)%s\n' "$DIM" "$RESET"
        skipped+=("npm (root-owned prefix)")
    else
        run "npm" npm update -g
    fi
else
    skip "npm"
fi

# Summary
printf '\n%s==>%s %sSummary%s\n' "$GREEN" "$RESET" "$BOLD" "$RESET"
if (( ${#failures[@]} == 0 )); then
    printf '%sAll updates completed successfully.%s\n' "$GREEN" "$RESET"
else
    printf '%sFailed: %s%s\n' "$RED" "${failures[*]}" "$RESET"
fi
if (( ${#skipped[@]} > 0 )); then
    printf '%sSkipped: %s%s\n' "$DIM" "${skipped[*]}" "$RESET"
fi

exit $(( ${#failures[@]} > 0 ? 1 : 0 ))
