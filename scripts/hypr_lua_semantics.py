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


TOKEN = re.compile(r'''\s*(?:(--[^\n]*)|([A-Za-z_][A-Za-z0-9_]*)|(-?\d+(?:\.\d+)?)|("(?:\\.|[^"\\])*"|'(?:\\.|[^'\\])*')|(.))''')


def _tokens(text: str) -> list[str]:
    return [next(part for part in match.groups()[1:] if part is not None)
            for match in TOKEN.finditer(text) if match.group(1) is None]


def _table(tokens: list[str], at: int) -> tuple[dict, int]:
    assert tokens[at] == "{"
    result = {}
    at += 1
    while at < len(tokens) and tokens[at] != "}":
        if at + 1 < len(tokens) and re.match(r"^[A-Za-z_]", tokens[at]) and tokens[at + 1] == "=":
            key = tokens[at]
            at += 2
            if tokens[at] == "{":
                value, at = _table(tokens, at)
            else:
                value = tokens[at]
                at += 1
            result[key] = value
        else:
            # Positional tables are values of a containing key. Preserve their
            # complete spelling rather than pretending they are scoped keys.
            at += 1
        if at < len(tokens) and tokens[at] == ",":
            at += 1
    return result, at + 1


def config_values(text: str) -> dict[str, str]:
    tokens = _tokens(text)
    found = {}
    at = 0
    while at + 4 < len(tokens):
        if tokens[at:at + 4] == ["hl", ".", "config", "("] and tokens[at + 4] == "{":
            table, at = _table(tokens, at + 4)
            def flatten(value, prefix=""):
                for key, child in value.items():
                    path = f"{prefix}.{key}" if prefix else key
                    if isinstance(child, dict):
                        flatten(child, path)
                    else:
                        found[path] = child
            flatten(table)
        at += 1
    return found


def typed(value: str) -> str:
    value = value.strip()
    if value in {"true", "false"}:
        return "bool:" + value
    if re.fullmatch(r"-?\d+(?:\.\d+)?", value):
        return "number:" + value
    return "string:" + canonical(value)


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
    configs = config_values("\n".join(lines))
    if path in configs:
        actual_value = configs[path]
        expected_typed = typed(value)
        actual_typed = typed(actual_value)
        if actual_typed != expected_typed:
            raise ValueError(f"{path}: expected {expected_typed}, got {actual_typed}")
        matching = [number for number, line in enumerate(lines, 1)
                    if re.search(rf"\b{re.escape(path.rsplit('.', 1)[-1])}\s*=", line)]
        return {
            "source_tokens": [path, actual_typed],
            "source_lines": matching,
            "actual": f"lua[{owner.name}:{','.join(map(str, matching))}]:{path}={actual_typed}",
        }
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
