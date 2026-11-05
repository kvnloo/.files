from importlib.machinery import SourceFileLoader
from pathlib import Path

ocs = SourceFileLoader("owner_canon_sync", str(Path(__file__).parents[1] / "scripts/owner-canon-sync")).load_module()

CANON = "# canon\n\n" + "".join(f"{i}. Rule {i} text. — \"quote {i}\" (date, id)\n" for i in range(1, 16)) + \
    "\n## Candidates\n16. Not adopted. — \"x\"\n"


def block(tmp_path):
    src = tmp_path / "OWNER-CANON.md"
    src.write_text(CANON)
    return ocs.render(src)


def test_render_keeps_rules_drops_quotes_and_candidates(tmp_path):
    b = block(tmp_path)
    assert b.startswith(ocs.START) and b.rstrip().endswith(ocs.END)
    assert "14. Rule 14 text." in b and "quote" not in b and "16." not in b


def test_apply_creates_harness_files_replaces_in_place_and_skips_missing_profiles(tmp_path):
    b, home = block(tmp_path), tmp_path / "home"
    soul = home / ".hermes/profiles/clean/SOUL.md"
    soul.parent.mkdir(parents=True)
    soul.write_text(f"head\n{ocs.START} old -->\nstale\n{ocs.END}\ntail\n")
    assert ocs.apply(b, check=True, home=home) > 0          # drift reported, nothing written
    assert not (home / ".claude/CLAUDE.md").exists()
    ocs.apply(b, check=False, home=home)
    text = soul.read_text()
    assert text.startswith("head\n") and text.endswith("\ntail\n") and "stale" not in text
    assert text.count(ocs.START) == 1 and "Rule 14" in text
    assert (home / ".pi/agent/AGENTS.md").read_text() == b
    assert not (home / ".hermes/profiles/analyst").exists()  # absent profile untouched
    assert ocs.apply(b, check=True, home=home) == 0         # idempotent


def test_render_refuses_a_source_without_15_locked_rules(tmp_path):
    src = tmp_path / "OWNER-CANON.md"
    src.write_text("1. Only one rule.\n")
    try:
        ocs.render(src)
    except SystemExit as e:
        assert "found 1" in str(e)
    else:
        raise AssertionError("render accepted a short canon")
