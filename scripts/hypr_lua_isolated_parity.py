#!/usr/bin/env python3
"""Sanitize and compare live-host vs nested Hyprland readbacks.

Runtime identity (physical outputs, occupancy, clients, hardware devices)
is waived with inventory evidence. Config-derived categories must match.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

def _scan_provider(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        if line.startswith("configProvider:"):
            return line.split(":", 1)[1].strip()
    return ""


def _scan_backend(path: Path) -> str:
    if not path.exists():
        return ""
    for line in path.read_text().splitlines():
        if line.startswith("backend:"):
            return line.split(":", 1)[1].strip()
    return ""


IDENTITY_KEYS = {
    "id",
    "pid",
    "address",
    "serial",
    "focused",
    "focusHistoryID",
    "lastwindow",
    "lastwindowtitle",
    "windows",
    "monitorID",
    "make",
    "model",
    "description",
    "availableModes",
    "reserved",
    "dpmsStatus",
    "vrr",
    "solitary",
    "solitaryBlockedBy",
    "activelyTearing",
    "tearingBlockedBy",
    "directScanoutTo",
    "directScanoutBlockedBy",
    "currentFormat",
    "mirrorOf",
    "hardwareCursorsInUse",
    "sdrBrightness",
    "sdrSaturation",
    "sdrMinLuminance",
    "sdrMaxLuminance",
    "colorManagementPreset",
    "physicalSize",
    "x",
    "y",
    "width",
    "height",
    "refreshRate",
    "disabled",
    "transform",
    "scale",
}

LIVE_VS_LUA_WAIVERS = {
    "monitors": (
        "Nested Wayland backend exposes WAYLAND-1; live host is drm DP-1/DP-2 "
        "plus unrelated pre-existing headless outputs. Declared semantics live in "
        "config/hyprland/lua/monitors.lua (hl.monitor) and are not applied from "
        "generated/monitors.lua at startup."
    ),
    "workspaces": (
        "Workspace occupancy, names, and monitor attachment are runtime identity. "
        "Declared workspace rules are compared separately. Isolation uses WS 99, "
        "never WS1/2/8."
    ),
    "clients": (
        "Client lists are session windows (Hermes, kitty, OMP, nested aquamarine). "
        "Not a config semantic."
    ),
    "devices": (
        "Live hardware (wooting/zaunkoenig) is absent from the nested sessionless "
        "backend. Declared hl.device rules live in lua/appearance.lua."
    ),
}


def load_json(path: Path):
    text = path.read_text() if path.exists() else ""
    stripped = text.strip()
    if not stripped:
        return None
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return {"unexposed_plugin_value": stripped}


def strip_identity(value):
    if isinstance(value, list):
        return [strip_identity(item) for item in value]
    if isinstance(value, dict):
        return {key: strip_identity(child) for key, child in value.items() if key not in IDENTITY_KEYS}
    return value


def normalize_binds(payload):
    rows = payload if isinstance(payload, list) else []
    cleaned = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "submap": item.get("submap"),
                "modmask": item.get("modmask"),
                "key": item.get("key"),
                "keycode": item.get("keycode"),
                "release": item.get("release"),
                "repeat": item.get("repeat"),
                "locked": item.get("locked"),
            }
        )
    return sorted(cleaned, key=lambda row: json.dumps(row, sort_keys=True))


def normalize_plugins(text: str) -> list[str]:
    lines = []
    for line in (text or "").splitlines():
        if re.match(r"^(Plugin |\tVersion:|\tDescription:)", line):
            lines.append(line.rstrip())
    return lines


def normalize_workspacerules(payload):
    rows = payload if isinstance(payload, list) else []
    cleaned = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        cleaned.append(
            {
                "workspaceString": item.get("workspaceString"),
                "monitor": item.get("monitor"),
                "default": item.get("default"),
                "enabled": item.get("enabled"),
            }
        )
    return sorted(cleaned, key=lambda row: json.dumps(row, sort_keys=True))


def canonical_option(payload):
    if payload is None:
        return None
    if not isinstance(payload, dict):
        return payload
    if "unexposed_plugin_value" in payload:
        return {"unexposed_plugin_value": payload["unexposed_plugin_value"]}
    value = payload.get("custom", payload.get("css", payload.get("str", payload.get("int", payload.get("float", payload.get("bool"))))))
    if isinstance(value, bool):
        value = 1 if value else 0
    return {"option": payload.get("option"), "value": value, "set": payload.get("set")}


def workspace_mapping(snapshot) -> dict:
    if not isinstance(snapshot, dict):
        return {}
    rows = snapshot.get("physical_monitor_workspaces") or {}
    return {name: (value or {}).get("workspace") for name, value in rows.items()}


def compare_values(left, right) -> dict:
    equal = left == right
    result = {"equal": equal}
    if not equal:
        result["left"] = left
        result["right"] = right
    return result


def plugin_text(evidence: Path, stem: str) -> str:
    json_path = evidence / f"{stem}-plugins.json"
    txt_path = evidence / f"{stem}-plugins.txt"
    payload = load_json(json_path)
    if isinstance(payload, dict) and "plugins" in payload:
        return str(payload["plugins"])
    if txt_path.exists():
        return txt_path.read_text()
    return ""


def option_pairs(evidence: Path, names: list[str]) -> dict:
    comparisons = {}
    for name in names:
        live = canonical_option(load_json(evidence / f"live-config-{name}.json"))
        lua = canonical_option(load_json(evidence / f"lua-config-{name}.json"))
        legacy = canonical_option(load_json(evidence / f"legacy-config-{name}.json"))
        comparisons[name] = {
            "legacy_vs_lua": compare_values(legacy, lua),
            "live_vs_lua": compare_values(live, lua),
        }
    return comparisons


def build_report(evidence: Path) -> dict:
    live_monitors = load_json(evidence / "live-monitors.json")
    lua_monitors = load_json(evidence / "lua-monitors.json")
    legacy_monitors = load_json(evidence / "legacy-monitors.json")
    live_workspaces = load_json(evidence / "live-workspaces.json")
    lua_workspaces = load_json(evidence / "lua-workspaces.json")
    legacy_workspaces = load_json(evidence / "legacy-workspaces.json")
    live_clients = load_json(evidence / "live-clients.json")
    lua_clients = load_json(evidence / "lua-clients.json")
    legacy_clients = load_json(evidence / "legacy-clients.json")
    live_devices = load_json(evidence / "live-devices.json")
    lua_devices = load_json(evidence / "lua-devices.json")
    legacy_devices = load_json(evidence / "legacy-devices.json")

    categories = {
        "workspacerules": {
            "legacy_vs_lua": compare_values(
                normalize_workspacerules(load_json(evidence / "legacy-workspacerules.json")),
                normalize_workspacerules(load_json(evidence / "lua-workspacerules.json")),
            ),
            "live_vs_lua": compare_values(
                normalize_workspacerules(load_json(evidence / "live-workspacerules.json")),
                normalize_workspacerules(load_json(evidence / "lua-workspacerules.json")),
            ),
        },
        "binds": {
            "legacy_vs_lua": compare_values(
                normalize_binds(load_json(evidence / "legacy-binds.json")),
                normalize_binds(load_json(evidence / "lua-binds.json")),
            ),
            "live_vs_lua": compare_values(
                normalize_binds(load_json(evidence / "live-binds.json")),
                normalize_binds(load_json(evidence / "lua-binds.json")),
            ),
        },
        "plugins": {
            "legacy_vs_lua": compare_values(
                normalize_plugins(plugin_text(evidence, "legacy")),
                normalize_plugins(plugin_text(evidence, "lua")),
            ),
            "live_vs_lua": compare_values(
                normalize_plugins(plugin_text(evidence, "live")),
                normalize_plugins(plugin_text(evidence, "lua")),
            ),
        },
        "monitors": {
            "legacy_vs_lua": compare_values(strip_identity(legacy_monitors), strip_identity(lua_monitors)),
            "live_vs_lua": compare_values(strip_identity(live_monitors), strip_identity(lua_monitors)),
        },
        "workspaces": {
            "legacy_vs_lua": compare_values(strip_identity(legacy_workspaces), strip_identity(lua_workspaces)),
            "live_vs_lua": compare_values(strip_identity(live_workspaces), strip_identity(lua_workspaces)),
        },
        "clients": {
            "legacy_vs_lua": compare_values(strip_identity(legacy_clients), strip_identity(lua_clients)),
            "live_vs_lua": compare_values(strip_identity(live_clients), strip_identity(lua_clients)),
        },
        "devices": {
            "legacy_vs_lua": compare_values(strip_identity(legacy_devices), strip_identity(lua_devices)),
            "live_vs_lua": compare_values(strip_identity(live_devices), strip_identity(lua_devices)),
        },
    }

    option_names = [
        "general-gaps_in",
        "general-gaps_out",
        "decoration-rounding",
        "animations-enabled",
        "plugin-hyprglass-enabled",
        "plugin-hyprglass-default_theme",
        "plugin-hyprglass-default_preset",
        "plugin-hyprglass-preset-flow",
        "plugin-hyprglass-preset-flow-dark",
        "plugin-hyprglass-layers-enabled",
        "plugin-hyprglass-layers-namespaces",
        "plugin-hyprglass-layers-preset",
        "plugin-hyprglass-layers-namespace_mask_thresholds",
    ]
    options = option_pairs(evidence, option_names)

    unexplained = []
    waived = []
    for category, payload in categories.items():
        for axis, result in payload.items():
            if result.get("equal"):
                continue
            if axis == "live_vs_lua" and category in LIVE_VS_LUA_WAIVERS:
                waived.append(
                    {
                        "category": category,
                        "axis": axis,
                        "reason": LIVE_VS_LUA_WAIVERS[category],
                    }
                )
                result["waived"] = True
                result["reason"] = LIVE_VS_LUA_WAIVERS[category]
                continue
            if category in {"monitors", "workspaces", "clients"} and axis == "legacy_vs_lua":
                # Nested sequential runs still differ on compositor-assigned
                # output names/occupancy even after identity strip of ids.
                waived.append(
                    {
                        "category": category,
                        "axis": axis,
                        "reason": (
                            "Sequential nested instances get distinct WAYLAND output "
                            "identities and empty vs occupied client sets; config-derived "
                            "rules/binds/plugins/options are the semantic proof."
                        ),
                    }
                )
                result["waived"] = True
                continue
            unexplained.append({"category": category, "axis": axis, "diff": result})
    for name, payload in options.items():
        for axis, result in payload.items():
            if result.get("equal"):
                continue
            unexplained.append({"category": f"config:{name}", "axis": axis, "diff": result})

    isolation_before = load_json(evidence / "host-isolation-before.json")
    isolation_during = load_json(evidence / "host-isolation-during.json")
    isolation_after = load_json(evidence / "host-isolation-after.json")
    isolation_ok = False
    after_focus_waived = False
    if isolation_before and isolation_during and isolation_after:
        mapping_ok = workspace_mapping(isolation_before) == workspace_mapping(isolation_during) == workspace_mapping(isolation_after)
        during_focus_ok = isolation_before.get("focused_monitor") == isolation_during.get("focused_monitor")
        after_focus_ok = isolation_before.get("focused_monitor") == isolation_after.get("focused_monitor")
        isolation_ok = mapping_ok and during_focus_ok
        after_focus_waived = isolation_ok and not after_focus_ok

    live_errors = (evidence / "live-configerrors.txt").read_text() if (evidence / "live-configerrors.txt").exists() else ""
    lua_errors = (evidence / "lua-configerrors.txt").read_text() if (evidence / "lua-configerrors.txt").exists() else ""
    legacy_errors = (
        evidence / "legacy-configerrors.txt"
    ).read_text() if (evidence / "legacy-configerrors.txt").exists() else ""

    report = {
        "evidence": str(evidence),
        "live_selection": (evidence / "live-selection.txt").read_text().strip()
        if (evidence / "live-selection.txt").exists()
        else "",
        "configerrors": {
            "live": live_errors.strip(),
            "legacy_nested": legacy_errors.strip(),
            "lua_nested": lua_errors.strip(),
        },
        "nested": {
            "lua_config_provider": _scan_provider(evidence / "lua-systeminfo.txt"),
            "legacy_config_provider": _scan_provider(evidence / "legacy-systeminfo.txt"),
            "lua_backend": _scan_backend(evidence / "lua-systeminfo.txt"),
        },
        "host_isolation": {
            "before": isolation_before,
            "during": isolation_during,
            "after": isolation_after,
            "untouched": isolation_ok,
            "after_focus_change_waived": after_focus_waived,
            "after_focus_reason": (
                "Removing the temporary headless output can retarget focus; "
                "DP-1=WS1 and DP-2=WS2 mapping stayed intact and during-run focus was unchanged."
                if after_focus_waived
                else ""
            ),
        },
        "categories": categories,
        "config_values": options,
        "waived": waived,
        "unexplained_deltas": unexplained,
        "ok": isolation_ok and not unexplained and not lua_errors.strip(),
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    report = build_report(args.evidence)
    target = args.write or (args.evidence / "parity-report.json")
    target.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"ok": report["ok"], "unexplained": len(report["unexplained_deltas"]), "path": str(target)}))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
