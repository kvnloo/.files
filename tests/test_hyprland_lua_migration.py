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
    for token in (
        "enabled=false", 'default_theme="dark"', 'default_preset="flow"',
        'layers={enabled=false,preset="flow"}',
        'hg.layer("waybar", {preset="flow",mask_threshold=0.05})',
    ):
        assert token in appearance
    assert "blur_strength=1.10" in appearance
    assert "brightness=0.88" in appearance


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


def test_nested_bind_parity_normalizes_lua_callback_transport_only():
    script = (ROOT / "scripts/verify-hypr-lua-nested").read_text()
    assert '[[ $category != binds ]] || normalization=' in script
    assert '.dispatcher,.arg,.mouse' in script
    assert 'sort_by(.submap,.modmask,.key' in script
    assert 'The executable inventory separately proves dispatcher/argument ownership' in script
    assert 'Lua IPC reports native callback mouse binds as mouse=false' in script
    assert 'canonical_config()' in script
    assert '.value=(.custom // .css // .str // .int // .float // .bool)' in script


def test_generated_mouse_binds_use_native_lua_mouse_flag():
    binds = (HYPR / "lua/binds.lua").read_text()
    assert 'hl.dsp.window.drag(), {mouse=true}' in binds
    assert 'hl.dsp.window.resize(), {mouse=true}' in binds
    assert '{drag=true}' not in binds


def test_hyprglass_uses_post_load_native_lua_api():
    appearance = (HYPR / "lua/appearance.lua").read_text()
    harness = (ROOT / "scripts/verify-hypr-lua-nested").read_text()
    assert 'local hg=hl.plugin.hyprglass' in appearance
    assert 'hl.plugin.load(hyprglass_plugin)\n  local hg=hl.plugin.hyprglass' in appearance
    assert 'hl.on("hyprland.start"' not in appearance
    assert 'hg.config(hyprglass)' in appearance
    assert 'hg.preset("flow"' in appearance
    assert 'hg.layer("waybar"' in appearance
    assert 'keyword plugin:hyprglass' not in harness


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


def test_checker_executes_every_inventory_semantic_and_broad_sabotage(tmp_path):
    checker = ROOT / "scripts/check-hypr-lua-parity"
    inventory = json.loads(INVENTORY.read_text())
    assert inventory["semantics"]
    for item in inventory["semantics"]:
        assert item.get("proof"), item
    for relative, old, new in (
        ("lua/environment.lua", "QT_QPA_PLATFORMTHEME", "QT_THEME_SABOTAGED"),
        ("lua/appearance.lua", "workspace_swipe_distance=300", "workspace_swipe_distance=301"),
        ("lua/appearance.lua", 'leaf="fadeDim"', 'leaf="fadeDimBroken"'),
        ("lua/autostart.lua", "cliphist store", "cliphist discard"),
    ):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        body = (HYPR / relative).read_text()
        assert old in body
        target.write_text(body.replace(old, new, 1))
        result = subprocess.run([checker, "--lua-root", tmp_path / "lua"], capture_output=True, text=True)
        assert result.returncode != 0, relative


def test_nested_harness_compares_legacy_and_lua_and_asserts_cleanup_and_plugin():
    body = (ROOT / "scripts/verify-hypr-lua-nested").read_text()
    for token in (
        "legacy-", "lua-", "parity-mismatch", "plugin:hyprglass:enabled",
        "cleanup_complete", "kill -0", "host-workspaces-after", "nested socket remains",
    ):
        assert token in body


def test_nested_harness_compares_every_required_runtime_category_and_hyprglass_value():
    body = (ROOT / "scripts/verify-hypr-lua-nested").read_text()
    for category in ("monitors", "workspaces", "workspacerules", "clients", "binds", "devices", "plugins"):
        assert f'compare_category "{category}"' in body
    assert 'compare_static_category "window-rules"' in body
    assert 'compare_static_category "layer-rules"' in body
    for option in (
        "preset-flow", "preset-flow-dark", "layers-enabled", "layers-namespaces",
        "layers-preset", "layers-namespace_mask_thresholds",
    ):
        assert option in body


def test_each_inventory_semantic_has_independent_expected_and_actual_proof():
    inventory = json.loads(INVENTORY.read_text())
    keys = set()
    for item in inventory["semantics"]:
        proof = item["proof"]
        assert proof["expected"] == f'{item["path"]}={item["value"]}'
        assert proof["actual"]
        assert proof["actual"].startswith("lua[")
        assert proof["source_tokens"]
        key = (item["line"], proof["actual"])
        assert key not in keys
        keys.add(key)


def test_checker_detects_specific_rule_and_ordinary_semantic_sabotage(tmp_path):
    checker = ROOT / "scripts/check-hypr-lua-parity"
    for relative, old, new in (
        ("lua/rules.lua", 'class="^(Spotify|spotify)$"', 'class="^(SpotifyBROKEN|spotify)$"'),
        ("lua/rules.lua", 'namespace="^(noctalia-background-.*)$"', 'namespace="^(noctalia-broken-.*)$"'),
        ("lua/appearance.lua", "workspace_swipe_distance=300", "workspace_swipe_distance=301"),
    ):
        lua_root = tmp_path / relative.replace("lua/" + relative.split("/")[-1], "lua")
        lua_root.mkdir(parents=True, exist_ok=True)
        source = HYPR / relative
        body = source.read_text()
        assert old in body
        (lua_root / source.name).write_text(body.replace(old, new, 1))
        result = subprocess.run([checker, "--lua-root", lua_root], capture_output=True, text=True)
        assert result.returncode != 0, (relative, result.stdout, result.stderr)


def test_checker_detects_exact_typed_config_value_sabotage(tmp_path):
    checker = ROOT / "scripts/check-hypr-lua-parity"
    for old, new, semantic in (
        ("gaps_out=8", "gaps_out=9", "general.gaps_out"),
        ("allow_tearing=false", "allow_tearing=true", "general.allow_tearing"),
        ("gaps_out=8, gradient_rounding", "gaps_out=9, gradient_rounding", "group.groupbar.gaps_out"),
    ):
        lua_root = tmp_path / semantic.replace(".", "-")
        lua_root.mkdir()
        source = HYPR / "lua/appearance.lua"
        body = source.read_text()
        assert old in body
        (lua_root / source.name).write_text(body.replace(old, new, 1))
        result = subprocess.run([checker, "--lua-root", lua_root], capture_output=True, text=True)
        assert result.returncode != 0, (semantic, result.stdout, result.stderr)
        assert semantic in result.stderr
