#!/usr/bin/env python3
"""Export configured shortcuts for Noctalia and show a searchable Rofi sheet."""

from __future__ import annotations

import html
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HOME = Path.home()
HYPR_CONFIG = HOME / ".config/hypr/hyprland.conf"
TMUX_CONFIG = HOME / ".tmux.conf"
ROFI_THEME = ROOT / "config/rofi-themes/files/launchers/type-1/keybind-cheatsheet.rasi"


def clean_modifiers(value: str) -> str:
    replacements = {
        "$mod": "Super",
        "SUPER": "Super",
        "CTRL": "Ctrl",
        "SHIFT": "Shift",
        "ALT": "Alt",
    }
    parts = [replacements.get(part, part.title()) for part in value.split() if part]
    return "+".join(parts)


def describe(dispatcher: str, argument: str, comment: str) -> str:
    if comment:
        return comment.strip()
    text = " ".join(part for part in (dispatcher, argument) if part).strip()
    return text[:100]


def shortcut_group(scope: str, dispatcher: str, argument: str) -> str:
    if scope == "tmux":
        return "Terminal"
    if scope.startswith("Hypr · "):
        mode = scope.partition("·")[2].strip()
        return {
            "wallpaper": "Wallpaper mode",
            "resize": "Resize mode",
            "system": "System mode",
        }.get(mode, f"{mode.title()} mode")

    if dispatcher in {
        "workspace",
        "movetoworkspace",
        "movetoworkspacesilent",
        "togglespecialworkspace",
        "movecurrentworkspacetomonitor",
    }:
        return "Workspaces"
    if dispatcher in {
        "changegroupactive",
        "centerwindow",
        "focuscurrentorlast",
        "fullscreen",
        "killactive",
        "layoutmsg",
        "movefocus",
        "moveoutofgroup",
        "movewindoworgroup",
        "resizeactive",
        "resizewindowpixel",
        "togglefloating",
        "togglegroup",
    }:
        return "Windows & layout"

    command = f"{dispatcher} {argument}".lower()
    if any(token in command for token in ("grim", "slurp", "cliphist", "wl-copy")):
        return "Capture & clipboard"
    if any(token in command for token in ("wpctl", "playerctl", "audio-")):
        return "Audio & media"
    if any(token in command for token in ("wallpaper", "hypr-gaps", "bar-mode")):
        return "Appearance"
    if any(token in command for token in ("hyprlock", "systemctl", "night-mode", "reload-desktop")):
        return "System"
    if dispatcher == "submap":
        return "Modes"
    if dispatcher == "exec":
        return "Apps"
    return "Other"


def hyprland_shortcuts(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    submap = "default"
    for raw in path.read_text(errors="replace").splitlines():
        stripped = raw.strip()
        submap_match = re.match(r"submap\s*=\s*(.+)", stripped)
        if submap_match:
            value = submap_match.group(1).strip()
            submap = "default" if value == "reset" else value.split(" ·", 1)[0]
            continue

        match = re.match(r"bind[a-z]*\s*=\s*(.+)", stripped)
        if not match:
            continue
        binding, _, comment = match.group(1).partition("#")
        fields = [field.strip() for field in binding.split(",", 3)]
        if len(fields) < 3:
            continue
        modifiers, key, dispatcher = fields[:3]
        argument = fields[3] if len(fields) == 4 else ""
        if dispatcher == "global" and argument.startswith("keybind-cheatsheet:"):
            continue
        prefix = clean_modifiers(modifiers)
        shortcut = "+".join(part for part in (prefix, key) if part)
        scope = "Hypr" if submap == "default" else f"Hypr · {submap}"
        rows.append(
            {
                "scope": scope,
                "shortcut": shortcut,
                "action": describe(dispatcher, argument, comment),
                "group": shortcut_group(scope, dispatcher, argument),
            }
        )
    return rows


def hyprland_bindings(path: Path) -> list[str]:
    return [
        f"{row['scope']:<20} {row['shortcut']:<28} {row['action']}"
        for row in hyprland_shortcuts(path)
    ]


def tmux_binding(tokens: list[str]) -> tuple[str, str] | None:
    index = 1
    table = "prefix"
    while index < len(tokens) and tokens[index].startswith("-"):
        option = tokens[index]
        index += 1
        if option in {"-T", "-N"} and index < len(tokens):
            if option == "-T":
                table = tokens[index]
            index += 1
    if index >= len(tokens):
        return None
    key = tokens[index]
    action = " ".join(tokens[index + 1 :])
    if table == "prefix":
        shortcut = f"Ctrl-B, {key}"
    else:
        shortcut = f"{table}: {key}"
    return shortcut, action


def tmux_shortcuts(path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    logical_lines: list[str] = []
    pending = ""
    content = path.read_text(errors="replace")
    for raw in content.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        pending = f"{pending} {line}".strip()
        if pending.endswith("\\"):
            pending = pending[:-1].rstrip()
            continue
        logical_lines.append(pending)
        pending = ""

    for line in logical_lines:
        if not re.match(r"bind(?:-key)?\s", line):
            continue
        try:
            parsed = tmux_binding(shlex.split(line))
        except ValueError:
            continue
        if not parsed:
            continue
        shortcut, action = parsed
        rows.append(
            {
                "scope": "tmux",
                "shortcut": shortcut,
                "action": action[:100],
                "group": "Terminal",
            }
        )
    fleet_key = re.search(r"set\s+-g\s+@agent-fleet-key\s+['\"]?([^'\"\s]+)", content)
    if fleet_key and fleet_key.group(1) != "none":
        rows.append(
            {
                "scope": "tmux",
                "shortcut": f"Ctrl-B, {fleet_key.group(1)}",
                "action": "open multi-harness agent fleet dashboard",
                "group": "Terminal",
            }
        )
    return rows


def tmux_bindings(path: Path) -> list[str]:
    return [
        f"{row['scope']:<20} {row['shortcut']:<28} {row['action']}"
        for row in tmux_shortcuts(path)
    ]


def all_shortcuts() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if HYPR_CONFIG.exists():
        rows.extend(hyprland_shortcuts(HYPR_CONFIG))
    if TMUX_CONFIG.exists():
        rows.extend(tmux_shortcuts(TMUX_CONFIG))
    return rows


def grouped_shortcuts(rows: list[dict[str, str]]) -> list[dict[str, object]]:
    groups: dict[str, list[dict[str, str]]] = {}
    for row in rows:
        groups.setdefault(row["group"], []).append(
            {
                "scope": row["scope"],
                "shortcut": row["shortcut"],
                "action": row["action"],
            }
        )
    return [{"title": title, "rows": entries} for title, entries in groups.items()]


def rofi_row(row: dict[str, str]) -> str:
    scope = html.escape(row["scope"])
    shortcut = html.escape(row["shortcut"])
    action = html.escape(row["action"])
    return (
        f'<span size="small" foreground="#aab2c0">{scope}</span>  '
        f'<span foreground="#f1f3fa" background="#303748"> {shortcut} </span>  '
        f'<span foreground="#d5dae5">{action}</span>'
    )


def main() -> int:
    arguments = sys.argv[1:]
    if arguments not in ([], ["--json"], ["--print"]):
        print("usage: keybind-cheatsheet.py [--json|--print]", file=sys.stderr)
        return 2
    shortcuts = all_shortcuts()
    if "--json" in sys.argv:
        print(json.dumps(grouped_shortcuts(shortcuts), ensure_ascii=False))
        return 0

    rows = ["CONTEXT              SHORTCUT                     ACTION"]
    rows.extend(
        f"{row['scope']:<20} {row['shortcut']:<28} {row['action']}"
        for row in shortcuts
    )
    if "--print" in sys.argv:
        print("\n".join(rows))
        return 0

    rofi_rows = [rofi_row(row) for row in shortcuts]
    subprocess.run(
        [
            "rofi",
            "-dmenu",
            "-i",
            "-no-custom",
            "-markup-rows",
            "-theme",
            str(ROFI_THEME),
            "-p",
            "Global shortcuts",
            "-mesg",
            "Read-only · type to filter · Esc closes",
        ],
        input="\n".join(rofi_rows) + "\n",
        text=True,
        check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
