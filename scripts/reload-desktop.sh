#!/usr/bin/env bash
# Reload config while preserving the running desktop and its saved modes.

# Shells and automation can retain a stale Hyprland instance after a compositor
# restart. Resolve the live command socket before touching desktop processes.
if ! hyprctl -j monitors >/dev/null 2>&1; then
    while IFS=$'\t' read -r signature wayland_display; do
        if HYPRLAND_INSTANCE_SIGNATURE="$signature" hyprctl -j monitors >/dev/null 2>&1; then
            export HYPRLAND_INSTANCE_SIGNATURE="$signature"
            export WAYLAND_DISPLAY="$wayland_display"
            break
        fi
    done < <(hyprctl -j instances | jq -r '.[] | [.instance, .wl_socket] | @tsv')
fi

if ! hyprctl -j monitors >/dev/null 2>&1; then
    printf 'No live Hyprland instance found\n' >&2
    exit 1
fi

SCRIPTS=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)

# Keep NUL-delimited argv and process identity intact; never reconstruct shell commands.
exec python3 -S - "$SCRIPTS" <<'PY_RELOAD'
import json
import os
from pathlib import Path
import shlex
import signal
import subprocess
import sys
import time

scripts = Path(sys.argv[1])
home = Path(os.environ["HOME"])
runtime = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp"))
signature = os.environ.get("HYPRLAND_INSTANCE_SIGNATURE", "")
display = os.environ.get("WAYLAND_DISPLAY", "")
dry = os.environ.get("DRY_RUN") == "1"
wallpaper_file = home / ".cache/wallpaper-mode/state"
bar_file = home / ".cache/desktop-shell/bar-mode"
performance_dir = runtime / f"unified-performance-mode-{os.getuid()}"
options = ("animations:enabled", "decoration:blur:enabled", "decoration:shadow:enabled")


def saved(path):
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


def value(option):
    result = subprocess.run(["hyprctl", "-j", "getoption", option],
                            check=True, capture_output=True, text=True)
    return json.loads(result.stdout)["int"]


def identity(path):
    fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
    return fields[0], fields[19]  # state, start time; protects against PID reuse


def processes():
    rows = []
    for path in Path("/proc").glob("[0-9]*"):
        try:
            if path.stat().st_uid != os.getuid():
                continue
            name = (path / "comm").read_text().strip()
            if name not in {"linux-wallpaper", "linux-wallpaperengine", "swaybg",
                            "qs", "quickshell", "noctalia", "waybar"}:
                continue
            env = dict(item.split("=", 1) for item in
                       os.fsdecode((path / "environ").read_bytes()).split("\0") if "=" in item)
            if env.get("XDG_RUNTIME_DIR") != str(runtime):
                continue
            if env.get("HYPRLAND_INSTANCE_SIGNATURE") != signature and not (
                    display and env.get("WAYLAND_DISPLAY") == display):
                continue
            argv = [os.fsdecode(arg) for arg in (path / "cmdline").read_bytes().split(b"\0") if arg]
            if name in {"qs", "quickshell"} and not any("noctalia" in arg for arg in argv):
                continue
            state, start = identity(path)
            if state in {"Z", "X"} or not argv:
                continue
            rows.append(dict(pid=int(path.name), name=name, argv=argv, env=env,
                             state=state, start=start, cwd=os.readlink(path / "cwd"),
                             exe=os.readlink(path / "exe")))
        except (FileNotFoundError, ProcessLookupError):
            continue  # exited during the snapshot
    return rows


def is_wallpaper(row):
    return row["name"] in {"linux-wallpaper", "linux-wallpaperengine", "swaybg"}


def flag(row, key):
    argv = row["argv"]
    return argv[argv.index(key) + 1] if key in argv and argv.index(key) + 1 < len(argv) else "?"


def alive(row):
    try:
        state, start = identity(Path("/proc") / str(row["pid"]))
        return start == row["start"] and state not in {"Z", "X"}
    except (FileNotFoundError, ProcessLookupError):
        return False


def command(argv):
    print(("DRY_RUN: " if dry else "run: ") + shlex.join(map(str, argv)), flush=True)
    if not dry:
        subprocess.run(argv, check=True)


def restart(row):
    print("recover wallpaper: " + shlex.join(row["argv"]), flush=True)
    logdir = home / ".cache/desktop-reload"
    logdir.mkdir(parents=True, exist_ok=True)
    with (logdir / "wallpaper.log").open("ab") as log:
        child = subprocess.Popen(row["argv"], executable=row["exe"], cwd=row["cwd"],
                                 env=row["env"], stdin=subprocess.DEVNULL,
                                 stdout=log, stderr=log, start_new_session=True)
    time.sleep(0.4)
    if child.poll() is not None:
        raise RuntimeError(f"wallpaper recovery exited {child.returncode}; see {logdir}/wallpaper.log")
    if row["state"] in {"T", "t"}:
        child.send_signal(signal.SIGSTOP)


wallpaper_state = saved(wallpaper_file)
bar_state = saved(bar_file)
performance_state = {name: saved(performance_dir / name) for name in
                     ("active", "hypr-options", "wallpaper-state", "wallpaper-changed")}
active = performance_state["active"] is not None
before_options = {option: value(option) for option in options}
before = processes()
wallpapers = [row for row in before if is_wallpaper(row)]
bars = [row for row in before if not is_wallpaper(row)]
bar_mode = ("waybar" if bars[0]["name"] == "waybar" else "noctalia") if bars else (
    (bar_state or b"noctalia").decode().strip())
print(f"found: wallpaper={(wallpaper_state or b'(unsaved)').decode().strip()}; "
      f"live={sum(row['name'] != 'swaybg' for row in wallpapers)}; "
      f"stills={sum(row['name'] == 'swaybg' for row in wallpapers)}; "
      f"bar={bar_mode} ({len(bars)} process); performance={'on' if active else 'off'}", flush=True)
for row in wallpapers:
    if row["name"] != "swaybg":
        print(f"engine: pid={row['pid']} output={flag(row, '--screen-root')} "
              f"fps={flag(row, '--fps')} wallpaper={Path(flag(row, '--bg')).name}", flush=True)

command(["hyprctl", "reload"])
if dry:
    print("DRY_RUN: keep healthy wallpaper/bar processes; recover only lost wallpaper argv", flush=True)
    print(f"DRY_RUN: if bar dies: {scripts / 'bar-mode.sh'} restore (captured {bar_mode})", flush=True)
    if not wallpapers and wallpaper_state is None:
        command([str(scripts / "wallpaper-mode.sh"), "restore"])
    if active:
        print("DRY_RUN: restore only changed performance options to " + str(before_options), flush=True)
    print("summary: DRY_RUN; no mutations or files changed", flush=True)
    sys.exit(0)

time.sleep(0.3)
restored_options = 0
if active:
    if any(saved(performance_dir / name) != content for name, content in performance_state.items()):
        raise RuntimeError("performance mode changed concurrently; recovery cancelled")
    for option, previous in before_options.items():
        if value(option) != previous:
            command(["hyprctl", "keyword", option, str(previous)])
            if value(option) != previous:
                raise RuntimeError(f"performance option {option} did not restore")
            restored_options += 1

after = processes()
connected = {monitor["name"] for monitor in json.loads(subprocess.run(
    ["hyprctl", "-j", "monitors"], check=True, capture_output=True, text=True).stdout)
    if not monitor.get("disabled")}
recovered = 0
wallpaper_failed = 0
for row in wallpapers:
    if alive(row):
        continue
    # A supervisor may already have replaced it; avoid a duplicate on that output.
    output_flag = "-o" if row["name"] == "swaybg" else "--screen-root"
    if any(is_wallpaper(other) and other["name"] == row["name"] and
           flag(other, output_flag) == flag(row, output_flag) for other in after):
        continue
    if saved(wallpaper_file) != wallpaper_state:
        raise RuntimeError("wallpaper mode changed concurrently; recovery cancelled")
    # Never relaunch on an output the reload removed or disabled.
    if flag(row, output_flag) not in connected | {"?", "*"}:
        print(f"skip wallpaper recovery: output {flag(row, output_flag)} is not connected", flush=True)
        continue
    # A failed wallpaper recovery must not prevent the bar check below.
    try:
        restart(row)
        recovered += 1
    except (OSError, RuntimeError) as error:
        print(f"wallpaper recovery failed: {error}", file=sys.stderr, flush=True)
        wallpaper_failed += 1
if not wallpapers and wallpaper_state is None and not any(is_wallpaper(row) for row in after):
    try:
        command([str(scripts / "wallpaper-mode.sh"), "restore"])
        recovered += 1
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"wallpaper default start failed: {error}", file=sys.stderr, flush=True)
        wallpaper_failed += 1

bar_recovered = False
if not any(not is_wallpaper(row) for row in after):
    if saved(bar_file) != bar_state:
        raise RuntimeError("bar mode changed concurrently; recovery cancelled")
    print(f"bar died or was absent after reload; restoring {bar_mode} (known reload hazard)", flush=True)
    # The running bar wins over a stale saved mode; return the state file to its original bytes.
    selected = (bar_mode + "\n").encode()
    bar_file.parent.mkdir(parents=True, exist_ok=True)
    if bar_state != selected:
        bar_file.write_bytes(selected)
    try:
        command([str(scripts / "bar-mode.sh"), "restore"])
    finally:
        if saved(bar_file) == selected:
            if bar_state is None:
                bar_file.unlink()
            else:
                bar_file.write_bytes(bar_state)
    time.sleep(0.4)
    if not any(not is_wallpaper(row) for row in processes()):
        raise RuntimeError("bar restore returned without a running bar")
    bar_recovered = True

print(f"summary: wallpaper recovered={recovered}; bar recovered={int(bar_recovered)}; "
      f"performance options restored={restored_options}; saved modes preserved", flush=True)
sys.exit(1 if wallpaper_failed else 0)
PY_RELOAD
