"""Isolated GUI E2E display controller — no live compositor required."""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
CTRL = REPO / "scripts" / "gui-e2e-display.sh"


def run(
    *args: str,
    env: dict[str, str] | None = None,
    lease_root: Path,
    check: bool = False,
) -> subprocess.CompletedProcess[str]:
    merged = os.environ | {
        "GUI_E2E_LEASE_DIR": str(lease_root),
        "GUI_E2E_DRY_RUN": "1",
    }
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


def test_stop_removes_lease(lease_root: Path) -> None:
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
    assert not (lease_root / "gone").exists()


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
