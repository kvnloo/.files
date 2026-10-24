"""Isolated nested Hyprland Lua parity sanitizer (no compositor launch)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/prove-hypr-lua-isolated-parity"
COMPARE = ROOT / "scripts/hypr_lua_isolated_parity.py"


def test_harness_refuses_protected_workspaces_and_documents_isolation():
    body = SCRIPT.read_text()
    assert "protected workspaces 1, 2, 8" in body
    assert "hyprland.lua" in body
    assert "configerrors" in body
    assert "parity-report.json" in body
    assert "phone-display.sh" not in body
    result = subprocess.run([SCRIPT, "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "protected workspaces" in result.stdout


def test_live_vs_lua_workspacerules_must_match_and_monitors_are_waived(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    rules = [
        {"workspaceString": "20", "enabled": True, "monitor": "PHONE", "default": True},
        {"workspaceString": "1", "enabled": True, "monitor": "DP-1", "default": True},
        {"workspaceString": "10", "enabled": True, "monitor": "HDMI-A-1", "default": True},
    ]
    isolation = {
        "physical_monitor_workspaces": {
            "DP-1": {"focused": False, "workspace": 1},
            "DP-2": {"focused": True, "workspace": 2},
        },
        "focused_monitor": "DP-2",
    }
    for stem in ("live", "legacy", "lua"):
        (evidence / f"{stem}-workspacerules.json").write_text(json.dumps(rules))
        (evidence / f"{stem}-binds.json").write_text("[]")
        (evidence / f"{stem}-plugins.txt").write_text(
            "Plugin hyprglass by Hyprnux:\n\tVersion: 1.0.0\n\tDescription: Apple-style Liquid Glass effect\n"
        )
        (evidence / f"{stem}-plugins.json").write_text(
            json.dumps(
                {
                    "plugins": "Plugin hyprglass by Hyprnux:\n\tVersion: 1.0.0\n\tDescription: Apple-style Liquid Glass effect\n"
                }
            )
        )
        (evidence / f"{stem}-devices.json").write_text("{}\n")
        (evidence / f"{stem}-clients.json").write_text("[]")
        (evidence / f"{stem}-workspaces.json").write_text("[]")
        (evidence / f"{stem}-configerrors.txt").write_text("")
    (evidence / "live-monitors.json").write_text(json.dumps([{"name": "DP-1", "id": 0}, {"name": "DP-2", "id": 1}]))
    (evidence / "legacy-monitors.json").write_text(json.dumps([{"name": "WAYLAND-1", "id": 0}]))
    (evidence / "lua-monitors.json").write_text(json.dumps([{"name": "WAYLAND-1", "id": 0}]))
    for axis in ("before", "during", "after"):
        (evidence / f"host-isolation-{axis}.json").write_text(json.dumps(isolation))
    (evidence / "live-selection.txt").write_text("/workspace/.files/config/hyprland/hyprland.legacy.conf\n")
    option = {"option": "general:gaps_out", "int": 8, "set": True}
    for stem in ("live", "legacy", "lua"):
        (evidence / f"{stem}-config-general-gaps_out.json").write_text(json.dumps(option))
        for name in (
            "general-gaps_in",
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
        ):
            (evidence / f"{stem}-config-{name}.json").write_text(json.dumps({"option": name, "int": 1, "set": True}))

    result = subprocess.run(
        ["python3", str(COMPARE), "--evidence", str(evidence), "--write", str(evidence / "parity-report.json")],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((evidence / "parity-report.json").read_text())
    assert report["ok"] is True
    assert report["categories"]["workspacerules"]["live_vs_lua"]["equal"] is True
    assert report["categories"]["monitors"]["live_vs_lua"]["equal"] is False
    assert report["categories"]["monitors"]["live_vs_lua"]["waived"] is True
    assert report["unexplained_deltas"] == []
    assert report["host_isolation"]["untouched"] is True


def test_after_cleanup_focus_change_is_waived_when_workspace_mapping_holds(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    isolation_before = {
        "physical_monitor_workspaces": {
            "DP-1": {"focused": False, "workspace": 1},
            "DP-2": {"focused": True, "workspace": 2},
        },
        "focused_monitor": "DP-2",
    }
    isolation_after = {
        "physical_monitor_workspaces": {
            "DP-1": {"focused": True, "workspace": 1},
            "DP-2": {"focused": False, "workspace": 2},
        },
        "focused_monitor": "DP-1",
    }
    for stem in ("live", "legacy", "lua"):
        (evidence / f"{stem}-workspacerules.json").write_text("[]")
        (evidence / f"{stem}-binds.json").write_text("[]")
        (evidence / f"{stem}-plugins.txt").write_text("")
        (evidence / f"{stem}-plugins.json").write_text('{"plugins":""}')
        (evidence / f"{stem}-devices.json").write_text("{}")
        (evidence / f"{stem}-clients.json").write_text("[]")
        (evidence / f"{stem}-workspaces.json").write_text("[]")
        (evidence / f"{stem}-monitors.json").write_text("[]")
        (evidence / f"{stem}-configerrors.txt").write_text("")
    (evidence / "host-isolation-before.json").write_text(json.dumps(isolation_before))
    (evidence / "host-isolation-during.json").write_text(json.dumps(isolation_before))
    (evidence / "host-isolation-after.json").write_text(json.dumps(isolation_after))
    result = subprocess.run(
        ["python3", str(COMPARE), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads((evidence / "parity-report.json").read_text())
    assert report["ok"] is True
    assert report["host_isolation"]["untouched"] is True
    assert report["host_isolation"]["after_focus_change_waived"] is True


def test_workspacerule_mismatch_is_unexplained(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    live = [{"workspaceString": "1", "enabled": True, "monitor": "DP-1", "default": True}]
    lua = [{"workspaceString": "1", "enabled": True, "monitor": "DP-2", "default": True}]
    isolation = {"physical_monitor_workspaces": {}, "focused_monitor": "DP-2"}
    for stem, payload in (("live", live), ("legacy", live), ("lua", lua)):
        (evidence / f"{stem}-workspacerules.json").write_text(json.dumps(payload))
        (evidence / f"{stem}-binds.json").write_text("[]")
        (evidence / f"{stem}-plugins.txt").write_text("")
        (evidence / f"{stem}-plugins.json").write_text('{"plugins":""}')
        (evidence / f"{stem}-devices.json").write_text("{}")
        (evidence / f"{stem}-clients.json").write_text("[]")
        (evidence / f"{stem}-workspaces.json").write_text("[]")
        (evidence / f"{stem}-monitors.json").write_text("[]")
        (evidence / f"{stem}-configerrors.txt").write_text("")
    for axis in ("before", "during", "after"):
        (evidence / f"host-isolation-{axis}.json").write_text(json.dumps(isolation))
    result = subprocess.run(
        ["python3", str(COMPARE), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads((evidence / "parity-report.json").read_text())
    assert report["ok"] is False
    assert any(item["category"] == "workspacerules" for item in report["unexplained_deltas"])
