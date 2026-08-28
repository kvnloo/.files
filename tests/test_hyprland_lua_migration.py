import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HYPR = ROOT / "config/hyprland"
LEGACY = HYPR / "hyprland.legacy.conf"
INVENTORY = HYPR / "migration-inventory.json"


def legacy_directive_lines():
    directives = []
    depth = 0
    for number, raw in enumerate(LEGACY.read_text().splitlines(), 1):
        text = raw.split("#", 1)[0].strip()
        if not text:
            continue
        if text.endswith("{"):
            depth += 1
            directives.append((number, text))
        elif text == "}":
            directives.append((number, text))
            depth -= 1
        else:
            directives.append((number, text))
    assert depth == 0
    return directives


def test_inventory_classifies_every_legacy_directive_exactly_once():
    inventory = json.loads(INVENTORY.read_text())
    expected = legacy_directive_lines()
    actual = [(item["line"], item["directive"]) for item in inventory["directives"]]
    assert actual == expected
    assert all(item["owner"].endswith(".lua") for item in inventory["directives"])
    assert inventory["unclassified"] == []


def test_entrypoint_is_modular_lua_and_legacy_sources_are_owned_by_lua():
    entrypoint = (HYPR / "hyprland.lua").read_text()
    required = set(re.findall(r'require\("([^"]+)"\)', entrypoint))
    assert required == {
        "lua.monitors", "lua.environment", "lua.appearance", "lua.rules",
        "lua.binds", "lua.autostart",
    }
    all_lua = "\n".join(path.read_text() for path in HYPR.glob("lua/*.lua"))
    assert "colors-hyprland.conf" not in all_lua
    assert "liquid-glass.conf" not in all_lua


def test_lua_is_syntactically_valid():
    files = [HYPR / "hyprland.lua", *sorted((HYPR / "lua").glob("*.lua"))]
    subprocess.run(["luac", "-p", *map(str, files)], check=True)


def test_agent_gui_rules_are_fail_closed_to_special_headless_workspace():
    rules = (HYPR / "lua/rules.lua").read_text()
    assert "special:hermes-tests" in rules
    assert "workspace 9" not in rules
    assert "HermesE2E-" in rules
    assert "Agent Orchestrator" in rules


def test_activation_and_rollback_are_atomic_and_do_not_restart_live_compositor():
    script = (ROOT / "scripts/hypr-lua-config").read_text()
    assert "ln -sfn" in script
    assert "hyprland.lua" in script
    assert "hyprland.legacy.conf" in script
    assert "Hyprland" not in script
    assert "hyprctl reload" not in script


def test_activation_and_rollback_select_exact_targets_in_sandbox(tmp_path):
    env = {"HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    script = ROOT / "scripts/hypr-lua-config"
    subprocess.run([script, "activate"], check=True, env=env)
    link = tmp_path / "config/hypr/hyprland.conf"
    assert link.resolve() == HYPR / "hyprland.lua"
    subprocess.run([script, "rollback"], check=True, env=env)
    assert link.resolve() == HYPR / "hyprland.legacy.conf"


def test_sabotaged_lua_is_rejected_by_parser(tmp_path):
    broken = tmp_path / "broken.lua"
    broken.write_text((HYPR / "lua/monitors.lua").read_text().replace(")", "", 1))
    result = subprocess.run(["luac", "-p", broken], capture_output=True, text=True)
    assert result.returncode != 0
    assert "expected" in result.stderr
