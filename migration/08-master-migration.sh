#!/bin/bash
set -uo pipefail  # no -e, we handle errors per-stage

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
SCRIPT_DIR="$(dirname "$(readlink -f "$0")")"
DOTFILES="$(dirname "$SCRIPT_DIR")"
LOG_DIR="$DOTFILES/logs"
DATE=$(date +%Y%m%d-%H%M%S)
LOG_FILE="$LOG_DIR/master-migration-$DATE.log"
CHECKPOINT_FILE="$LOG_DIR/migration-checkpoint.txt"
mkdir -p "$LOG_DIR"

log() { echo -e "${GREEN}[$(date +'%Y-%m-%d %H:%M:%S')]${NC} $*" | tee -a "$LOG_FILE"; }
log_warn() { echo -e "${YELLOW}[$(date +'%Y-%m-%d %H:%M:%S')] WARNING:${NC} $*" | tee -a "$LOG_FILE"; }
log_error() { echo -e "${RED}[$(date +'%Y-%m-%d %H:%M:%S')] ERROR:${NC} $*" | tee -a "$LOG_FILE"; }
log_section() { echo -e "\n${BLUE}========== $* ==========\n${NC}" | tee -a "$LOG_FILE"; }

# --- Checkpoint system ---
save_checkpoint() {
    local stage="$1"
    echo "$stage:$(date +%s)" >> "$CHECKPOINT_FILE"
    log "Checkpoint saved: $stage"
}

is_stage_completed() {
    local stage="$1"
    [[ -f "$CHECKPOINT_FILE" ]] && grep -q "^$stage:" "$CHECKPOINT_FILE"
}

get_last_checkpoint() {
    if [[ -f "$CHECKPOINT_FILE" ]]; then
        local result
        result=$(tail -1 "$CHECKPOINT_FILE" | cut -d: -f1)
        echo "${result:-none}"
    else
        echo "none"
    fi
}

# Trap for clean interruption
trap 'log_warn "Migration interrupted. Resume with: $0"; exit 130' INT TERM

# --- Stage definitions ---
STAGES=(
    "install_packages"
    "deploy_dotfiles"
    "setup_audio"
    "setup_hyprland"
    "setup_dev_services"
    "verify"
)

STAGE_DESCRIPTIONS=(
    "Install system packages"
    "Deploy dotfiles and symlinks"
    "Configure audio (PipeWire DSP)"
    "Set up Hyprland window manager"
    "Set up dev services and Zsh"
    "Verify migration"
)

declare -A STAGE_TIMES

run_stage() {
    local stage="$1"
    local stage_start
    stage_start=$(date +%s)

    case "$stage" in
        install_packages)
            log_section "Stage 1/6: Install Packages"
            bash "$SCRIPT_DIR/01-install-packages.sh" 2>&1 | tee -a "$LOG_FILE"
            ;;
        deploy_dotfiles)
            log_section "Stage 2/6: Deploy Dotfiles"
            bash "$SCRIPT_DIR/02-deploy-dotfiles.sh" 2>&1 | tee -a "$LOG_FILE"
            ;;
        setup_audio)
            log_section "Stage 3/6: Setup Audio"
            bash "$SCRIPT_DIR/03-setup-audio.sh" 2>&1 | tee -a "$LOG_FILE"
            ;;
        setup_hyprland)
            log_section "Stage 4/6: Setup Hyprland"
            bash "$SCRIPT_DIR/04-setup-hyprland.sh" 2>&1 | tee -a "$LOG_FILE"
            ;;
        setup_dev_services)
            log_section "Stage 5/6: Setup Dev Services & Zsh"
            bash "$SCRIPT_DIR/05-setup-dev-services.sh" 2>&1 | tee -a "$LOG_FILE"
            local rc=$?
            if [[ $rc -ne 0 ]]; then
                return $rc
            fi
            bash "$SCRIPT_DIR/06-setup-zsh.sh" 2>&1 | tee -a "$LOG_FILE"
            ;;
        verify)
            log_section "Stage 6/6: Verify Migration"
            bash "$SCRIPT_DIR/07-verify-migration.sh" 2>&1 | tee -a "$LOG_FILE"
            ;;
        *)
            log_error "Unknown stage: $stage"
            return 1
            ;;
    esac

    local rc=$?
    local stage_end
    stage_end=$(date +%s)
    STAGE_TIMES["$stage"]=$(( stage_end - stage_start ))

    return $rc
}

print_banner() {
    local host kernel cur_date
    host=$(hostname)
    kernel=$(uname -r)
    cur_date=$(date '+%Y-%m-%d %H:%M:%S')

    echo -e "${BLUE}"
    echo "╔══════════════════════════════════════════════════════╗"
    echo "║           DOTFILES MASTER MIGRATION                 ║"
    echo "╠══════════════════════════════════════════════════════╣"
    printf "║  Host:     %-42s║\n" "$host"
    printf "║  Kernel:   %-42s║\n" "$kernel"
    printf "║  Date:     %-42s║\n" "$cur_date"
    printf "║  Dotfiles: %-42s║\n" "$DOTFILES"
    echo "╚══════════════════════════════════════════════════════╝"
    echo -e "${NC}"
}

print_summary() {
    local total_time="$1"
    echo ""
    log_section "MIGRATION SUMMARY"
    echo -e "${GREEN}┌──────────────────────────────────────────────────────┐${NC}"

    for i in "${!STAGES[@]}"; do
        local stage="${STAGES[$i]}"
        local desc="${STAGE_DESCRIPTIONS[$i]}"
        local elapsed="${STAGE_TIMES[$stage]:-skipped}"
        local status

        if is_stage_completed "$stage"; then
            if [[ "$elapsed" == "skipped" ]]; then
                status="${YELLOW}SKIPPED (resumed)${NC}"
            else
                status="${GREEN}DONE${NC} (${elapsed}s)"
            fi
        else
            status="${RED}NOT RUN${NC}"
        fi

        printf "${GREEN}│${NC}  %-4s %-30s %s\n" "$((i+1))." "$desc" "$status"
    done

    echo -e "${GREEN}├──────────────────────────────────────────────────────┤${NC}"
    local mins=$(( total_time / 60 ))
    local secs=$(( total_time % 60 ))
    printf "${GREEN}│${NC}  Total migration time: %dm %ds\n" "$mins" "$secs"
    echo -e "${GREEN}└──────────────────────────────────────────────────────┘${NC}"

    echo ""
    log "Manual verification steps recommended:"
    log "  1. Reboot and confirm Hyprland launches correctly"
    log "  2. Open a terminal and verify Zsh prompt + plugins"
    log "  3. Play audio to confirm PipeWire DSP pipeline"
    log "  4. Run 'docker ps' to verify dev services"
    log "  5. Check 'systemctl --user status' for user services"
}

usage() {
    echo "Usage: $0 [OPTIONS]"
    echo ""
    echo "Options:"
    echo "  --fresh       Ignore checkpoints and start from scratch"
    echo "  --dry-run     Print what would be done without executing"
    echo "  --stage N     Run only stage N (1-${#STAGES[@]})"
    echo "  -h, --help    Show this help message"
    echo ""
    echo "Stages:"
    for i in "${!STAGES[@]}"; do
        echo "  $((i+1)). ${STAGE_DESCRIPTIONS[$i]}"
    done
}

# --- Parse arguments ---
FRESH=false
DRY_RUN=false
SINGLE_STAGE=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --fresh)
            FRESH=true
            shift
            ;;
        --dry-run)
            DRY_RUN=true
            shift
            ;;
        --stage)
            if [[ $# -lt 2 ]]; then
                echo "Error: --stage requires a stage number"
                exit 1
            fi
            SINGLE_STAGE="$2"
            if [[ "$SINGLE_STAGE" -lt 1 || "$SINGLE_STAGE" -gt ${#STAGES[@]} ]]; then
                echo "Error: stage must be between 1 and ${#STAGES[@]}"
                exit 1
            fi
            shift 2
            ;;
        -h|--help)
            usage
            exit 0
            ;;
        *)
            echo "Unknown option: $1"
            usage
            exit 1
            ;;
    esac
done

# --- Main ---
main() {
    local migration_start
    migration_start=$(date +%s)

    print_banner

    # Handle fresh start
    if [[ "$FRESH" == true ]] && [[ -f "$CHECKPOINT_FILE" ]]; then
        log_warn "Removing existing checkpoint file (--fresh)"
        rm -f "$CHECKPOINT_FILE"
    fi

    # Check for existing checkpoint
    if [[ -f "$CHECKPOINT_FILE" ]] && [[ "$FRESH" == false ]] && [[ "$SINGLE_STAGE" -eq 0 ]]; then
        local last
        last=$(get_last_checkpoint)
        log_warn "Found existing checkpoint: last completed stage = $last"
        echo -en "${YELLOW}Resume from checkpoint? [Y/n/fresh]: ${NC}"
        read -r answer
        case "$answer" in
            n|N)
                log "Aborting. Use --fresh to start over."
                exit 0
                ;;
            fresh|f|F)
                log "Starting fresh migration"
                rm -f "$CHECKPOINT_FILE"
                ;;
            *)
                log "Resuming migration from checkpoint"
                ;;
        esac
    fi

    # Determine which stages to run
    local stages_to_run=()
    if [[ "$SINGLE_STAGE" -gt 0 ]]; then
        stages_to_run=("${STAGES[$((SINGLE_STAGE - 1))]}")
    else
        stages_to_run=("${STAGES[@]}")
    fi

    # Dry run mode
    if [[ "$DRY_RUN" == true ]]; then
        log_section "DRY RUN MODE"
        for i in "${!stages_to_run[@]}"; do
            local stage="${stages_to_run[$i]}"
            if is_stage_completed "$stage"; then
                log "[SKIP] $stage (already completed)"
            else
                log "[WOULD RUN] $stage"
            fi
        done
        log "Dry run complete. No changes made."
        exit 0
    fi

    # Execute stages
    local failed=false
    for i in "${!stages_to_run[@]}"; do
        local stage="${stages_to_run[$i]}"

        if is_stage_completed "$stage" && [[ "$SINGLE_STAGE" -eq 0 ]]; then
            log "Skipping $stage (already completed)"
            continue
        fi

        run_stage "$stage"
        local rc=$?

        if [[ $rc -ne 0 ]]; then
            log_error "Stage '$stage' failed with exit code $rc"
            echo -en "${YELLOW}Continue to next stage? [y/N]: ${NC}"
            read -r answer
            if [[ "$answer" =~ ^[Yy]$ ]]; then
                log_warn "Continuing despite failure in $stage"
                continue
            else
                log_error "Migration aborted at stage: $stage"
                failed=true
                break
            fi
        fi

        save_checkpoint "$stage"
    done

    local migration_end
    migration_end=$(date +%s)
    local total_time=$(( migration_end - migration_start ))

    print_summary "$total_time"

    if [[ "$failed" == true ]]; then
        log_error "Migration did not complete successfully."
        log "Re-run '$0' to resume from the last checkpoint."
        exit 1
    fi

    log "Migration completed successfully!"
    log "Checkpoint file: $CHECKPOINT_FILE"
}

main "$@"
