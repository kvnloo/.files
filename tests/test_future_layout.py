from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_deferred_moves_keep_the_live_path_canonical():
    """Desired destinations are recorded, but the material move is not applied."""
    expected = {
        "migration": "transitions/legacy/cachyos-migration",
        "claudedocs": "docs/archive/claude",
        "POLYBAR_PYWAL_USAGE.md": "docs/legacy/POLYBAR_PYWAL_USAGE.md",
    }
    for old, new in expected.items():
        path = ROOT / old
        assert path.exists(), old
        assert not path.is_symlink(), old
        assert not (ROOT / new).exists(), new
    proposal = ROOT / "proposal_codexbar_aggregate.md"
    assert not proposal.exists()
    assert not (ROOT / "docs/proposals/codexbar-aggregate.md").exists()


def test_path_map_covers_every_compatibility_alias():
    data = tomllib.loads((ROOT / "transitions" / "path-map.toml").read_text())
    moves = {(row["from"], row["to"]) for row in data["move"]}
    assert ("migration", "transitions/legacy/cachyos-migration") in moves
    assert ("claudedocs", "docs/archive/claude") in moves
    assert ("POLYBAR_PYWAL_USAGE.md", "docs/legacy/POLYBAR_PYWAL_USAGE.md") in moves
    assert ("proposal_codexbar_aggregate.md", "docs/proposals/codexbar-aggregate.md") in moves
