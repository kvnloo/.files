from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_compatibility_paths_are_symlinks_to_new_canonical_locations():
    expected = {
        "migration": "transitions/legacy/cachyos-migration",
        "claudedocs": "docs/archive/claude",
        "POLYBAR_PYWAL_USAGE.md": "docs/legacy/POLYBAR_PYWAL_USAGE.md",
        "proposal_codexbar_aggregate.md": "docs/proposals/codexbar-aggregate.md",
    }
    for old, new in expected.items():
        path = ROOT / old
        assert path.is_symlink(), old
        assert path.readlink().as_posix() == new
        assert (ROOT / new).exists(), new


def test_path_map_covers_every_compatibility_alias():
    data = tomllib.loads((ROOT / "transitions" / "path-map.toml").read_text())
    moves = {(row["from"], row["to"]) for row in data["move"]}
    assert ("migration", "transitions/legacy/cachyos-migration") in moves
    assert ("claudedocs", "docs/archive/claude") in moves
    assert ("POLYBAR_PYWAL_USAGE.md", "docs/legacy/POLYBAR_PYWAL_USAGE.md") in moves
    assert ("proposal_codexbar_aggregate.md", "docs/proposals/codexbar-aggregate.md") in moves
