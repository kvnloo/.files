#!/usr/bin/env bash
set -euo pipefail
repo=$(cd -- "$(dirname -- "$0")/.." && pwd)
root=$(mktemp -d)
trap 'rm -rf -- "$root"' EXIT
mkdir -m 700 "$root/state"
cp "$repo/config/systemd/user/disk-pressure-guard.service" "$root/disk-pressure-guard.service"
cp "$repo/config/systemd/user/disk-pressure-guard.timer" "$root/disk-pressure-guard.timer"
python3 - "$root/disk-pressure-guard.service" "$repo/scripts/disk-pressure-guard.sh" "$root/state" <<'PY'
from pathlib import Path
import sys
p = Path(sys.argv[1])
s = p.read_text().replace('%h/.local/bin/disk-pressure-guard', sys.argv[2]).replace('%h/.local/state/disk-pressure-guard', sys.argv[3])
p.write_text(s)
PY
systemd-analyze verify --user "$root/disk-pressure-guard.service" "$root/disk-pressure-guard.timer"
# Lifecycle truth for this checkout: fixtures are valid, but no real unit is installed or enabled.
[[ $(systemctl --user show disk-pressure-guard.timer -p LoadState --value) == not-found ]]
[[ $(systemctl --user is-active disk-pressure-guard.timer 2>/dev/null || true) == inactive ]]
[[ $(systemctl --user is-enabled disk-pressure-guard.timer 2>/dev/null || true) == not-found ]]
echo PASS
