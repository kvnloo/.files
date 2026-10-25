from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "zer0_storage_tier.py"
SPEC = importlib.util.spec_from_file_location("zer0_storage_tier", SCRIPT)
assert SPEC and SPEC.loader
tier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(tier)


def test_migrate_rejects_source_outside_source_root(tmp_path):
    source = tmp_path / "elsewhere" / "venv"
    source.mkdir(parents=True)
    with pytest.raises(RuntimeError, match="source must be under"):
        tier.migrate(source, tmp_path / "dest", dry_run=True, source_root=tmp_path / "allowed")


def test_migrate_dry_run_accepts_explicit_source_root(tmp_path, monkeypatch):
    source_root = tmp_path / "tmp"
    source = source_root / "scratch" / ".venv"
    source.mkdir(parents=True)
    (source / "pyvenv.cfg").write_text("version = 3.11\n")
    events = []
    monkeypatch.setattr(tier, "emit", lambda event, **fields: events.append(event))
    monkeypatch.setattr(tier, "active_references", lambda _source: [])
    tier.migrate(source, tmp_path / "dest", dry_run=True, source_root=source_root)
    assert events == ["dry_run_ready"]
