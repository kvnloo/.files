#!/usr/bin/env bash
# install.sh -- host-drift applier for the network meta-optimizer (groot only).
#
# Copies the optimizer from this repo (the source of truth; D8) to the runtime
# location, installs the systemd --user timer, and writes the rollback line.
# Idempotent and reversible. Run ON GROOT:  bash install.sh [--enact]
#
#   (no flag)  -> deploy in observe-only DRY-RUN (NETOPT_DRYRUN=1)
#   --enact    -> also flip the service env to NETOPT_DRYRUN=0 (WP1-B; only after
#                 the preconditions in README "WP1-B" are verified + recorded)
#   --uninstall-> stop + disable the timer, remove units + runtime copy (rollback)
set -euo pipefail

SELF_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
RUNTIME="$HOME/.local/share/network-optimizer"
USER_UNITS="$HOME/.config/systemd/user"
BASE="$HOME/tmp/network"
BIN="$HOME/.local/bin"
ROLLBACK="$BASE/rollback.txt"

log() { printf '[install] %s\n' "$*"; }

uninstall() {
  systemctl --user stop network-optimizer.timer 2>/dev/null || true
  systemctl --user disable network-optimizer.timer 2>/dev/null || true
  rm -f "$USER_UNITS/network-optimizer.service" "$USER_UNITS/network-optimizer.timer"
  systemctl --user daemon-reload 2>/dev/null || true
  rm -f "$BIN/netopt-decide"
  rm -rf "$RUNTIME"
  log "uninstalled: timer stopped+disabled, units + runtime copy removed."
  log "state/decisions kept under $BASE (remove manually if desired)."
}

if [[ "${1:-}" == "--uninstall" ]]; then uninstall; exit 0; fi

mkdir -p "$RUNTIME" "$USER_UNITS" "$BASE/state" "$BIN"

# 1. Deploy code from repo -> runtime (source of truth stays the repo).
install -m 0644 "$SELF_DIR"/{laws.py,place.py,sampler.py,engine.py,optimize.py,decide.py} "$RUNTIME/"
install -m 0755 "$SELF_DIR/route-build" "$BIN/route-build"
# small convenience shim so the wrapper's ssh target finds decide.py
cat > "$BIN/netopt-decide" <<EOF
#!/usr/bin/env sh
exec /usr/bin/python3 "$RUNTIME/decide.py" "\$@"
EOF
chmod 0755 "$BIN/netopt-decide"

# 2. Install systemd --user units.
install -m 0644 "$SELF_DIR/systemd/network-optimizer.service" "$USER_UNITS/"
install -m 0644 "$SELF_DIR/systemd/network-optimizer.timer" "$USER_UNITS/"

if [[ "${1:-}" == "--enact" ]]; then
  sed -i 's/^Environment=NETOPT_DRYRUN=1/Environment=NETOPT_DRYRUN=0/' \
    "$USER_UNITS/network-optimizer.service"
  log "ENACT mode: NETOPT_DRYRUN=0 (WP1-B)."
else
  log "observe-only DRY-RUN (NETOPT_DRYRUN=1)."
fi

systemctl --user daemon-reload
systemctl --user enable --now network-optimizer.timer
loginctl enable-linger "$USER" 2>/dev/null || log "note: enable-linger needs auth; groot is always-on so the user instance runs."

# 3. Write the rollback line (owner-visible, logged).
{
  echo "# network meta-optimizer rollback -- written by install.sh on $(date -Is)"
  echo "# KILL SWITCH (halts enactment immediately; loop then only samples+logs):"
  echo "touch $BASE/network-optimizer.OFF"
  echo "# FULL ROLLBACK (stop + remove the unit and runtime copy):"
  echo "systemctl --user disable --now network-optimizer.timer"
  echo "bash $SELF_DIR/install.sh --uninstall"
  echo "# WP1-B wrapper rollback (stop routing new builds): remove route-build from PATH"
  echo "rm -f $BIN/route-build $BIN/netopt-decide"
} > "$ROLLBACK"
log "rollback written to $ROLLBACK"
log "done. status: systemctl --user status network-optimizer.timer"
