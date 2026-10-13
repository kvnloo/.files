#!/bin/sh
# shot.sh - screenshot entry points for the Hyprland binds.
#
# Why this exists: the region binds call slurp, and slurp has no buttons.
# This script adds one "button": press the region bind a second time while
# the slurp crosshair is up, and the crosshair is replaced by satty
# (fullscreen, frozen frame, drawing toolbar).
#
#   shot.sh region-clip   slurp region -> clipboard   (second press: annotate)
#   shot.sh region-file   slurp region -> PNG file    (second press: annotate)
#   shot.sh annotate      frozen frame of the focused monitor -> satty
#
# In satty: draw; Enter or Ctrl+C = copy and close; Ctrl+S = save and close;
# Esc = close without output. The crop tool is the "select region" step.
set -u

dir=${SHOT_DIR:-$HOME/Pictures/screenshots}
# Time for the slurp overlay to leave the screen before the frame is taken.
settle=${SHOT_SETTLE:-0.06}

stamp() { date +%Y%m%d-%H%M%S; }

# Marker file: present while a region bind waits in slurp. A file test is a
# shell builtin, so the first press pays no process scan (pkill costs ~23 ms
# on this machine, measured).
mark=${XDG_RUNTIME_DIR:-/tmp}/shot-selecting

# Second press of a region bind: slurp is up, so switch to annotate mode.
# pkill returns 0 only when it found and signalled a slurp process; a stale
# marker (no slurp) falls through to a normal selection.
switch_if_selecting() {
    [ -e "$mark" ] || return 0
    rm -f "$mark"
    if pkill -x slurp; then
        exec "$0" annotate
    fi
}

# Run slurp with the marker set. A cancelled slurp (Esc, or killed by the
# second press) ends the script here. The old one-line bind ran wl-copy with
# empty input in that case.
select_region() {
    : >"$mark"
    geom=$(slurp)
    rc=$?
    rm -f "$mark"
    [ "$rc" -eq 0 ] || exit 0
}

annotate() {
    # Only one annotator at a time. A second request does nothing.
    pgrep -x satty >/dev/null && exit 0
    # Binds do not always get ~/.local/bin in PATH, so fall back to the path.
    satty=$(command -v satty || echo "$HOME/.local/bin/satty")

    # Wait for a killed slurp to exit, then for its overlay to be gone.
    n=0
    while pgrep -x slurp >/dev/null && [ "$n" -lt 50 ]; do
        sleep 0.01
        n=$((n + 1))
    done
    sleep "$settle"

    # Focused monitor: satty opens there, so the frame must be from there.
    mon=$(hyprctl monitors -j | jq -r '.[] | select(.focused) | .name')
    if [ -n "$mon" ]; then
        set -- -o "$mon"
    else
        set --
    fi

    mkdir -p "$dir"
    # ppm: no PNG encode on the capture side (21 ms against 111 ms, measured).
    # fullscreen current-screen: cover the monitor the frame came from.
    # brush: start with the pen. wl-copy: the image stays after satty closes.
    # early-exit: copy or save, then close, like the plain region bind.
    grim -t ppm "$@" - | "$satty" --filename - --fullscreen current-screen \
        --initial-tool brush --copy-command wl-copy \
        --early-exit copy --early-exit save --no-window-decoration \
        --output-filename "$dir/screenshot-%Y%m%d-%H%M%S.png"
}

case ${1:-} in
region-clip)
    switch_if_selecting
    select_region
    grim -g "$geom" - | wl-copy
    ;;
region-file)
    switch_if_selecting
    select_region
    mkdir -p "$dir"
    grim -g "$geom" "$dir/screenshot-$(stamp).png"
    ;;
annotate)
    annotate
    ;;
*)
    echo "usage: shot.sh region-clip|region-file|annotate" >&2
    exit 2
    ;;
esac
