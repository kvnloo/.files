#!/usr/bin/env bash
# The sole privileged entrypoint. Heavy archive conversion stays on the MBP.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
[[ ${1:-} == apply ]] || { printf 'Usage: sudo bash %s apply\n' "$0" >&2; exit 2; }
(( EUID == 0 )) || { printf 'Run this entrypoint with sudo.\n' >&2; exit 1; }
[[ $(hostname) == groot || $(hostname) == 0 ]] || { printf 'Run the fleet entrypoint on groot.\n' >&2; exit 1; }
user=kvn
home=$(getent passwd "$user" | cut -d: -f6)
uid=$(id -u "$user")
as_user() { runuser -u "$user" -- env HOME="$home" XDG_RUNTIME_DIR="/run/user/$uid" DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/$uid/bus" "$@"; }

# Use the repository implementation on both declared fleet hosts. Stage only
# the owned, credential-free configuration; never overwrite the MBP checkout.
remote_stage="$home/.local/state/infra-monitor-deploy"
as_user ssh -o BatchMode=yes mbp "mkdir -p '$remote_stage'"
tar -C "$root" -czf - config/netdata scripts/setup-netdata.sh | as_user ssh -o BatchMode=yes mbp "tar -xzf - -C '$remote_stage'"
# Kevin types the remote sudo password in this SSH terminal if required.
# Package transactions install only the requested monitoring dependencies.
as_user ssh -tt mbp "sudo /usr/bin/bash -c 'pacman -S --needed --noconfirm netdata smartmontools python libnotify && /usr/bin/bash \"$remote_stage/scripts/setup-netdata.sh\" apply mbp \"$user\" && runuser -u netdata -- /usr/local/libexec/netdata-desktop-notify --test WARNING'"
pacman -S --needed --noconfirm netdata smartmontools python libnotify atop
bash "$root/scripts/setup-netdata.sh" apply desktop "$user"
runuser -u netdata -- /usr/local/libexec/netdata-desktop-notify --test WARNING
as_user python3 "$root/scripts/setup-netdata-mcp.py"

# Install only root-owned executables into privileged service paths.
install -d -m755 /usr/local/lib/infra-monitor
install -m755 -o root -g root "$root/scripts/atop-rollup.py" /usr/local/lib/infra-monitor/atop-rollup.py
install -Dm644 -o root -g root "$root/config/atop/verified-retention.conf" /etc/systemd/system/atop.service.d/verified-retention.conf
install -Dm644 -o root -g root "$root/config/atop/default" /etc/default/atop
for unit in atop-rollup.service atop-rollup-retire.service atop-rollup.timer; do
  install -Dm644 -o root -g root "$root/config/systemd/system/$unit" "/etc/systemd/system/$unit"
done
# Preserve historic SQLite and raw ownership; rollup shards contain system-only
# metrics and are owned by the unprivileged fleet orchestrator.
install -d -m700 -o "$user" -g "$user" /mnt/zer0models/hw_monitor/rollups

# Ship the cleanup option, but keep it disabled pending the T3 Storage decision.
install -Dm755 -o "$user" -g "$user" "$root/scripts/nightly-cleanup.py" "$home/.local/lib/infra-monitor/nightly-cleanup.py"
for unit in nightly-cleanup.service nightly-cleanup.timer; do
  install -Dm644 -o "$user" -g "$user" "$root/config/systemd/user/$unit" "$home/.config/systemd/user/$unit"
done
as_user systemctl --user daemon-reload
as_user systemctl --user disable --now nightly-cleanup.timer

systemctl daemon-reload
systemctl enable --now atop.service atopacct.service atop-rotate.timer atop-rollup.timer
# Do not restart today's collector. Its next daily rotation reads retention=8;
# the age-only purge has already been removed by daemon-reload above.
# Conversion runs as kvn on the MBP, then OnSuccess performs verified retirement.
systemctl start --no-block atop-rollup.service
systemctl is-active netdata.service netdata-desktop-notify.socket atop-rollup.timer
printf '%s\n' 'Installed on both hosts. MBP conversion/verified retirement is scheduled now.' \
  'Inspect journalctl -u atop-rollup.service -u atop-rollup-retire.service and the retirement JSONL ledger.'
