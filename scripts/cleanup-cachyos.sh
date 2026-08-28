#!/usr/bin/env bash
# Clear unused system files and caches on CachyOS.

set -euo pipefail

GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'
RESET=$'\033[0m'

DRY_RUN=false
AUTO_YES=false
ENV_MAX_AGE_DAYS=90
declare -a ENV_ROOTS=()

usage() {
    cat <<'EOF'
Usage:
  cleanup-cachyos.sh [--yes] [--dry-run] [--env-days DAYS]
                     [--env-root PATH]

Options:
  --yes           Run without confirmation prompts.
  --dry-run       Show what would be run, then exit.
  --env-days DAYS Consider development environments inactive after DAYS
                  without directory access or modification (default: 90).
  --env-root PATH Scan PATH for stale environments. May be repeated.
                  Defaults to /workspace and $HOME/Projects when they exist.
  -h, --help      Show this help text.

Development environment cleanup detects:
  - Python .venv/venv directories containing pyvenv.cfg
  - node_modules directories
  - Conda environments containing conda-meta/history

Access time is only a best-effort signal. Filesystems mounted with noatime, or
relatime with infrequent updates, cannot provide an exact "last used" time.
EOF
}

have() { command -v "$1" >/dev/null 2>&1; }

log() {
    printf '%s%s%s\n' "$DIM" "$1" "$RESET"
}

run_cmd() {
    local cmd="$*"
    if "$DRY_RUN"; then
        printf '%s[DRY-RUN]%s %s\n' "$YELLOW" "$RESET" "$cmd"
        return 0
    fi
    log "$cmd"
    eval "$cmd"
}

run_argv() {
    if "$DRY_RUN"; then
        printf '%s[DRY-RUN]%s ' "$YELLOW" "$RESET"
        printf '%q ' "$@"
        printf '\n'
        return 0
    fi
    printf '%q ' "$@"
    printf '\n'
    "$@"
}

ask_confirm() {
    local prompt="$1"
    if "$AUTO_YES"; then
        return 0
    fi
    printf '%s[Y/n]%s %s ' "$YELLOW" "$RESET" "$prompt"
    read -r ans
    case "${ans:-y}" in
        [Yy]|[Yy][Ee][Ss]) return 0 ;;
        *) return 1 ;;
    esac
}

check_env() {
    if ! have pacman; then
        printf '%serror:%s pacman is required for this script\n' "$RED" "$RESET"
        exit 1
    fi

    if [ -f /etc/os-release ]; then
        # shellcheck disable=SC1091
        . /etc/os-release
        if [ "${ID:-}" != "cachyos" ] && [[ "${ID_LIKE:-}" != *"arch"* ]]; then
            log "warning: this machine is not detected as Arch/CachyOS; continuing anyway."
        fi
    fi

    if [ ! -w /var/cache/pacman/pkg ]; then
        printf '%swarning:%s /var/cache/pacman/pkg is not writable without elevated rights\n' "$YELLOW" "$RESET"
    fi
}

cleanup_orphans() {
    mapfile -t orphaned < <(pacman -Qtdq || true)
    if (( ${#orphaned[@]} == 0 )); then
        log "No orphaned packages found."
        return
    fi
    ask_confirm "Remove ${#orphaned[@]} orphaned packages (pacman -Rns)?" || return 0
    run_cmd "sudo pacman -Rns --noconfirm ${orphaned[*]}"
}

cleanup_pacman_cache() {
    ask_confirm "Clear pacman cache (pacman -Scc)?" || return 0
    run_cmd "sudo pacman -Scc --noconfirm"
}

cleanup_paccache() {
    if ! have paccache; then
        log "paccache not installed; skipping."
        return
    fi
    ask_confirm "Trim cached packages to one latest revision and remove uninstalled cache (paccache -rk1 -u)?" || return 0
    run_cmd "sudo paccache -rk1 -u"
}

cleanup_aur_cache() {
    local helper=""
    if have paru; then
        helper="paru"
    elif have yay; then
        helper="yay"
    else
        log "No AUR helper cache cleanup helper (paru/yay) found."
        return
    fi

    ask_confirm "Clear $helper cache (-Scc)?" || return 0
    run_cmd "sudo $helper -Scc --noconfirm"
}

cleanup_npx_cache() {
    local npm_cache npx_cache

    if ! have npm; then
        log "npm not installed; skipping npx cache cleanup."
        return
    fi

    npm_cache="$(npm config get cache 2>/dev/null || true)"
    if [[ -z "$npm_cache" || "$npm_cache" == "undefined" || ! -d "$npm_cache" ]]; then
        log "npm cache directory not found; skipping npx cache cleanup."
        return
    fi

    npm_cache="$(readlink -f -- "$npm_cache")"
    npx_cache="${npm_cache}/_npx"
    if [[ ! -d "$npx_cache" ]]; then
        log "No npx execution cache found at $npx_cache."
        return
    fi

    if [[ "${npx_cache##*/}" != "_npx" || "${npx_cache%/*}" != "$npm_cache" ]]; then
        printf '%serror:%s refusing unexpected npx cache path: %s\n' "$RED" "$RESET" "$npx_cache"
        return
    fi

    local cache_size
    cache_size="$(du -sh -- "$npx_cache" 2>/dev/null | awk '{print $1}')"
    ask_confirm "Clear reproducible npx execution cache at $npx_cache (${cache_size:-unknown})?" || return 0
    run_argv rm -rf -- "$npx_cache"
}

cleanup_flatpak() {
    if ! have flatpak; then
        log "flatpak not installed; skipping."
        return
    fi
    ask_confirm "Remove unused flatpak runtimes/apps (flatpak uninstall --unused)?" || return 0
    run_cmd "flatpak uninstall --unused -y"
}

cleanup_journal() {
    if ! have journalctl; then
        log "journalctl not installed; skipping."
        return
    fi
    ask_confirm "Vacuum journal logs older than 14 days (journalctl --vacuum-time=14d)?" || return 0
    run_cmd "sudo journalctl --vacuum-time=14d"
}

cleanup_dev_envs() {
    local -a roots=()
    local -a candidates=()
    local root path candidate
    local now cutoff atime mtime last_used age_days size
    declare -A seen_roots=()
    declare -A seen_candidates=()

    if (( ${#ENV_ROOTS[@]} > 0 )); then
        roots=( "${ENV_ROOTS[@]}" )
    else
        [[ -d /workspace ]] && roots+=( /workspace )
        [[ -d "${HOME}/Projects" ]] && roots+=( "${HOME}/Projects" )
    fi

    for root in "${roots[@]}"; do
        if [[ ! -d "$root" ]]; then
            log "Environment scan root does not exist; skipping: $root"
            continue
        fi
        root="$(readlink -f -- "$root")"
        [[ -n "${seen_roots[$root]:-}" ]] && continue
        seen_roots["$root"]=1

        while IFS= read -r -d '' path; do
            if [[ "${path##*/}" == "conda-meta" ]]; then
                candidate="${path%/conda-meta}"
                [[ -f "$path/history" ]] || continue
            else
                candidate="$path"
            fi
            [[ -n "${seen_candidates[$candidate]:-}" ]] && continue
            seen_candidates["$candidate"]=1
            candidates+=( "$candidate" )
        done < <(
            find "$root" -xdev \
                \( -type d \( \
                    -name .git -o -name .cache -o -name cache -o \
                    -name .Trash -o -name Trash -o -name .Trash-1000 -o \
                    -name SteamLibrary -o -name .pnpm-store -o -name .npm-cache -o \
                    -name tmp -o -name kvn-home -o -name hermes-home -o \
                    -name app.asar.unpacked \
                \) -prune \) -o \
                \( -type d -name node_modules -print0 -prune \) -o \
                \( -type d \( -name .venv -o -name venv \) -exec test -f '{}/pyvenv.cfg' \; -print0 -prune \) -o \
                \( -type d -name conda-meta -exec test -f '{}/history' \; -print0 -prune \) \
                2>/dev/null
        )
    done

    if (( ${#candidates[@]} == 0 )); then
        log "No Python, Node, or Conda development environments found."
        return
    fi

    now="$(date +%s)"
    cutoff=$((now - ENV_MAX_AGE_DAYS * 86400))
    log "Checking ${#candidates[@]} development environments; inactivity threshold: ${ENV_MAX_AGE_DAYS} days."

    for path in "${candidates[@]}"; do
        read -r atime mtime < <(stat -c '%X %Y' -- "$path")
        if (( atime > mtime )); then
            last_used="$atime"
        else
            last_used="$mtime"
        fi
        (( last_used <= cutoff )) || continue

        age_days=$(((now - last_used) / 86400))
        size="$(du -sh -- "$path" 2>/dev/null | awk '{print $1}')"
        printf '%s[stale-env]%s %s  size=%s  estimated-idle=%sd\n' \
            "$YELLOW" "$RESET" "$path" "${size:-unknown}" "$age_days"

        if ask_confirm "Delete this stale development environment?"; then
            run_argv rm -rf -- "$path"
        fi
    done
}

while [[ $# -gt 0 ]]; do
    case "${1:-}" in
        --yes) AUTO_YES=true ;;
        --dry-run) DRY_RUN=true ;;
        --env-days)
            [[ $# -ge 2 ]] || { printf '%serror:%s --env-days requires a value\n' "$RED" "$RESET"; exit 2; }
            ENV_MAX_AGE_DAYS="$2"
            shift
            ;;
        --env-root)
            [[ $# -ge 2 ]] || { printf '%serror:%s --env-root requires a path\n' "$RED" "$RESET"; exit 2; }
            ENV_ROOTS+=( "$2" )
            shift
            ;;
        -h|--help) usage; exit 0 ;;
        *) printf '%serror:%s unknown argument: %s\n' "$RED" "$RESET" "$1"; usage; exit 2 ;;
    esac
    shift
done

if [[ ! "$ENV_MAX_AGE_DAYS" =~ ^[0-9]+$ ]] || (( ENV_MAX_AGE_DAYS < 1 )); then
    printf '%serror:%s --env-days must be a positive integer\n' "$RED" "$RESET"
    exit 2
fi

printf '%s==>%s %sStarting CachyOS cleanup routine%s\n' "$GREEN" "$RESET" "$GREEN" "$RESET"
check_env

if "$DRY_RUN"; then
    log "dry-run mode enabled; no changes will be made."
fi

if ! "$AUTO_YES"; then
    ask_confirm "Proceed with cleanup actions now?"
fi

cleanup_orphans
cleanup_pacman_cache
cleanup_paccache
cleanup_aur_cache
cleanup_npx_cache
cleanup_flatpak
cleanup_journal
cleanup_dev_envs

printf '%s==>%s Cleanup complete.\n' "$GREEN" "$RESET"
