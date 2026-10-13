from pathlib import Path
import tomllib


ROOT = Path(__file__).resolve().parents[1]


def test_resolved_path_moves_match_current_evidence():
    """The cold docs, the CachyOS migration tree and their symlinks are gone."""
    for gone in (
        "claudedocs",
        "POLYBAR_PYWAL_USAGE.md",
        "docs/archive",
        "docs/legacy",
        "migration",
        "transitions/legacy/cachyos-migration",
    ):
        path = ROOT / gone
        assert not path.exists() and not path.is_symlink(), gone

    assert not (ROOT / "proposal_codexbar_aggregate.md").exists()
    assert not (ROOT / "docs/proposals/codexbar-aggregate.md").exists()


def test_path_map_covers_every_compatibility_alias():
    data = tomllib.loads((ROOT / "transitions" / "path-map.toml").read_text())
    moves = {(row["from"], row["to"]) for row in data["move"]}
    removed = {"migration", "claudedocs", "POLYBAR_PYWAL_USAGE.md"}
    assert not removed & {row["from"] for row in data["move"]}
    assert ("proposal_codexbar_aggregate.md", "docs/proposals/codexbar-aggregate.md") in moves
