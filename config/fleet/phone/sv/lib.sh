# Sourced by every fleet service run script (busybox runsv, cwd = the service dir).
# busybox sh (applets instead of exec'ing coreutils under PRoot). Installed as ~/.local/share/fleet/sv/lib.sh by scripts/fleet-phone-keepalive.sh.
exec 9>&- 8>&- # never hold the supervisor's locks: only the supervisor and runsv may
exec 2>&1
umask 077
HOME=/root
XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/0}
PATH=/usr/local/sbin:/usr/local/bin:/usr/bin:/usr/sbin:$HOME/.local/bin
export HOME XDG_RUNTIME_DIR PATH
date +%s >./start # ./finish reads it to tell a crash loop from a long run

pid_alive() {
    case $1 in '' | *[!0-9]*) return 1 ;; esac
    kill -0 "$1" 2>/dev/null
}

# An instance this supervisor didn't start (the old watcher, Tern's launcher wrapper, a
# manual start) owns the port: block on it with a pidfd (util-linux waitpid, no polling)
# and start our own the moment it exits. Never kills it, so installing is seamless.
adopt() { # adopt <pid> <name>
    pid_alive "$1" || return 0
    echo "$(date '+%F %T') $2: unsupervised pid $1 is serving; taking over when it exits"
    exec waitpid "$1"
}

# The Tern binary remote serve runs: a launcher wrapper's TERN_BINARY first (the S25's
# ~/.local/bin/tern, which Tern's own start scripts compare against), then the
# launcher's Tern, then the newest under ~/.local/opt.
tern_binary() {
    w=$HOME/.local/bin/tern
    if [ -f "$w" ] && [ ! -L "$w" ] && [ "$(wc -c <"$w")" -lt 65536 ]; then
        b=$(sed -n 's/^TERN_BINARY=//p' "$w" | head -1)
        [ -n "$b" ] && [ -x "$b" ] && { echo "$b"; return; }
    fi
    [ -x /opt/tern/tern/tern ] && { echo /opt/tern/tern/tern; return; }
    ls -d "$HOME"/.local/opt/tern-*/tern/tern-bin 2>/dev/null | /usr/bin/sort -V | tail -1
}
