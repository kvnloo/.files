import json
import os
import re
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYPR = ROOT / "config/hyprland"
MAP_PATH = HYPR / "lua-ownership-map.json"
LIVE_LINK = Path.home() / ".config/hypr/hyprland.conf"
STATIC_APIS = {
    "hl.config",
    "hl.monitor",
    "hl.workspace_rule",
    "hl.window_rule",
    "hl.layer_rule",
    "hl.bind",
    "hl.on",
    "require",
}
DEFERRED_APIS = {"generated Lua artifact", "explicit bridge"}
STRUCTURAL = re.compile(r"^[\w.:$-]+\s*\{$|^\{$|^\}$")
MATCHER = re.compile(r"match:(?:class|title|namespace)\s+([^,]+)")


def payload():
    return json.loads(MAP_PATH.read_text())


def owner_body(item: dict) -> str:
    owner = item["owner_module"]
    path = HYPR / owner
    assert path.is_file(), f"missing owner module {owner} for {item['text']}"
    return path.read_text()


def test_every_static_inventory_line_has_an_owning_lua_module():
    data = payload()
    missing = []
    for item in data["lines"]:
        api = item["lua_api"]
        if api in DEFERRED_APIS:
            continue
        assert api in STATIC_APIS, item
        owner = item.get("owner_module")
        if not owner or not owner.endswith(".lua"):
            missing.append(item)
            continue
        if not (HYPR / owner).is_file():
            missing.append(item)
    assert missing == []


def test_deferred_inventory_lines_stay_classified_as_bridges_or_generated():
    data = payload()
    deferred = [item for item in data["lines"] if item["lua_api"] in DEFERRED_APIS]
    assert deferred
    assert all(item["lua_api"] in DEFERRED_APIS for item in deferred)
    assert any("colors-hyprland.conf" in item["text"] or item["file"].endswith("colors-hyprland.conf") for item in deferred)
    assert any("liquid-glass.conf" in item["text"] for item in deferred)


def _needles_for(text: str) -> list[str]:
    needles: list[str] = []
    for raw in MATCHER.findall(text):
        unescaped = raw.strip().replace("\\\\", "\\")
        inner = unescaped
        if inner.startswith("^(") and inner.endswith(")$"):
            inner = inner[2:-2]
        needles.extend(part.strip() for part in inner.split("|") if part.strip())
    if text.startswith("env ="):
        needles.append(text.split("=", 1)[1].split(",", 1)[0].strip())
    elif text.startswith("monitor ="):
        name = text.split("=", 1)[1].split(",", 1)[0].strip()
        if name:
            needles.append(name)
    elif text.startswith("workspace ="):
        needles.append(text.split("=", 1)[1].split(",", 1)[0].strip())
    elif text.startswith("exec-once ="):
        needles.append(Path(text.split("=", 1)[1].strip().split()[0]).name)
    elif text.startswith(("bind", "binde", "bindl", "bindel", "bindm")):
        parts = [part.strip() for part in text.split("=", 1)[1].split(",")]
        if len(parts) >= 3:
            needles.append(parts[1])
            needles.append(parts[2])
    elif "hyprglass.so" in text:
        needles.append("hyprglass.so")
    elif re.fullmatch(r"[A-Za-z0-9_.:-]+\s*=\s*.+", text) and not text.startswith("windowrule"):
        leaf = text.split("=", 1)[0].strip().split(":")[-1]
        if leaf == "namespaces":
            needles.append("waybar")
        elif leaf == "namespace_mask_thresholds":
            needles.append("mask_threshold")
        else:
            needles.append(leaf.split(".")[-1])
    return [needle for needle in needles if needle]


def test_static_matchers_and_commands_appear_in_owner_modules():
    data = payload()
    failures = []
    for item in data["lines"]:
        if item["lua_api"] not in STATIC_APIS:
            continue
        text = item["text"]
        if STRUCTURAL.fullmatch(text):
            continue
        body = owner_body(item)
        needles = _needles_for(text)
        if not needles:
            continue
        if not any(needle in body or needle.replace("\\", "\\\\") in body for needle in needles):
            failures.append((item["line"], item["keyword"], text, needles))
    assert failures == [], failures


def test_nested_sway_and_wlroots_rules_are_owned_without_workspace_nine():
    rules = (HYPR / "lua/rules.lua").read_text()
    assert 'class="^(sway)$"' in rules
    assert 'class="^(wlroots)$"' in rules
    assert "workspace 9" not in rules
    assert "special:hermes-tests" in rules


def test_lua_tree_parses_with_luac():
    files = [HYPR / "hyprland.lua", *sorted((HYPR / "lua").glob("*.lua"))]
    subprocess.run(["luac", "-p", *map(str, files)], check=True)


def test_static_lua_verify_or_lsp_is_clean():
    if shutil.which("lua-language-server"):
        result = subprocess.run(
            ["lua-language-server", "--check", str(HYPR / "hyprland.lua")],
            capture_output=True,
            text=True,
            env={**os.environ, "HYPR_LUA_TEST_MODE": "1"},
        )
        output = result.stdout + result.stderr
        assert result.returncode == 0, output
    result = subprocess.run(
        ["Hyprland", "--verify-config", "-c", str(HYPR / "hyprland.lua")],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "error" not in output.lower(), output
    assert "config ok" in output.lower(), output


def test_legacy_conf_remains_selected_and_lua_is_not_live_symlink_target():
    assert (HYPR / "hyprland.lua").is_file()
    assert (HYPR / "hyprland.legacy.conf").is_file()
    assert LIVE_LINK.is_symlink()
    assert LIVE_LINK.resolve() == (HYPR / "hyprland.legacy.conf").resolve()
    assert LIVE_LINK.resolve() != (HYPR / "hyprland.lua").resolve()
    entry = (HYPR / "hyprland.lua").read_text()
    for module in ("lua.monitors", "lua.environment", "lua.appearance", "lua.rules", "lua.binds", "lua.autostart"):
        assert f'require("{module}")' in entry
