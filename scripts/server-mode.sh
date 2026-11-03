#!/usr/bin/env bash
# server-mode: run groot headless while the owner drives all work from the phone (t3os-style "personal server").
#
#   server-mode audit        memory by unit/scope, GUI vs headless, no changes
#   server-mode on [--yes]   stop the graphical session (Hyprland + every app it launched) and leftover GUI app scopes
#   server-mode off          clear the flag; the desktop returns on the next login at the console (tty1/SDDM)
#   server-mode status
#
# Kept running: every user service (linger is on), so Hermes, t3 serve, tern daemon, tailscale, agents, docker,
# k3s and dev servers survive. Only GUI processes stop. Nothing is killed by pattern: units are stopped by name,
# leftover processes only by PID after checking they belong to a GUI unit.
set -u
STATE_DIR=${XDG_STATE_HOME:-$HOME/.local/state}/server-mode
ACTIVE=$STATE_DIR/active
LOG=$STATE_DIR/log.jsonl
GUI_UNIT=wayland-wm@hyprland.desktop.service
mkdir -p "$STATE_DIR"

avail_mb() { awk '/MemAvailable/{print int($2/1024)}' /proc/meminfo; }

audit() {
  python3 - "$@" <<'PY'
import os, re, collections, sys
gui_markers = ("wayland-wm@", "app-", "graphical", "xdg-desktop-portal", "noctalia", "waybar", "swww", "hyprpaper",
               "linux-wallpaperengine", "kdeconnect", "at-spi")
units = collections.defaultdict(lambda: {"rss": 0, "swap": 0, "n": 0, "top": (0, "")})
for p in os.listdir("/proc"):
    if not p.isdigit():
        continue
    try:
        st = open(f"/proc/{p}/status").read()
        if not re.search(r"Uid:\s+%d\b" % os.getuid(), st) and os.getuid() != 0:
            pass
        cg = open(f"/proc/{p}/cgroup").read().strip().split("::")[-1]
        rss = int(re.search(r"VmRSS:\s+(\d+)", st).group(1)) if "VmRSS" in st else 0
        swap = int(re.search(r"VmSwap:\s+(\d+)", st).group(1)) if "VmSwap" in st else 0
        cmd = open(f"/proc/{p}/cmdline", "rb").read().replace(b"\0", b" ").decode(errors="replace").strip()
    except Exception:
        continue
    unit = next((x for x in reversed(cg.split("/")) if x.endswith((".service", ".scope"))), cg or "?")
    u = units[unit]
    u["rss"] += rss; u["swap"] += swap; u["n"] += 1
    if rss + swap > u["top"][0]:
        u["top"] = (rss + swap, cmd[:70])
tot_gui = tot = 0
rows = sorted(units.items(), key=lambda kv: -(kv[1]["rss"] + kv[1]["swap"]))
print(f"{'kind':8} {'unit':52} {'rss_mb':>7} {'swap_mb':>7} {'n':>4}  biggest process")
for name, u in rows[:int(sys.argv[1]) if len(sys.argv) > 1 else 40]:
    gui = any(m in name for m in gui_markers)
    print(f"{'GUI' if gui else 'server':8} {name[:52]:52} {u['rss']//1024:7d} {u['swap']//1024:7d} {u['n']:4d}  {u['top'][1]}")
for name, u in units.items():
    t = u["rss"] + u["swap"]; tot += t
    if any(m in name for m in gui_markers):
        tot_gui += t
print(f"\nGUI-attributable: {tot_gui//1024} MB of {tot//1024} MB resident+swap (process RSS, shared pages double-count)")
PY
}

gui_scopes() {
  systemctl --user list-units --type=scope --state=running --no-legend --plain 2>/dev/null \
    | awk '{print $1}' | grep -E '^app-.*\.scope$' | grep -v -E '^app-(tmux|ssh)' || true
}

on() {
  local yes=${1:-}
  local before; before=$(avail_mb)
  if [[ $yes != --yes ]]; then
    echo "This stops Hyprland and every GUI app (Chrome, the tern window, Xwayland, KDE Connect, clipboard watcher)."
    echo "Unsaved work in GUI apps is lost. Re-run with --yes to proceed."; return 2
  fi
  if [[ $(loginctl show-user "$USER" -p Linger --value 2>/dev/null) != yes ]]; then
    echo "refusing: linger is off, so stopping the last session could stop user services (Hermes, t3)"; return 1
  fi
  printf '%s\n' "$(date -Is)" > "$ACTIVE"
  local stopped=()
  if systemctl --user is-active --quiet "$GUI_UNIT"; then
    systemctl --user stop "$GUI_UNIT" && stopped+=("$GUI_UNIT")
  fi
  local s
  for s in $(gui_scopes); do
    systemctl --user stop "$s" && stopped+=("$s")
  done
  systemctl --user stop graphical-session.target >/dev/null 2>&1 || true
  sleep 3
  local after; after=$(avail_mb)
  printf '{"at":"%s","action":"on","avail_before_mb":%s,"avail_after_mb":%s,"stopped":"%s"}\n' \
    "$(date -Is)" "$before" "$after" "${stopped[*]:-}" >> "$LOG"
  echo "server mode ON: stopped ${#stopped[@]} unit(s); MemAvailable ${before} -> ${after} MB"
}

off() {
  rm -f "$ACTIVE"
  printf '{"at":"%s","action":"off"}\n' "$(date -Is)" >> "$LOG"
  echo "server mode OFF. Log in at the console (tty1 or SDDM) to start Hyprland again; nothing else needs restoring."
}

status() {
  if [[ -e $ACTIVE ]]; then echo "server mode: ON since $(cat "$ACTIVE")"; else echo "server mode: off"; fi
  systemctl --user is-active --quiet "$GUI_UNIT" && echo "graphical session: running" || echo "graphical session: stopped"
  echo "MemAvailable: $(avail_mb) MB"
}

case "${1:-status}" in
  audit) audit "${2:-40}" ;;
  on) on "${2:-}" ;;
  off) off ;;
  status) status ;;
  *) echo "usage: server-mode audit|on [--yes]|off|status" >&2; exit 2 ;;
esac
