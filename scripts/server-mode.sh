#!/usr/bin/env bash
# server-mode: run groot headless while the owner drives all work from the phone (t3os-style "personal server").
#
#   server-mode audit        memory by unit/scope, GUI vs headless, no changes
#   server-mode on [--yes]   stop the graphical session (Hyprland + every app it launched) and leftover GUI app scopes
#   server-mode off          clear the flag; the desktop returns on the next login at the console (tty1/SDDM)
#   server-mode status
#   server-mode failsafe     check the root failsafe (SysRq, hardware watchdog, earlyoom, sshd/tailscaled protection)
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
  remote_ok || return 1
  failsafe || echo "warning: root failsafe incomplete; continuing (server mode itself frees RAM)"
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
  echo "way back in: ssh $USER@$(tailscale ip -4 2>/dev/null | head -1) | console Ctrl+Alt+F2 | frozen: Alt+SysRq+F, then R-E-I-S-U-B"
  # Processes started from the desktop inherit its private D-Bus (/tmp/dbus-*), which is now gone: keyring, bws
  # bootstrap and gh auth then fail inside them. Point new shells at the user bus; restart such services when idle.
  if [[ ${DBUS_SESSION_BUS_ADDRESS:-} == *"/tmp/dbus-"* ]]; then
    echo "note: this shell used the desktop D-Bus; run: export DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$(id -u)/bus"
  fi
}

off() {
  rm -f "$ACTIVE"
  printf '{"at":"%s","action":"off"}\n' "$(date -Is)" >> "$LOG"
  echo "server mode OFF. Log in at the console (tty1 or SDDM) to start Hyprland again; nothing else needs restoring."
}

status() {
  if [[ -e $ACTIVE && $(date -d "$(cat "$ACTIVE")" +%s) -lt $(date -d "$(uptime -s)" +%s) ]]; then
    echo "server mode: stale flag from before the last boot ($(cat "$ACTIVE")); clearing"; rm -f "$ACTIVE"
  fi
  if [[ -e $ACTIVE ]]; then echo "server mode: ON since $(cat "$ACTIVE")"; else echo "server mode: off"; fi
  systemctl --user is-active --quiet "$GUI_UNIT" && echo "graphical session: running" || echo "graphical session: stopped"
  echo "MemAvailable: $(avail_mb) MB"
}

case "${1:-status}" in
  audit) audit "${2:-40}" ;;
  on) on "${2:-}" ;;
  off) off ;;
  status) status ;;
  failsafe) failsafe ;;
  *) echo "usage: server-mode audit|on [--yes]|off|status|failsafe" >&2; exit 2 ;;
esac
