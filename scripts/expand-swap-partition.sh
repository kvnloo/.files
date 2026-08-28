#!/usr/bin/env bash
# Expand an existing swap partition to fill remaining space on its disk, then recreate swap.

set -euo pipefail

DRY_RUN=false
AUTO_YES=false
TARGET_GIB=100
TARGET_TOLERANCE_PCT=15
FORCE_NON_MATCH=0
TARGET_PARTITION=""
TARGET_LABEL=""

GREEN=$'\033[32m'
YELLOW=$'\033[33m'
RED=$'\033[31m'
DIM=$'\033[2m'
RESET=$'\033[0m'

usage() {
    cat <<'EOF'
Usage:
  sudo ./expand-swap-partition.sh [--partition /dev/nvme0n1p3] [--label swap]
                                  [--yes] [--dry-run] [--target-gib 100]
                                  [--force]

Options:
  --partition    Explicit swap partition path (defaults: auto-detect linux-swap partition)
  --label        Match swap partition by exact lsblk LABEL
  --target-gib   Expected current size in GiB (default: 100)
  --force        Skip size/position safety checks (use with caution)
  --yes          Run without confirmation prompts.
  --dry-run      Print commands only.
  --help         Show this help text.

Notes:
  - This script only supports swap partitions, not swap files.
  - It may fail if the swap partition is not the last partition on disk.
EOF
}

have() { command -v "$1" >/dev/null 2>&1; }

log() { printf '%s[info]%s %s\n' "$DIM" "$RESET" "$*"; }
warn() { printf '%s[warn]%s %s\n' "$YELLOW" "$RESET" "$*"; }
err() { printf '%s[error]%s %s\n' "$RED" "$RESET" "$*"; }

run_cmd() {
    local cmd=( "$@" )
    if "$DRY_RUN"; then
        printf '%s[DRY-RUN]%s ' "$YELLOW" "$RESET"
        printf '%q ' "${cmd[@]}"
        printf '\n'
        return 0
    fi
    "${cmd[@]}"
}

ask() {
    local question="$1"
    if "$AUTO_YES"; then
        return 0
    fi
    printf '%s[Y/n]%s %s ' "$YELLOW" "$RESET" "$question"
    read -r answer
    case "${answer:-y}" in
        [Yy]|[Yy][Ee][Ss]) return 0 ;;
        *) return 1 ;;
    esac
}

human_bytes() {
    local b=${1:-0}
    awk -v bytes="$b" 'BEGIN {
        split("B KiB MiB GiB TiB PiB", units)
        i = 1
        while (bytes >= 1024 && i < 6) {
            bytes /= 1024
            i++
        }
        printf "%.2f %s\n", bytes, units[i]
    }'
}

bytes_to_gib_floor() { awk -v b="${1:-0}" 'BEGIN { print int(b / 1024 / 1024 / 1024) }'; }

is_root() { [[ "$(id -u)" -eq 0 ]]; }
require_root() {
    if ! is_root; then
        err "run as root (or use: sudo)"
        exit 1
    fi
}

require_cmd() {
    local cmd="$1"
    have "$cmd" || { err "missing required command: $cmd"; exit 1; }
}

select_swap_partition() {
    local -a all_candidates=()
    local dev part_size part_label part_active count=0

    while IFS= read -r dev; do
        [[ -n "$dev" ]] || continue
        [[ -b "$dev" ]] || continue
        part_size=$(lsblk -b -nro SIZE "$dev")
        part_label=$(lsblk -nro LABEL "$dev" 2>/dev/null | head -n1 || true)
        all_candidates+=( "$dev" )
        CAND_SIZE["$dev"]="$part_size"
        CAND_LABEL["$dev"]="$part_label"
    done < <(lsblk -rpno NAME,TYPE,FSTYPE -b | awk '$2=="part" && ($3=="swap" || $3=="linux-swap"){print $1}')

    if ((${#all_candidates[@]} == 0)); then
        err "no linux-swap partitions found"
        exit 1
    fi

    if [[ -n "$TARGET_PARTITION" ]]; then
        for dev in "${all_candidates[@]}"; do
            if [[ "$dev" == "$TARGET_PARTITION" ]]; then
                SELECTED_SWAP="$dev"
                return 0
            fi
        done
        err "explicit --partition '$TARGET_PARTITION' is not a linux-swap partition"
        exit 1
    fi

    if [[ -n "$TARGET_LABEL" ]]; then
        for dev in "${all_candidates[@]}"; do
            if [[ "${CAND_LABEL[$dev]}" == "$TARGET_LABEL" ]]; then
                SELECTED_SWAP="$dev"
                return 0
            fi
        done
        err "no swap partition found with label '$TARGET_LABEL'"
        exit 1
    fi

    for dev in "${all_candidates[@]}"; do
        if swapon --show=NAME --noheadings 2>/dev/null | awk -v d="$dev" '$1==d {found=1} END {exit !found}'; then
            count=$((count + 1))
            active_candidates+=( "$dev" )
        fi
    done

    if (( count == 1 )); then
        SELECTED_SWAP="${active_candidates[0]}"
        return 0
    fi

    if (( count > 1 )); then
        warn "multiple active swap partitions found; auto-picking the first."
        SELECTED_SWAP="${active_candidates[0]}"
        return 0
    fi

    local near_target=()
    local target_min=$((TARGET_GIB - (TARGET_GIB * TARGET_TOLERANCE_PCT) / 100))
    local target_max=$((TARGET_GIB + (TARGET_GIB * TARGET_TOLERANCE_PCT) / 100))
    if (( target_min < 1 )); then target_min=1; fi

    for dev in "${all_candidates[@]}"; do
        local size_gib
        size_gib="$(bytes_to_gib_floor "${CAND_SIZE[$dev]}")"
        if (( size_gib >= target_min && size_gib <= target_max )); then
            near_target+=( "$dev" )
        fi
    done

    if (( ${#near_target[@]} == 1 )); then
        SELECTED_SWAP="${near_target[0]}"
        return 0
    fi

    if (( ${#all_candidates[@]} == 1 )); then
        SELECTED_SWAP="${all_candidates[0]}"
        return 0
    fi

    printf 'Detected %d swap partitions:\n' "${#all_candidates[@]}"
    local idx=1
    local active
    for dev in "${all_candidates[@]}"; do
        if swapon --show=NAME --noheadings 2>/dev/null | awk -v d="$dev" '$1==d {found=1} END {exit !found}'; then
            active="(active)"
        else
            active="(inactive)"
        fi
        printf '  %d) %s %s label=%s size=%s\n' \
            "$idx" "$dev" "$active" "${CAND_LABEL[$dev]}" "$(human_bytes "${CAND_SIZE[$dev]}")"
        idx=$((idx + 1))
    done

    if "$AUTO_YES"; then
        warn "multiple candidates and --yes set; using first one"
        SELECTED_SWAP="${all_candidates[0]}"
        return 0
    fi

    read -r -p "Select partition index: " sel
    if ! [[ "$sel" =~ ^[0-9]+$ ]] || (( sel < 1 || sel > ${#all_candidates[@]} )); then
        err "invalid selection: $sel"
        exit 1
    fi
    SELECTED_SWAP="${all_candidates[$((sel - 1))]}"
}

resolve_partition_number_and_disk() {
    local part="$1"
    local disk candidate_num

    if [[ "$part" =~ ^(/.+)p([0-9]+)$ ]]; then
        SWAP_DISK="${BASH_REMATCH[1]}"
        SWAP_PART_NUM="${BASH_REMATCH[2]}"
    elif [[ "$part" =~ ^(/.+)([0-9]+)$ ]]; then
        disk_candidate="${BASH_REMATCH[1]}"
        SWAP_PART_NUM="${BASH_REMATCH[2]}"
        SWAP_DISK="${disk_candidate}"
        if [[ "${SWAP_DISK}" == "/dev/" ]]; then
            SWAP_DISK="$part"
        fi
    else
        err "unable to resolve partition number from $part"
        exit 1
    fi

    if ! [[ -b "$SWAP_DISK" ]]; then
        SWAP_DISK="$(lsblk -nro PKNAME "$part" 2>/dev/null || true)"
    fi

    if [[ -z "$SWAP_DISK" || ! -b "$SWAP_DISK" ]]; then
        err "could not resolve parent disk for $part"
        exit 1
    fi
}

get_partition_end() {
    local disk="$1"
    local part_num="$2"
    local line num end
    while IFS=':' read -r num start end size fstype fslabel flags; do
        [[ "$num" == "$part_num" ]] || continue
        echo "$end"
        return 0
    done < <(parted -ms "$disk" unit s print)
    return 1
}

prepare_resize() {
    local part="$1"
    local size="${CAND_SIZE[$part]}"
    local label="${CAND_LABEL[$part]}"
    local size_gib
    size_gib="$(bytes_to_gib_floor "$size")"

    if [[ ! -b "$part" ]]; then
        err "swap target $part is not a block device"
        exit 1
    fi

    if [[ ! -b "$SWAP_DISK" ]]; then
        err "resolved disk $SWAP_DISK is not a block device"
        exit 1
    fi

    log "Target swap partition: $part"
    log "Current size: $(human_bytes "$size") (~${size_gib} GiB)"
    if [[ -n "$label" ]]; then
        log "Label: $label"
    fi

    local lower=$((TARGET_GIB - (TARGET_GIB * TARGET_TOLERANCE_PCT) / 100))
    local upper=$((TARGET_GIB + (TARGET_GIB * TARGET_TOLERANCE_PCT) / 100))
    (( lower < 1 )) && lower=1
    if (( FORCE_NON_MATCH == 0 && (size_gib < lower || size_gib > upper) )); then
        warn "selected partition is ${size_gib} GiB (expected around ${TARGET_GIB} GiB ±${TARGET_TOLERANCE_PCT}%)."
        ask "Continue anyway?" || exit 1
    fi

    local disk_end part_end part_end_raw
    local free_after
    local disk_sectors part_end_raw
    disk_sectors="$(blockdev --getsz "$SWAP_DISK")"
    part_end="$(get_partition_end "$SWAP_DISK" "$SWAP_PART_NUM" || true)"
    if [[ -z "$part_end" ]]; then
        err "could not read partition end for ${part} on ${SWAP_DISK}"
        exit 1
    fi
    part_end_raw="${part_end%s}"
    if (( part_end_raw >= disk_sectors - 1 )); then
        log "Partition is already at disk end. No resize needed."
        return 1
    fi

    free_after=$((disk_sectors - 1 - part_end_raw))
    if (( free_after <= 0 )); then
        warn "No contiguous free space detected after partition."
        ask "Try resize anyway?" || exit 1
    else
        log "Free sectors after partition: $free_after"
    fi

    return 0
}

main() {
    while [[ $# -gt 0 ]]; do
        case "${1:-}" in
            --partition) TARGET_PARTITION="${2:-}"; shift 2 ;;
            --label) TARGET_LABEL="${2:-}"; shift 2 ;;
            --target-gib) TARGET_GIB="${2:-100}"; shift 2 ;;
            --force) FORCE_NON_MATCH=1; shift ;;
            --yes) AUTO_YES=true; shift ;;
            --dry-run) DRY_RUN=true; shift ;;
            -h|--help) usage; exit 0 ;;
            --) shift; break ;;
            *)
                err "unknown argument: ${1:-}"
                usage
                exit 2
                ;;
        esac
    done

    if [[ ! "$TARGET_GIB" =~ ^[0-9]+$ ]]; then
        err "invalid --target-gib value: $TARGET_GIB"
        exit 2
    fi

    require_cmd lsblk
    require_cmd parted
    require_cmd partprobe
    require_cmd blockdev
    require_cmd swapon
    require_cmd swapoff
    require_cmd mkswap

    if ! "$DRY_RUN"; then
        require_root
    fi

    log "Scanning for linux-swap partitions..."
    declare -Ag CAND_SIZE
    declare -Ag CAND_LABEL
    declare -ag active_candidates
    declare SELECTED_SWAP=""
    declare SWAP_DISK=""
    declare SWAP_PART_NUM=""

    select_swap_partition
    resolve_partition_number_and_disk "$SELECTED_SWAP"

    if "$DRY_RUN"; then
        log "Dry-run mode enabled."
    fi

    local needs_resize=0
    if prepare_resize "$SELECTED_SWAP"; then
        needs_resize=1
        if ! ask "Proceed with resize + recreate swap for $SELECTED_SWAP?"; then
            log "Aborted by user."
            exit 0
        fi
    else
        needs_resize=0
        log "No resize required; still refreshing swap metadata."
    fi

    local had_active=0
    if swapon --show=NAME --noheadings 2>/dev/null | awk -v d="$SELECTED_SWAP" '$1==d {found=1} END {exit !found}'; then
        had_active=1
    fi

    if (( had_active == 1 )); then
        run_cmd swapoff "$SELECTED_SWAP"
        if "$DRY_RUN"; then
            log "Would disable swap on $SELECTED_SWAP"
        else
            log "swapoff succeeded on $SELECTED_SWAP"
        fi
    fi

    if (( needs_resize == 1 )); then
        log "Resizing partition $SWAP_PART_NUM on $SWAP_DISK to 100%."
        run_cmd parted -s "$SWAP_DISK" resizepart "$SWAP_PART_NUM" 100%
        run_cmd partprobe "$SWAP_DISK"
    else
        log "Skipping resize: partition already uses full available tail space."
    fi

    log "Recreating swap signature on $SELECTED_SWAP"
    run_cmd mkswap -f "$SELECTED_SWAP"
    log "Re-enabling swap: $SELECTED_SWAP"
    run_cmd swapon "$SELECTED_SWAP"
    run_cmd lsblk -r -o NAME,SIZE,TYPE,FSTYPE "$SELECTED_SWAP"

    log "Final swap status:"
    run_cmd swapon --show
    log "Done."
}

main "$@"
