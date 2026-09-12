"""E2E nested output lifecycle, conversion sabotage, and rollback (no live activate)."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HARNESS = ROOT / "scripts/prove-hypr-lua-e2e-lifecycle"
COMPARE = ROOT / "scripts/hypr_lua_e2e_lifecycle.py"
SABOTAGE = ROOT / "scripts/prove-hypr-lua-conversion-sabotage"
ROLLBACK = ROOT / "scripts/hypr-lua-config"
DOCS = ROOT / "docs/hypr-lua-migration.md"
HYPR = ROOT / "config/hyprland"
LIVE_LINK = Path.home() / ".config/hypr/hyprland.conf"


def test_e2e_harness_refuses_protected_workspaces_and_documents_lifecycle():
    body = HARNESS.read_text()
    assert "protected workspaces 1, 2, 8" in body
    assert "phone-display.sh" in body
    assert "gui-e2e-display.sh" in body
    assert "recover" in body
    assert "keyword can't work with non-legacy parsers. Use eval." in body
    assert "hyprland.lua" in body
    assert "activate" not in body.splitlines()[0]
    assert "systemctl" not in body or "wayland-wm@hyprland" not in body
    result = subprocess.run([HARNESS, "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "protected workspaces" in result.stdout
    denied = subprocess.run(
        [HARNESS],
        capture_output=True,
        text=True,
        env={**os.environ, "HYPR_LUA_NESTED_WORKSPACE": "1"},
        check=False,
    )
    assert denied.returncode == 3
    assert "protected" in denied.stderr.lower() or "refusing" in denied.stderr.lower()


def test_lifecycle_report_requires_add_remove_recover_and_cleanup(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    isolation = {
        "physical_monitor_workspaces": {
            "DP-1": {"focused": False, "workspace": 1},
            "DP-2": {"focused": True, "workspace": 2},
        },
        "focused_monitor": "DP-2",
    }
    for axis in ("before", "during", "after"):
        (evidence / f"host-isolation-{axis}.json").write_text(json.dumps(isolation))
    (evidence / "live-selection.txt").write_text(str(HYPR / "hyprland.legacy.conf") + "\n")
    (evidence / "lua-configerrors.txt").write_text("")
    (evidence / "lua-systeminfo.txt").write_text("configProvider: lua\nbackend: wayland\n")
    (evidence / "controller-lifecycle.json").write_text(
        json.dumps({"name": "E2E-INNER", "added": True, "removed": True, "recovered": True})
    )
    (evidence / "phone-lifecycle.json").write_text(
        json.dumps({"name": "PHONE", "added": True, "removed": True, "recovered": True})
    )
    (evidence / "sabotage.json").write_text(
        json.dumps(
            {
                "monitor": {"visible": True, "recovered": True},
                "window": {"visible": True, "recovered": True},
                "bind": {"visible": True, "recovered": True},
                "source": {"visible": True, "recovered": True},
            }
        )
    )
    (evidence / "rollback.json").write_text(
        json.dumps(
            {
                "command": "scripts/hypr-lua-config rollback",
                "target": str(HYPR / "hyprland.legacy.conf"),
                "proven": True,
            }
        )
    )
    (evidence / "result.json").write_text(json.dumps({"cleanup_complete": True, "exit_status": 0}))
    report_path = evidence / "lifecycle-report.json"
    result = subprocess.run(
        ["python3", str(COMPARE), "--evidence", str(evidence), "--write", str(report_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    report = json.loads(report_path.read_text())
    assert report["ok"] is True
    assert report["controller"]["recovered"] is True
    assert report["phone"]["recovered"] is True
    assert report["sabotage"]["all_recovered"] is True
    assert report["rollback"]["proven"] is True
    assert report["cleanup_complete"] is True
    assert report["lua_active_for_login"] is False


def test_lifecycle_report_fails_when_recover_is_missing(tmp_path: Path):
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    isolation = {"physical_monitor_workspaces": {}, "focused_monitor": "DP-2"}
    for axis in ("before", "during", "after"):
        (evidence / f"host-isolation-{axis}.json").write_text(json.dumps(isolation))
    (evidence / "live-selection.txt").write_text(str(HYPR / "hyprland.legacy.conf") + "\n")
    (evidence / "lua-configerrors.txt").write_text("")
    (evidence / "lua-systeminfo.txt").write_text("configProvider: lua\nbackend: wayland\n")
    (evidence / "controller-lifecycle.json").write_text(
        json.dumps({"name": "E2E-INNER", "added": True, "removed": True, "recovered": False})
    )
    (evidence / "phone-lifecycle.json").write_text(
        json.dumps({"name": "PHONE", "added": True, "removed": True, "recovered": True})
    )
    (evidence / "sabotage.json").write_text(
        json.dumps(
            {
                "monitor": {"visible": True, "recovered": True},
                "window": {"visible": True, "recovered": True},
                "bind": {"visible": True, "recovered": True},
                "source": {"visible": True, "recovered": True},
            }
        )
    )
    (evidence / "rollback.json").write_text(json.dumps({"proven": True, "target": "legacy"}))
    (evidence / "result.json").write_text(json.dumps({"cleanup_complete": True, "exit_status": 0}))
    result = subprocess.run(
        ["python3", str(COMPARE), "--evidence", str(evidence)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1
    report = json.loads((evidence / "lifecycle-report.json").read_text())
    assert report["ok"] is False


def test_conversion_sabotage_script_covers_monitor_window_bind_and_source():
    body = SABOTAGE.read_text()
    for token in ("monitors.lua", "rules.lua", "binds.lua", "bridges.lua", "parity mismatch"):
        assert token in body
    result = subprocess.run([SABOTAGE, "--help"], capture_output=True, text=True, check=False)
    assert result.returncode == 0
    assert "monitor" in result.stdout
    assert "window" in result.stdout
    assert "bind" in result.stdout
    assert "source" in result.stdout


def test_rollback_command_reselects_legacy_in_sandbox_without_restart(tmp_path: Path):
    env = {**os.environ, "HOME": str(tmp_path), "XDG_CONFIG_HOME": str(tmp_path / "config")}
    script = ROLLBACK
    subprocess.run([script, "activate"], check=True, env=env)
    link = tmp_path / "config/hypr/hyprland.conf"
    assert link.resolve() == HYPR / "hyprland.lua"
    subprocess.run([script, "rollback"], check=True, env=env)
    assert link.resolve() == HYPR / "hyprland.legacy.conf"
    body = script.read_text()
    assert "ln -sfn" in body
    assert "hyprctl reload" not in body
    assert "systemctl" not in body


def test_live_login_still_selects_legacy_conf():
    assert LIVE_LINK.is_symlink()
    assert LIVE_LINK.resolve() == HYPR / "hyprland.legacy.conf"


def test_migration_test_rollback_docs_exist():
    text = DOCS.read_text()
    for token in (
        "hyprland.lua",
        "hyprland.legacy.conf",
        "scripts/hypr-lua-config rollback",
        "prove-hypr-lua-e2e-lifecycle",
        "prove-hypr-lua-conversion-sabotage",
        "gui-e2e-display.sh",
        "phone-display.sh",
        "workspaces 1",
        "workspace 8",
        "do not restart",
        "independent reviewer",
    ):
        assert token in text, token
