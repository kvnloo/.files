#!/usr/bin/env bash
# Root half of server-mode's console: installed to /usr/local/libexec/server-mode-console (a root-owned copy, never
# the user-writable checkout) and run only by server-mode-console-{sleep,wake}.service.
#   sleep  stop SDDM, park the display on an empty VT (no getty is spawned above tty6) and power the panel off
#   wake   power the panel on and start SDDM; ctrl-alt-del.target pulls this in, so Ctrl+Alt+Del shows the login
set -u
VT=12
fb_blank() { local f; for f in /sys/class/graphics/fb*/blank; do [[ -w $f ]] && echo "$1" > "$f"; done; }
case "${1:-}" in
  sleep)
    systemctl stop sddm.service
    chvt "$VT"
    printf '\033[2J\033[H\033[?25l' > /dev/tty$VT        # clear, hide cursor: a woken panel shows only black
    TERM=linux setterm --blank force --powerdown 1 < /dev/tty$VT > /dev/tty$VT 2>/dev/null || true
    fb_blank 4                                           # FB_BLANK_POWERDOWN = DPMS off
    ;;
  wake)
    fb_blank 0
    TERM=linux setterm --blank poke < /dev/tty$VT > /dev/tty$VT 2>/dev/null || true
    systemctl start sddm.service
    ;;
  *) echo "usage: $0 sleep|wake" >&2; exit 2 ;;
esac
