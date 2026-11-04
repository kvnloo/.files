#!/usr/bin/env bash
# Root half of the server-mode failsafe. Idempotent; run via pkexec. Installs repo copies and applies them live
# without restarting sshd or tailscaled (that would drop the remote session).
set -euo pipefail
src=$(cd "$(dirname "$0")/.." && pwd)/config/host/etc
install -Dm644 "$src/sysctl.d/98-failsafe.conf" /etc/sysctl.d/98-failsafe.conf
install -Dm644 "$src/systemd/system.conf.d/50-failsafe-watchdog.conf" /etc/systemd/system.conf.d/50-failsafe-watchdog.conf
for u in sshd tailscaled; do
  install -Dm644 "$src/systemd/system/$u.service.d/50-failsafe.conf" /etc/systemd/system/$u.service.d/50-failsafe.conf
done
install -Dm644 "$src/default/earlyoom" /etc/default/earlyoom
sysctl -q -w kernel.sysrq=1
systemctl daemon-reload
systemctl daemon-reexec            # picks up RuntimeWatchdogSec
for u in sshd tailscaled; do       # live equivalents of the drop-in, no restart
  systemctl set-property --runtime "$u.service" MemoryMin=96M
  for p in $(systemctl show -p MainPID --value "$u.service"); do [[ $p -gt 0 ]] && choom -p "$p" -n -1000 >/dev/null; done
done
systemctl restart earlyoom
echo "sysrq=$(sysctl -n kernel.sysrq) watchdog=$(systemctl show -p RuntimeWatchdogUSec --value) earlyoom=$(systemctl is-active earlyoom)"
