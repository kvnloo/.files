# /etc/profile.d/zz-fleet-autostart.sh (Omalauncher guest; installed by
# scripts/fleet-phone-keepalive.sh). The fleet supervisor normally starts from
# Omalauncher's PulseAudio session (/usr/local/bin/pulseaudio); a login shell only
# starts it when none runs, and the next PulseAudio start moves it into that session.
# Silent and detached: login shells never wait on it. Off switch:
# touch ~/.config/fleet/no-autostart
if [ -x "$HOME/.local/bin/fleet-phone-supervise" ] && [ ! -e "$HOME/.config/fleet/no-autostart" ]; then
    (setsid -f "$HOME/.local/bin/fleet-phone-supervise" up >/dev/null 2>&1 </dev/null)
fi
