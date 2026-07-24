#!/usr/bin/env python3
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WALLPAPER_DIR = Path.home() / "workspace/UX/background"
WALLPAPER_MODE = ROOT / "scripts/wallpaper-mode.sh"
STATE_FILE = Path.home() / ".cache/wallpaper-mode/state"


def run(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, capture_output=True, text=True, check=False)


def catalog() -> list[str]:
    extensions = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
    return sorted(
        (str(path) for path in WALLPAPER_DIR.rglob("*") if path.is_file() and path.suffix.lower() in extensions),
        key=lambda path: (Path(path).name.casefold(), path.casefold()),
    )


def focused_monitor() -> str:
    result = run("hyprctl", "-j", "monitors")
    if result.returncode != 0:
        return ""
    import json

    for monitor in json.loads(result.stdout):
        if monitor.get("focused"):
            return str(monitor.get("name", ""))
    return ""


def noctalia_wallpaper(monitor: str) -> str | None:
    result = run("qs", "-c", "noctalia-shell", "ipc", "call", "wallpaper", "get", monitor)
    return result.stdout.strip() if result.returncode == 0 else None


def waybar_wallpaper() -> str:
    try:
        state = STATE_FILE.read_text().strip()
    except OSError:
        return ""
    if not state.startswith("static|"):
        return ""
    fields = state.split("|", 2)
    return fields[-1]


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] not in {"next", "previous"}:
        print(f"usage: {Path(sys.argv[0]).name} next|previous", file=sys.stderr)
        return 2

    files = catalog()
    if not files:
        print(f"no wallpapers found in {WALLPAPER_DIR}", file=sys.stderr)
        return 1

    monitor = focused_monitor()
    current = noctalia_wallpaper(monitor)
    using_noctalia = current is not None
    if current is None:
        current = waybar_wallpaper()

    step = 1 if sys.argv[1] == "next" else -1
    try:
        index = files.index(current)
        target = files[(index + step) % len(files)]
    except ValueError:
        target = files[0] if step > 0 else files[-1]

    if using_noctalia:
        result = run("qs", "-c", "noctalia-shell", "ipc", "call", "wallpaper", "set", target, "all")
    else:
        result = run(str(WALLPAPER_MODE), "static", target)

    if result.returncode != 0:
        print(result.stderr.strip() or "wallpaper change failed", file=sys.stderr)
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
