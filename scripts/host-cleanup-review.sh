#!/usr/bin/env bash
# Host cleanup review. Dry run by default: prints every action, changes nothing.
#   --apply               perform the safe actions (remove dangling ~/.omp symlinks)
#   --disable-loop-tick   with --apply: disable z0int-loop-tick.timer
#   --stop-executor       with --apply: scale the hermes-lab executor to 0
# Never uses pkill/killall. Never touches the master z0intelligence checkout.
set -uo pipefail

APPLY=0 DISABLE_TICK=0 STOP_EXEC=0
for a in "$@"; do
  case $a in
    --apply) APPLY=1 ;;
    --disable-loop-tick) DISABLE_TICK=1 ;;
    --stop-executor) STOP_EXEC=1 ;;
    -h|--help) sed -n '2,6p' "$0"; exit 0 ;;
    *) echo "unknown flag: $a" >&2; exit 2 ;;
  esac
done

MASTER=/mnt/zer0models/z0-wt/z0intelligence   # reported against only, never modified
KCTX=kind-hermes-lab NS=hermes-lab DEPLOY=z0intelligence-executor

mode() { ((APPLY)) && echo APPLY || echo DRY-RUN; }
run() { # run CMD... : print, and execute only under --apply
  if ((APPLY)); then echo "+ $*"; "$@"; else echo "[dry-run] would run: $*"; fi
}
section() { printf '\n== %s ==\n' "$1"; }

echo "host-cleanup-review mode: $(mode)"

section "1. Dangling symlinks under ~/.omp"
mapfile -d '' links < <(find "$HOME/.omp" -xtype l -print0 2>/dev/null)
if ((${#links[@]} == 0)); then echo "none found"; fi
for l in "${links[@]}"; do
  echo "dangling: $l -> $(readlink "$l")"
  run rm -- "$l"
done

section "2. z0int-loop-tick.timer"
systemctl --user list-timers --all 2>/dev/null | grep -E 'NEXT|z0int-loop-tick' || echo "timer not listed"
echo "option FIX:     review ExecStart in config/systemd/user/z0int-loop-tick.service (PYTHONPATH points at ~/workspace/z0intelligence-pinned/src, whose .git is broken), then:"
echo "                systemctl --user restart z0int-loop-tick.service"
echo "option DISABLE: systemctl --user disable --now z0int-loop-tick.timer"
if ((APPLY && DISABLE_TICK)); then
  run systemctl --user disable --now z0int-loop-tick.timer
else
  echo "[skipped] disable runs only with: --apply --disable-loop-tick"
fi

section "3. hermes-lab z0intelligence-executor"
kubectl --context "$KCTX" -n "$NS" get pods 2>&1 | grep -E 'NAME|executor' || echo "kubectl unavailable"
echo "stop command: kubectl --context $KCTX -n $NS scale deployment/$DEPLOY --replicas=0"
if ((APPLY && STOP_EXEC)); then
  run kubectl --context "$KCTX" -n "$NS" scale "deployment/$DEPLOY" --replicas=0
else
  echo "[skipped] scale runs only with: --apply --stop-executor"
fi

section "4. References to non-master z0intelligence checkouts (report only)"
echo "master checkout: $MASTER"
targets=("$HOME/.config/systemd/user" "$HOME/.omp/agent/extensions" "$HOME/.omp/extensions" "$HOME/.claude-home/hooks")
for f in "$HOME"/.claude-home/settings*.json; do [[ -e $f ]] && targets+=("$f"); done
existing=()
for t in "${targets[@]}"; do [[ -e $t ]] && existing+=("$t"); done
refs=$(mktemp)
# Any path containing a z0intelligence* component, minus the master path.
grep -RIEn --exclude-dir=node_modules -e '[A-Za-z0-9_./%~$-]*z0intelligence[A-Za-z0-9_.-]*[A-Za-z0-9_./-]*' "${existing[@]}" 2>/dev/null \
  | grep -v -F "$MASTER" \
  | grep -E '/(z0-wt|workspace|worktrees?|salvage)/|z0intelligence-[A-Za-z0-9]|%h/|~/' \
  | cut -c1-220 > "$refs"
[[ -s $refs ]] && cat "$refs" || echo "none found"
rm -f "$refs"
echo "(no files edited; fix these by hand after review)"

echo; echo "done ($(mode))"
