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


def test_verified_readonly_backup_removed_without_destination_mode_changes(tmp_path, monkeypatch):
    import shutil
    import stat

    backup = tmp_path / "backup"
    (backup / "nested").mkdir(parents=True)
    (backup / "nested" / "data").write_text("preserve me")
    (backup / "nested").chmod(0o555)
    backup.chmod(0o555)
    destination = tmp_path / "destination"
    shutil.copytree(backup, destination)
    before = {str(p.relative_to(destination)): stat.S_IMODE(p.stat().st_mode)
              for p in [destination, *destination.rglob("*")]}
    monkeypatch.setattr(tier, "verify_checksum", lambda *_: None)
    tier.remove_verified_backup(backup, destination)
    assert not backup.exists()
    assert before == {str(p.relative_to(destination)): stat.S_IMODE(p.stat().st_mode)
                      for p in [destination, *destination.rglob("*")]}


def test_unverified_backup_is_never_removed(tmp_path, monkeypatch):
    backup = tmp_path / "backup"
    backup.mkdir()
    backup.chmod(0o555)
    destination = tmp_path / "destination"
    destination.mkdir()
    def reject(*_):
        raise RuntimeError("checksum mismatch")
    monkeypatch.setattr(tier, "verify_checksum", reject)
    with pytest.raises(RuntimeError, match="checksum mismatch"):
        tier.remove_verified_backup(backup, destination)
    assert backup.exists()
    assert backup.stat().st_mode & 0o777 == 0o555
