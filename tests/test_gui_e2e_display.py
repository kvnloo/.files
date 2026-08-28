"""Isolated GUI display controller — dry-run plus live Xvfb safety."""

from __future__ import annotations

import json
import os
import signal
import subprocess
import time
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CTRL = REPO / "scripts" / "gui-e2e-display.sh"
KNOWN_XVFB = Path(
    "/home/kvn/.hermes/kanban/boards/hermes-agent/workspaces/"
    "t_6080dad3/xvfb-root/usr/bin/Xvfb"
)


def run(
    *args: str,
    env: dict[str, str] | None = None,
    lease_root: Path,
    check: bool = False,
    dry_run: bool = True,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ | {
        "GUI_E2E_LEASE_DIR": str(lease_root),
        "PATH": os.environ.get("PATH", ""),
    }
    if dry_run:
        merged["GUI_E2E_DRY_RUN"] = "1"
    else:
        merged.pop("GUI_E2E_DRY_RUN", None)
    if env:
        merged.update(env)
    return subprocess.run(
        ["bash", str(CTRL), *args],
        cwd=REPO,
        env=merged,
        check=check,
        capture_output=True,
        text=True,
    )


@pytest.fixture
def lease_root(tmp_path: Path) -> Path:
    root = tmp_path / "leases"
    root.mkdir()
    return root


def test_help_exits_zero() -> None:
    completed = subprocess.run(
        ["bash", str(CTRL), "--help"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    assert "usage:" in completed.stdout


def test_refuses_protected_workspaces(lease_root: Path) -> None:
    for ws in ("1", "2", "8"):
        completed = run(
            "--workspace",
            ws,
            "--lease-id",
            "t",
            "start",
            lease_root=lease_root,
        )
        assert completed.returncode == 3, completed.stderr
        assert "protected workspace" in completed.stderr


def test_xvfb_default_writes_lease_and_proof(lease_root: Path) -> None:
    completed = run(
        "--tier",
        "xvfb",
        "--width",
        "1920",
        "--height",
        "1080",
        "--scale",
        "2",
        "--workspace",
        "9",
        "--class",
        "HermesE2E-42",
        "--lease-id",
        "unit",
        "start",
        lease_root=lease_root,
        check=True,
    )
    assert completed.returncode == 0
    lease = json.loads((lease_root / "unit" / "lease.json").read_text())
    assert lease["tier"] == "xvfb"
    assert lease["width"] == 1920
    assert lease["height"] == 1080
    assert lease["scale"] == 2
    assert lease["workspace"] == 9
    assert lease["window_class"] == "HermesE2E-42"
    before = json.loads((lease_root / "unit" / "proof-before.json").read_text())
    after = json.loads((lease_root / "unit" / "proof-after.json").read_text())
    assert before["protected_untouched"] is True
    assert after["protected_untouched"] is True
    assert after["tier"] == "xvfb"
    assert "physical_monitor_workspaces" in after


def test_hypr_headless_dry_run_lease(lease_root: Path) -> None:
    completed = run(
        "--tier",
        "hypr-headless",
        "--workspace",
        "20",
        "--output",
        "E2E-TEST",
        "--lease-id",
        "hypr",
        "start",
        lease_root=lease_root,
        check=True,
    )
    assert completed.returncode == 0
    lease = json.loads((lease_root / "hypr" / "lease.json").read_text())
    assert lease["tier"] == "hypr-headless"
    assert lease["workspace"] == 20
    assert lease["output"] == "E2E-TEST"
    script = (REPO / "scripts" / "gui-e2e-display.sh").read_text()
    assert "dispatch focusmonitor" not in script
    assert "dispatch workspace" not in script
    assert "workspace ${workspace} silent" in script


def test_stop_preserves_proof_evidence(lease_root: Path) -> None:
    run(
        "--lease-id",
        "gone",
        "--workspace",
        "9",
        "start",
        lease_root=lease_root,
        check=True,
    )
    assert (lease_root / "gone" / "lease.json").is_file()
    run("--lease-id", "gone", "stop", lease_root=lease_root, check=True)
    assert (lease_root / "gone").is_dir()
    assert (lease_root / "gone" / "proof-before.json").is_file()
    assert (lease_root / "gone" / "proof-after.json").is_file()
    assert (lease_root / "gone" / "lease-stopped.json").is_file()
    assert not (lease_root / "gone" / "lease.json").exists()


def test_status_inactive_without_lease(lease_root: Path) -> None:
    completed = run("--lease-id", "missing", "status", lease_root=lease_root, check=True)
    payload = json.loads(completed.stdout)
    assert payload["active"] is False


def test_obs_workspace_eight_blocked_even_with_hypr_tier(lease_root: Path) -> None:
    completed = run(
        "--tier",
        "hypr-headless",
        "--workspace",
        "8",
        "start",
        lease_root=lease_root,
    )
    assert completed.returncode == 3


def test_protected_workspace_sabotage_fails_closed(lease_root: Path) -> None:
    completed = run(
        "--workspace",
        "1",
        "--tier",
        "xvfb",
        "run",
        "--",
        "true",
        lease_root=lease_root,
    )
    assert completed.returncode == 3
    completed = run(
        "--workspace",
        "2",
        "--tier",
        "hypr-headless",
        "run",
        "--",
        "true",
        lease_root=lease_root,
    )
    assert completed.returncode == 3


@pytest.mark.skipif(not KNOWN_XVFB.is_file(), reason="rootless Xvfb artifact absent")
def test_rootless_xvfb_smoke(lease_root: Path, tmp_path: Path) -> None:
    env = {
        "PATH": "/usr/bin:/bin",
        "GUI_E2E_XVFB": "",
        "GUI_E2E_KNOWN_XVFB": str(KNOWN_XVFB),
        "GUI_E2E_DISPLAY_NUM": "187",
    }
    completed = run(
        "--tier",
        "xvfb",
        "--lease-id",
        "smoke",
        "--workspace",
        "9",
        "start",
        lease_root=lease_root,
        dry_run=False,
        env=env,
    )
    assert completed.returncode == 0, completed.stderr
    lease = json.loads((lease_root / "smoke" / "lease.json").read_text())
    assert lease["tier"] == "xvfb"
    assert lease["xvfb_bin"] == str(KNOWN_XVFB)
    assert Path("/tmp/.X11-unix/X187").is_socket()
    pid = int(lease["xvfb_pid"])
    os.kill(pid, 0)
    stop = run(
        "--lease-id",
        "smoke",
        "stop",
        lease_root=lease_root,
        dry_run=False,
        env=env,
    )
    assert stop.returncode == 0, stop.stderr
    time.sleep(0.1)
    with pytest.raises(OSError):
        os.kill(pid, 0)
    assert (lease_root / "smoke" / "proof-before.json").is_file()
    assert (lease_root / "smoke" / "proof-after.json").is_file()
    assert (lease_root / "smoke" / "lease-stopped.json").is_file()


@pytest.mark.skipif(not KNOWN_XVFB.is_file(), reason="rootless Xvfb artifact absent")
def test_interrupted_run_cleans_xvfb(lease_root: Path) -> None:
    env = os.environ | {
        "GUI_E2E_LEASE_DIR": str(lease_root),
        "PATH": "/usr/bin:/bin",
        "GUI_E2E_KNOWN_XVFB": str(KNOWN_XVFB),
        "GUI_E2E_DISPLAY_NUM": "188",
    }
    proc = subprocess.Popen(
        [
            "bash",
            str(CTRL),
            "--tier",
            "xvfb",
            "--lease-id",
            "int",
            "--workspace",
            "9",
            "run",
            "--",
            "bash",
            "-c",
            "sleep 30",
        ],
        cwd=REPO,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + 5
    lease_path = lease_root / "int" / "lease.json"
    while time.time() < deadline and not lease_path.is_file():
        time.sleep(0.05)
    assert lease_path.is_file(), proc.stderr.read() if proc.stderr else "no lease"
    lease = json.loads(lease_path.read_text())
    pid = int(lease["xvfb_pid"])
    proc.send_signal(signal.SIGTERM)
    proc.wait(timeout=8)
    time.sleep(0.2)
    with pytest.raises(OSError):
        os.kill(pid, 0)
    assert (lease_root / "int" / "proof-before.json").is_file()
    assert (lease_root / "int" / "lease-stopped.json").is_file()
