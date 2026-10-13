import os
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_resolved_path_moves_match_current_evidence():
    """The CachyOS migration tree is a compatibility symlink; cold docs are gone."""
    migration = ROOT / "migration"
    assert migration.is_symlink()
    assert os.readlink(migration) == "transitions/legacy/cachyos-migration"
    canonical = ROOT / "transitions/legacy/cachyos-migration"
    assert canonical.is_dir()
    assert not canonical.is_symlink()

    # The cold docs and their compatibility symlinks were removed.
    for gone in ("claudedocs", "POLYBAR_PYWAL_USAGE.md", "docs/archive", "docs/legacy"):
        path = ROOT / gone
        assert not path.exists() and not path.is_symlink(), gone

    assert not (ROOT / "proposal_codexbar_aggregate.md").exists()
    assert not (ROOT / "docs/proposals/codexbar-aggregate.md").exists()


def test_path_map_covers_every_compatibility_alias():
    data = tomllib.loads((ROOT / "transitions" / "path-map.toml").read_text())
    moves = {(row["from"], row["to"]) for row in data["move"]}
    assert ("migration", "transitions/legacy/cachyos-migration") in moves
    removed = {"claudedocs", "POLYBAR_PYWAL_USAGE.md"}
    assert not removed & {row["from"] for row in data["move"]}
    assert ("proposal_codexbar_aggregate.md", "docs/proposals/codexbar-aggregate.md") in moves
