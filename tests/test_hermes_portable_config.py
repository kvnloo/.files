import json
import os
import re
import runpy
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
    assert (out / "README.md").is_file()
    assert (out / "provenance.json").is_file()
    assert (out / "config" / "allowed-keys.json").is_file()
    assert (out / "services" / "templates.json").is_file()
    assert (out / "skills.snapshot.json").is_file()
    assert (out / "themes" / "registry.json").is_file()

    manifest = json.loads((out / "manifest.json").read_text())
    assert manifest["profile"] == "portable-hermes"
    assert manifest["version"] == "1.0.0"
    assert set(manifest["artifacts"]) == {
        "README.md",
        "config/allowed-keys.json",
        "provenance.json",
        "services/templates.json",
        "skills.snapshot.json",
        "themes/registry.json",
    }


def test_no_literal_forbidden_paths_in_artifacts(tmp_path: Path) -> None:
    completed, out = run_export(tmp_path)
    assert completed.returncode == 0, completed.stderr
    forbidden = ["/home/kvn", "/workspace/hermes-home", "/mnt/zer0models"]
    for path in out.rglob("*"):
        if path.is_file():
            text = path.read_text()
            for token in forbidden:
                assert token not in text, f"leaked forbidden path: {token} in {path}"


@pytest.mark.parametrize(
    "poison",
    [
        "/home/kvn/.hermes/config.yaml",
        "api_key=«redacted:sk-…»",
        "auth.json",
        "/portable/session.db",
        "/portable/cache.json",
    ],
)
def test_writer_rejects_forbidden_content_before_persist(tmp_path: Path, poison: str) -> None:
    module = runpy.run_path(str(EXPORT))
    allowlist = {
        "config": {"keys": ["theme"]},
        "provenance": {"tools": [poison], "skills": [], "plugins": []},
        "themes": [],
        "services": {"placeholders": {}},
    }
    out = tmp_path / "out"
    with pytest.raises(ValueError, match="forbidden content") as exc:
        module["write_artifacts"](out, allowlist)
    assert poison not in str(exc.value)
    assert not any(path.is_file() for path in out.rglob("*"))


def test_exporter_is_executable() -> None:
    assert os.access(EXPORT, os.X_OK)


def test_public_document_validator_rejects_host_identity_without_rejecting_exclusion_names() -> None:
    module = runpy.run_path(str(EXPORT))
    module["_assert_public_document"]("Never include .env, auth.json, state.db, sessions, logs, or cache.", "README.md")
    with pytest.raises(ValueError, match="forbidden content") as exc:
        module["_assert_public_document"]("host=/home/kvn/.hermes", "README.md")
    assert "/home/kvn" not in str(exc.value)


def test_generated_service_templates_use_placeholders(tmp_path: Path) -> None:
    completed, out = run_export(tmp_path)
    assert completed.returncode == 0, completed.stderr
    services = json.loads((out / "services" / "templates.json").read_text())
    placeholders = services["placeholders"].values()
    assert all("<HERMES_" in value for value in placeholders)
