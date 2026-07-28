#!/usr/bin/env python3
"""Show Hyprland and tmux bindings as a read-only Rofi cheatsheet."""

from __future__ import annotations

import re
import shlex
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
HYPR_CONFIG = HOME / ".config/hypr/hyprland.conf"
TMUX_CONFIG = HOME / ".tmux.conf"


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


def hyprland_bindings(path: Path) -> list[str]:
    rows: list[str] = []
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
        prefix = clean_modifiers(modifiers)
        shortcut = "+".join(part for part in (prefix, key) if part)
        scope = "Hypr" if submap == "default" else f"Hypr · {submap}"
        rows.append(f"{scope:<20} {shortcut:<28} {describe(dispatcher, argument, comment)}")
    return rows


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
        shortcut = f"Ctrl-Space, {key}"
    else:
        shortcut = f"{table}: {key}"
    return shortcut, action


def tmux_bindings(path: Path) -> list[str]:
    rows: list[str] = []
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
        rows.append(f"{'tmux':<20} {shortcut:<28} {action[:100]}")
    fleet_key = re.search(r"set\s+-g\s+@agent-fleet-key\s+['\"]?([^'\"\s]+)", content)
    if fleet_key and fleet_key.group(1) != "none":
        rows.append(
            f"{'tmux':<20} {f'Ctrl-Space, {fleet_key.group(1)}':<28} "
            "open multi-harness agent fleet dashboard"
        )
    return rows


def main() -> int:
    rows = ["CONTEXT              SHORTCUT                     ACTION"]
    if HYPR_CONFIG.exists():
        rows.extend(hyprland_bindings(HYPR_CONFIG))
    if TMUX_CONFIG.exists():
        rows.extend(tmux_bindings(TMUX_CONFIG))
    if "--print" in sys.argv:
        print("\n".join(rows))
        return 0
    subprocess.run(
        [
            "rofi",
            "-dmenu",
            "-i",
            "-no-custom",
            "-p",
            "Global shortcuts",
            "-mesg",
            "Read-only · type to filter · Esc closes",
        ],
        input="\n".join(rows) + "\n",
        text=True,
        check=False,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
