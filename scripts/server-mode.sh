#!/usr/bin/env bash
# server-mode: run groot as a personal server driven from the phone, with the display off.
#
#   server-mode audit        memory by unit/scope, GUI vs headless, no changes
#   server-mode on [--yes]   stop Hyprland (the graphical session) and turn the display off. Survives reboots until `off`.
#   server-mode off          display back on at the SDDM login; logging in starts Hyprland again
#   server-mode status
#   server-mode failsafe     check the root failsafe (SysRq, hardware watchdog, earlyoom, sshd/tailscaled protection)
#   server-mode screen-off   just the display part of `on`, without setting the flag
#
# Only the Hyprland unit (and what dies with the compositor) stops. Other app scopes and every user service keep
# running (linger is on): Hermes, t3 serve, tern daemon, tailscale, agents, docker, k3s, dev servers. SDDM is then
# stopped and the panel powered down on an empty VT; only Ctrl+Alt+Del at the keyboard (ctrl-alt-del.target)
# brings the login screen back, other keys leave it dark.
set -u
STATE_DIR=${XDG_STATE_HOME:-$HOME/.local/state}/server-mode
ACTIVE=$STATE_DIR/active
LOG=$STATE_DIR/log.jsonl
GUI_UNIT=${SERVER_MODE_GUI_UNIT:-wayland-wm@hyprland.desktop.service}
mkdir -p "$STATE_DIR"

ROOT_FIX="sudo $(cd "$(dirname "$(readlink -f "$0")")" && pwd)/server-mode-failsafe-root.sh"

# Remote access is the only way back in once the desktop is gone; check it before stopping anything.
remote_ok() {
  local bad=()
  systemctl is-active --quiet sshd || bad+=("sshd inactive")
  systemctl is-active --quiet tailscaled || bad+=("tailscaled inactive")
  tailscale ip -4 >/dev/null 2>&1 || bad+=("no tailscale IPv4")
  ((${#bad[@]} == 0)) || { echo "refusing: ${bad[*]}"; return 1; }
}

failsafe() {
  local miss=0 v
  v=$(sysctl -n kernel.sysrq); [[ $v == 1 ]] && echo "ok   SysRq=1 (Alt+SysRq+F kills the biggest process, R-E-I-S-U-B reboots)" || { echo "MISS SysRq=$v (keyboard recovery dead)"; miss=1; }
  v=$(systemctl show -p RuntimeWatchdogUSec --value); [[ $v != 0 && $v != infinity ]] && echo "ok   hardware watchdog $v" || { echo "MISS hardware watchdog off (a hang needs a power cycle)"; miss=1; }
  grep -q -- '-s 100' /etc/default/earlyoom && echo "ok   earlyoom fires on RAM alone" || { echo "MISS earlyoom waits for swap (zram livelock not caught)"; miss=1; }
  for u in sshd tailscaled; do
    v=$(cat /proc/"$(systemctl show -p MainPID --value $u)"/oom_score_adj 2>/dev/null)
    [[ ${v:-0} -le -900 ]] && echo "ok   $u oom_score_adj=$v" || { echo "MISS $u oom_score_adj=${v:-?}"; miss=1; }
  done
  ((miss)) && echo "apply (root, idempotent, no sshd/tailscaled restart): $ROOT_FIX"
  return $miss
}

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

# Display off on an empty VT with SDDM stopped; Ctrl+Alt+Del at the keyboard brings the login back.
screen_off() {
  systemctl start server-mode-console-sleep.service \
    && echo "screen off: Ctrl+Alt+Del at the keyboard shows the login screen" \
    || echo "warning: screen not turned off; install the console units: $ROOT_FIX"
}

# Re-applies screen_off after a reboot while the flag is set (user unit; linger starts it at boot).
RESTORE_UNIT=server-mode-restore.service
ensure_restore_unit() {
  local src; src=$(cd "$(dirname "$(readlink -f "$0")")/.." && pwd)/config/systemd/user/$RESTORE_UNIT
  systemctl --user is-enabled --quiet "$RESTORE_UNIT" 2>/dev/null && return
  systemctl --user link "$src" >/dev/null && systemctl --user enable "$RESTORE_UNIT" >/dev/null 2>&1
}

on() {
  local before; before=$(avail_mb)
  if systemctl --user is-active --quiet "$GUI_UNIT" && [[ ${1:-} != --yes ]]; then
    echo "This stops Hyprland; windows that need the compositor (browser, tern window) close. Re-run with --yes."
    return 2
  fi
  if [[ $(loginctl show-user "$USER" -p Linger --value 2>/dev/null) != yes ]]; then
    echo "refusing: linger is off, so stopping the last session could stop user services (Hermes, t3)"; return 1
  fi
  remote_ok || return 1
  failsafe || echo "warning: root failsafe incomplete; continuing"
  printf '%s\n' "$(date -Is)" > "$ACTIVE"
  ensure_restore_unit
  local stopped=""
  if systemctl --user is-active --quiet "$GUI_UNIT"; then
    systemctl --user stop "$GUI_UNIT" && stopped=$GUI_UNIT
  fi
  systemctl --user stop graphical-session.target >/dev/null 2>&1 || true
  screen_off
  sleep 3
  printf '{"at":"%s","action":"on","avail_before_mb":%s,"avail_after_mb":%s,"stopped":"%s"}\n' \
    "$(date -Is)" "$before" "$(avail_mb)" "$stopped" >> "$LOG"
  echo "MemAvailable ${before} -> $(avail_mb) MB${stopped:+; stopped $stopped}"
  if [[ ${DBUS_SESSION_BUS_ADDRESS:-} == *"/tmp/dbus-"* ]]; then
    echo "note: this shell used the desktop D-Bus; run: export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus"
  fi
  echo "server mode ON. Way back in: ssh $USER@$(tailscale ip -4 2>/dev/null | head -1) | Ctrl+Alt+Del at the keyboard"
}

off() {
  rm -f "$ACTIVE"
  systemctl start server-mode-console-wake.service
  printf '{"at":"%s","action":"off"}\n' "$(date -Is)" >> "$LOG"
  echo "server mode OFF: SDDM login on screen; logging in starts Hyprland."
}

status() {
  if [[ -e $ACTIVE ]]; then echo "server mode: ON since $(cat "$ACTIVE")"; else echo "server mode: off"; fi
  systemctl --user is-active --quiet "$GUI_UNIT" && echo "graphical session: running" || echo "graphical session: not started"
  echo "MemAvailable: $(avail_mb) MB"
}

case "${1:-status}" in
  audit) audit "${2:-40}" ;;
  on) on "${2:-}" ;;
  off) off ;;
  status) status ;;
  failsafe) failsafe ;;
  screen-off) screen_off ;;
  *) echo "usage: server-mode audit|on [--yes]|off|status|failsafe|screen-off" >&2; exit 2 ;;
esac
