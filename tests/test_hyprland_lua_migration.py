import json
import re
import runpy
import subprocess
from pathlib import Path

import pytest

from hypr_lua_fixtures import migration_inventory

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


def effective_repository_scalars():
    """Read ordered repository sources independently of the conversion generator."""
    values = {}
    seen = set()
    repeated = {
        "monitor", "workspace", "windowrule", "layerrule", "env", "exec-once",
        "exec", "bind", "binde", "bindm", "bindl", "bindel", "bindr", "unbind",
        "bezier", "animation", "gesture", "spatialoverview-gesture",
        "submap", "plugin",
    }

    def visit(path):
        if path in seen:
            return
        seen.add(path)
        stack = []
        for raw in path.read_text().splitlines():
            text = raw.partition("#")[0].strip()
            if not text:
                continue
            if text.endswith("{"):
                stack.append(text[:-1].strip())
                continue
            if text == "}":
                stack.pop()
                continue
            key, separator, value = text.partition("=")
            assert separator, (path, text)
            key, value = key.strip(), value.strip()
            if key == "source":
                for prefix in ("/home/kvn/workspace/.files/", "~/workspace/.files/"):
                    if value.startswith(prefix):
                        target = ROOT / value[len(prefix):]
                        if target.is_file():
                            visit(target)
                        break
                continue
            if key == "preset" and stack == ["plugin", "hyprglass"]:
                continue
            if key in repeated or key.startswith("$") or "device" in stack:
                continue
            normalized = ".".join([*stack, key]).replace(":", ".").replace("-", "_")
            values[normalized] = value

    visit(LEGACY)
    return values


def test_inventory_classifies_every_legacy_directive_exactly_once(migration_inventory):
    inventory = json.loads(migration_inventory.read_text())
    expected = legacy_directive_lines()
    actual = [(item["line"], item["directive"]) for item in inventory["directives"]]
    assert actual == expected
    assert all(item["owner"].endswith(".lua") for item in inventory["directives"])
    assert inventory["unclassified"] == []


def test_entrypoint_is_modular_lua_and_legacy_sources_are_owned_by_lua():
    entrypoint = (HYPR / "hyprland.lua").read_text()
    required = set(re.findall(r'require\("([^"]+)"\)', entrypoint))
    assert required == {
        "lua.monitors", "lua.environment", "lua.bridges", "lua.appearance", "lua.rules",
        "lua.binds", "lua.autostart",
    }
    all_lua = "\n".join(path.read_text() for path in HYPR.glob("lua/*.lua"))
    assert "source =" not in all_lua
    assert "colors-hyprland.conf" not in all_lua


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


def test_hyprglass_semantics_are_preserved_in_lua_and_inventory(migration_inventory):
    appearance = (HYPR / "lua/appearance.lua").read_text()
    inventory = json.loads(migration_inventory.read_text())
    effective = effective_repository_scalars()
    paths = {
        "plugin.hyprglass.enabled", "plugin.hyprglass.default_theme",
        "plugin.hyprglass.default_preset", "plugin.hyprglass.layers.enabled",
        "plugin.hyprglass.layers.namespaces", "plugin.hyprglass.layers.preset",
        "group.groupbar.gradients", "group.groupbar.height",
        "group.groupbar.indicator_height", "group.groupbar.indicator_gap",
        "group.groupbar.text_offset", "plugin.spatialoverview.animation.speed",
    }
    semantics = {
        item["path"].replace(":", ".").replace("-", "_"): item["value"]
        for item in inventory["semantics"]
    }
    actual = runpy.run_path(str(ROOT / "scripts/hypr_lua_semantics.py"))["config_values"](appearance)

    def normalized(value):
        value = str(value).strip().strip('"').strip("'")
        if value in {"true", "false"}:
            return int(value == "true")
        try:
            return float(value)
        except ValueError:
            return value

    for path in paths:
        assert path in effective
        assert normalized(semantics[path]) == normalized(effective[path]), path
        assert normalized(actual[path]) == normalized(effective[path]), path


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


def test_hyprglass_defers_native_lua_api_until_hyprland_start():
    appearance = (HYPR / "lua/appearance.lua").read_text()
    harness = (ROOT / "scripts/verify-hypr-lua-nested").read_text()
    assert 'local hg=hl.plugin.hyprglass' in appearance
    assert appearance.index("hl.plugin.load(") < appearance.index('hl.on("hyprland.start"')
    deferred = appearance.split('hl.on("hyprland.start", function()', 1)[1]
    assert 'error("hyprglass Lua API unavailable after plugin load")' in deferred
    assert re.search(r"hl\.config\(\{plugin=\{", deferred)
    for preset in ("Clear", "Frost", "Smoke", "Prism", "MonDP1", "MonDP2", "Slate"):
        assert f'hg.preset("{preset}"' in deferred
    assert 'namespace_presets=' in deferred
    assert 'keyword plugin:hyprglass' not in harness


@pytest.mark.live_system
def test_production_verify_config_has_no_error_text():
    result = subprocess.run(
        ["Hyprland", "--verify-config", "-c", HYPR / "hyprland.lua"],
        capture_output=True,
        text=True,
    )
    output = result.stdout + result.stderr
    assert result.returncode == 0, output
    assert "error" not in output.lower(), output
    assert "config ok" in output.lower(), output


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
        ("8", "9", "general.gaps_out"),
        ("false", "true", "general.allow_tearing"),
        ("8", "9", "group.groupbar.gaps_out"),
    ):
        lua_root = tmp_path / semantic.replace(".", "-")
        lua_root.mkdir()
        source = HYPR / "lua/appearance.lua"
        body = source.read_text()
        parts = semantic.split(".")
        offset = 0
        for table in parts[:-1]:
            match = re.search(rf"\b{re.escape(table)}\s*=\s*\{{", body[offset:])
            assert match is not None, semantic
            offset += match.end()
        match = re.search(rf"\b{re.escape(parts[-1])}\s*=\s*({re.escape(old)})\b", body[offset:])
        assert match is not None, semantic
        start, end = offset + match.start(1), offset + match.end(1)
        (lua_root / source.name).write_text(body[:start] + new + body[end:])
        result = subprocess.run([checker, "--lua-root", lua_root], capture_output=True, text=True)
        assert result.returncode != 0, (semantic, result.stdout, result.stderr)
        assert semantic in result.stderr
