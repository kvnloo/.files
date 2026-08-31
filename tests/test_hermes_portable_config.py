import json
import os
import re
import subprocess
import textwrap
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
EXPORT = REPO / "scripts" / "export-hermes-portable"


def run_export(tmp_path: Path):
    out = tmp_path / "artifacts"
    completed = subprocess.run(
        ["python3", str(EXPORT), str(out)],
        cwd=REPO,
        check=False,
        capture_output=True,
        text=True,
    )
    return completed, out


def test_exports_generated_artifacts(tmp_path: Path) -> None:
    completed, out = run_export(tmp_path)
    assert completed.returncode == 0, completed.stderr
    assert (out / "manifest.json").is_file()
    assert (out / "provenance.json").is_file()
    assert (out / "config" / "allowed-keys.json").is_file()
    assert (out / "services" / "templates.json").is_file()
    assert (out / "themes" / "registry.json").is_file()

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["profile"] == "portable-hermes"
    assert manifest["version"] == "1.0.0"


def test_no_literal_forbidden_paths_in_artifacts(tmp_path: Path) -> None:
    completed, out = run_export(tmp_path)
    assert completed.returncode == 0, completed.stderr
    forbidden = ["/home/kvn", "/workspace/hermes-home", "/mnt/zer0models"]
    for path in out.rglob("*"):
        if path.is_file():
            text = path.read_text()
            for token in forbidden:
                assert token not in text, f"leaked forbidden path: {token} in {path}"


def test_red_leak_deny_fails_when_home_path_present(tmp_path: Path) -> None:
    target = tmp_path / "leak"
    target.mkdir()
    poisoned = target / "leaked.json"
    poisoned.write_text(json.dumps({"value": "/home/kvn/.hermes/config.json"}) + "\n")
    completed, out = run_export(tmp_path)
    assert completed.returncode == 0, completed.stderr
    leak_scan = [
        p for p in out.rglob("*") if p.is_file() and "/home/kvn" in p.read_text()
    ]
    assert not leak_scan, f"red-stage leak denial failed: {leak_scan}"


def test_red_leak_deny_fails_when_host_token_shape_present(tmp_path: Path) -> None:
    target = tmp_path / "token"
    target.mkdir()
    poisoned = target / "tokens.json"
    poisoned.write_text(json.dumps({"token": "ghp_ABCDEF0123456789"}) + "\n")
    completed, out = run_export(tmp_path)
    assert completed.returncode == 0, completed.stderr
    leak_scan = [
        p
        for p in out.rglob("*")
        if p.is_file() and re.search(r"ghp_|github_pat_", p.read_text())
    ]
    assert not leak_scan, f"red-stage token denial failed: {leak_scan}"


def test_generated_service_templates_use_placeholders(tmp_path: Path) -> None:
    completed, out = run_export(tmp_path)
    assert completed.returncode == 0, completed.stderr
    services = json.loads((out / "services" / "templates.json").read_text())
    placeholders = services["placeholders"].values()
    assert all("<HERMES_" in value for value in placeholders)
