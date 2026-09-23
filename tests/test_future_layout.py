import os
from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_resolved_path_moves_match_current_evidence():
    """Hot migration stays put. Cold, unreferenced docs are compatibility symlinks."""
    migration = ROOT / "migration"
    assert migration.is_dir()
    assert not migration.is_symlink()
    assert not (ROOT / "transitions/legacy/cachyos-migration").exists()

    applied = {
        "claudedocs": "docs/archive/claude",
        "POLYBAR_PYWAL_USAGE.md": "docs/legacy/POLYBAR_PYWAL_USAGE.md",
    }
    for old, new in applied.items():
        path = ROOT / old
        assert path.is_symlink(), old
        assert os.readlink(path) == new
        canonical = ROOT / new
        assert canonical.exists(), new
        assert not canonical.is_symlink(), new

    assert not (ROOT / "proposal_codexbar_aggregate.md").exists()
    assert not (ROOT / "docs/proposals/codexbar-aggregate.md").exists()


def test_path_map_covers_every_compatibility_alias():
    data = tomllib.loads((ROOT / "transitions" / "path-map.toml").read_text())
    moves = {(row["from"], row["to"]) for row in data["move"]}
    assert ("migration", "transitions/legacy/cachyos-migration") in moves
    assert ("claudedocs", "docs/archive/claude") in moves
    assert ("POLYBAR_PYWAL_USAGE.md", "docs/legacy/POLYBAR_PYWAL_USAGE.md") in moves
    assert ("proposal_codexbar_aggregate.md", "docs/proposals/codexbar-aggregate.md") in moves
