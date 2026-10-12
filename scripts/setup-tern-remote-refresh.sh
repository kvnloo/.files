#!/usr/bin/env bash
# Install update recovery for an existing Tern system remote service.
set -euo pipefail
root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
if (( EUID != 0 )); then
  exec sudo /usr/bin/bash "$root/scripts/setup-tern-remote-refresh.sh"
fi

# Never install a second remote service or change its keys/access policy.
[[ "$(systemctl show tern-remote.service --property=LoadState --value)" == loaded ]]
[[ "$(systemctl show tern-remote.service --property=KillMode --value)" == process ]]
[[ -x /home/kvn/.local/bin/tern ]]
install -Dm755 "$root/scripts/tern-remote-refresh" /usr/local/libexec/tern-remote-refresh
for unit in tern-remote-refresh.service tern-remote-refresh.timer; do
  install -Dm644 "$root/config/systemd/system/$unit" "/etc/systemd/system/$unit"
done
systemctl daemon-reload
systemctl enable --now tern-remote-refresh.timer
systemctl start tern-remote-refresh.service
systemctl status tern-remote-refresh.timer --no-pager
