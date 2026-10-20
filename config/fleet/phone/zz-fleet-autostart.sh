# /etc/profile.d/zz-fleet-autostart.sh (Omalauncher guest; installed by
# scripts/fleet-phone-clone.sh). The guest has no systemd, so every login shell
# (the launcher's home Terminal tile, Tern's startup probe, new panes) starts the
# single fleet-phone-autostart watcher, which brings back tailscaled, sshd and
# `tern remote serve`. Silent and backgrounded: login shells never wait on it.
# Off switch: touch ~/.config/fleet/no-autostart
if [ -x "$HOME/.local/bin/fleet-phone-autostart" ] && [ ! -e "$HOME/.config/fleet/no-autostart" ]; then
    (setsid -f "$HOME/.local/bin/fleet-phone-autostart" --watch >/dev/null 2>&1 </dev/null)
fi
