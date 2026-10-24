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
# Path tokens that name a z0int* checkout, minus the master checkout and the
# ~/.config/z0intelligence config dir (config, not a checkout). Catches z0int-canonical too.
# A path token (at a word boundary) with a directory segment starting "z0int",
# e.g. /x/z0intelligence-pinned/src or ~/tmp/z0int-canonical. State dirs like ~/.z0int are skipped.
PATH_RE='(?<![^\s="'"'"'`(])(/|%h/|~/)(?:[^\s:="'"'"'`/]+/)*z0int[\w-]*(?:/[^\s:="'"'"'`]*)?'
filter_paths() { grep -v -E "(^|[^A-Za-z0-9_])$MASTER(/|\$|[[:space:]])|\.config/z0intelligence(/|\$)" ; }
echo "-- raw files (grep, symlinks followed):"
raw=$(for t in "${existing[@]}"; do
  grep -RIPon --exclude-dir=node_modules -e "$PATH_RE" "$t" 2>/dev/null
done | filter_paths | sort -u | cut -c1-220)
[[ -n $raw ]] && echo "$raw" || echo "none found"
echo "-- effective z0int* units (systemctl --user cat, drop-ins applied):"
eff=0
for u in "$HOME"/.config/systemd/user/z0int*.service "$HOME"/.config/systemd/user/z0int*.timer; do
  [[ -e $u ]] || continue
  name=${u##*/}
  frag=$(systemctl --user show "$name" -p FragmentPath --value 2>/dev/null)
  # Apply drop-in semantics: "Key=" resets a list, WorkingDirectory keeps its last value.
  out=$(systemctl --user cat "$name" 2>/dev/null | awk '
      /^#/ || !/^[A-Za-z]+=/ { next }
      { k=$0; sub(/=.*/,"",k); v=substr($0,length(k)+2)
        if (v=="" || k=="WorkingDirectory") n[k]=0
        if (v!="") val[k,++n[k]]=$0
        if (!(k in seen)) { seen[k]=1; order[++m]=k } }
      END { for (i=1;i<=m;i++) for (j=1;j<=n[order[i]];j++) print val[order[i],j] }' \
        | grep -P "$PATH_RE" | filter_paths | cut -c1-200)
  [[ -n $out ]] && { echo "$name (fragment $frag):"; echo "$out" | sed 's/^/    /'; eff=1; }
done
((eff)) || echo "none found"
echo "-- enablement links whose target differs from the loaded unit file:"
mis=0
for w in "$HOME"/.config/systemd/user/*.wants/z0int*; do
  [[ -L $w ]] || continue
  frag=$(systemctl --user show "${w##*/}" -p FragmentPath --value 2>/dev/null)
  wt=$(readlink -f "$w"); ft=$(readlink -f "$frag" 2>/dev/null)
  [[ $wt != "$ft" ]] && { echo "$w -> $wt (loaded: $frag -> $ft)"; mis=1; }
done
((mis)) || echo "none found"
echo "(no files edited; fix these by hand after review)"

echo; echo "done ($(mode))"
