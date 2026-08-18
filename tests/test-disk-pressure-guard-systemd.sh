#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=$(mktemp -d); trap 'rm -rf -- "$root"' EXIT
mkdir -m 700 "$root/config"
cp "$repo/config/systemd/user/disk-pressure-guard.service" "$root/disk-pressure-guard.service"
cp "$repo/config/systemd/user/disk-pressure-guard.timer" "$root/disk-pressure-guard.timer"
cp "$repo/config/user-tmpfiles.d/disk-pressure-guard.conf" "$root/config/"
# Disposable first run begins with no parent or leaf. The install-phase tmpfiles
# contract creates both with the strict leaf mode before the service is considered.
[[ ! -e $root/state ]]
XDG_STATE_HOME="$root/state" systemd-tmpfiles --user --create "$root/config/disk-pressure-guard.conf"
[[ -d $root/state/disk-pressure-guard ]]
[[ $(stat -c %a "$root/state/disk-pressure-guard") == 700 ]]
python3 - "$root/disk-pressure-guard.service" "$repo/scripts/disk-pressure-guard.sh" "$root/state" <<'PY'
from pathlib import Path
import sys
p=Path(sys.argv[1]); s=p.read_text()
s=s.replace('%h/.local/bin/disk-pressure-guard',sys.argv[2]).replace('%h/.local/state',sys.argv[3])
p.write_text(s)
PY
systemd-analyze verify --user "$root/disk-pressure-guard.service" "$root/disk-pressure-guard.timer"
grep -q '^ReadWritePaths=.*/state$' "$root/disk-pressure-guard.service"
! grep -q '^ReadWritePaths=.*/disk-pressure-guard$' "$root/disk-pressure-guard.service"
# No live installation or activation occurred.
[[ $(systemctl --user show disk-pressure-guard.timer -p LoadState --value) == not-found ]]
[[ $(systemctl --user is-active disk-pressure-guard.timer 2>/dev/null || true) == inactive ]]
[[ $(systemctl --user is-enabled disk-pressure-guard.timer 2>/dev/null || true) == not-found ]]
echo PASS
