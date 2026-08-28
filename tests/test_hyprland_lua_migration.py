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


def test_hyprglass_semantics_are_preserved_in_lua_and_inventory():
    appearance = (HYPR / "lua/appearance.lua").read_text()
    inventory = json.loads(INVENTORY.read_text())
    expected = {
        "plugin:hyprglass.enabled": "0",
        "plugin:hyprglass.default_theme": "dark",
        "plugin:hyprglass.default_preset": "flow",
        "plugin:hyprglass.layers.enabled": "0",
        "plugin:hyprglass.layers.namespaces": "waybar",
        "plugin:hyprglass.layers.preset": "flow",
        "plugin:hyprglass.layers.namespace_mask_thresholds": "waybar=0.05",
    }
    semantics = {item["path"]: item["value"] for item in inventory["semantics"]}
    assert expected.items() <= semantics.items()
    for value in expected.values():
        assert repr(value).strip("'") in appearance
    assert "blur_strength:1.10" in appearance
    assert "brightness:0.88" in appearance


def test_semantic_inventory_rejects_representative_sabotage(tmp_path):
    checker = ROOT / "scripts/check-hypr-lua-parity"
    for relative, old, new in (
        ("lua/monitors.lua", 'mode="1920x1080@540"', 'mode="1920x1080@539"'),
        ("lua/rules.lua", 'workspace="10"', 'workspace="11"'),
        ("lua/binds.lua", '"SUPER + Return"', '"SUPER + Backspace"'),
        ("lua/appearance.lua", 'default_theme="dark"', 'default_theme="light"'),
    ):
        candidate = tmp_path / relative
        candidate.parent.mkdir(parents=True, exist_ok=True)
        body = (HYPR / relative).read_text()
        assert old in body
        candidate.write_text(body.replace(old, new, 1))
        result = subprocess.run(
            [checker, "--lua-root", tmp_path / "lua"], capture_output=True, text=True
        )
        assert result.returncode != 0, relative
        assert "parity mismatch" in result.stderr


def test_phone_display_uses_injected_isolated_instance_without_focus_dispatch():
    script = (ROOT / "scripts/phone-display.sh").read_text()
    assert 'HYPRCTL_BIN=${PHONE_DISPLAY_HYPRCTL:-hyprctl}' in script
    assert 'SYSTEMCTL_BIN=${PHONE_DISPLAY_SYSTEMCTL:-systemctl}' in script
    assert 'dispatch focusmonitor' not in script
    assert 'dispatch workspace' not in script
    assert 'dispatch moveworkspacetomonitor' not in script


def test_nested_parity_harness_owns_health_readback_and_dynamic_lifecycles():
    harness = ROOT / "scripts/verify-hypr-lua-nested"
    assert harness.exists()
    body = harness.read_text()
    for token in (
        "configProvider: lua", "configerrors", "monitors", "workspaces",
        "binds", "devices", "plugins", "workspaceRules", "clients",
        "gui-e2e-display.sh", "phone-display.sh", "systeminfo",
        "HYPRLAND_INSTANCE_SIGNATURE", "WAYLAND_DISPLAY", "evidence",
    ):
        assert token in body
    result = subprocess.run([harness, "--help"], capture_output=True, text=True)
    assert result.returncode == 0
    assert "protected workspaces" in result.stdout
