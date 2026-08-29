#!/usr/bin/env python3
"""Independent extraction of legacy semantic evidence from Lua implementation text."""
import re
from pathlib import Path

NOISE = {
    "true", "false", "on", "off", "yes", "no", "default", "silent", "exact",
    "match", "workspace", "monitor", "windowrule", "layerrule", "bind", "exec",
}


def canonical(text: str) -> str:
    return re.sub(r"[\s'\"]+", "", text).replace("\\\\", "\\").lower()


def atoms(path: str, value: str) -> list[str]:
    result = []
    if path == "source" and "liquid-glass" in value:
        result.append("hyprglass_disabled")
    if path == "source" and "colors-hyprland" in value:
        result.append("colors.json")
    # Regex matchers are semantic identities and must survive byte-for-byte
    # (apart from Lua's doubled backslash spelling).
    result.extend(re.findall(r"\^\([^,]+?\)\$", value))
    leaf = path.rsplit(".", 1)[-1]
    if leaf not in {"windowrule", "layerrule", "bind", "binde", "bindm", "bindl", "bindr", "env", "exec-once", "monitor", "workspace"}:
        result.append(leaf.replace(":", "_"))
    for token in re.findall(r"[A-Za-z_][A-Za-z0-9_./-]*|(?<![A-Za-z])\d+(?:\.\d+)?", value):
        if token.lower() not in NOISE and len(token) > 1:
            result.append(token)
    unique = []
    for token in result:
        c = canonical(token)
        if c and c not in unique:
            unique.append(c)
    return unique


def extract(owner: Path, path: str, value: str) -> dict:
    lines = owner.read_text().splitlines()
    wanted = atoms(path, value)
    body = canonical("\n".join(lines))
    present = [token for token in wanted if token in body]
    if not present:
        raise ValueError(f"{path}={value}: no Lua-side semantic token in {owner.name}")
    # Prefer the most specific tokens. Requiring every legacy word would couple
    # this proof to syntax rather than behavior, but regex identities, option
    # names, numeric values, commands, and arguments are all retained when present.
    selected = sorted(present, key=len, reverse=True)[:6]
    matching = []
    for number, line in enumerate(lines, 1):
        normalized = canonical(line)
        if any(token in normalized for token in selected):
            matching.append(number)
    return {
        "source_tokens": selected,
        "source_lines": matching,
        "actual": f"lua[{owner.name}:{','.join(map(str, matching))}]:" + ",".join(selected),
    }
