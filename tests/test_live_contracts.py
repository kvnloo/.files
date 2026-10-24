import importlib.util
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("iac_contracts", ROOT / "scripts" / "iac" / "contracts.py")
contracts = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(contracts)


def test_missing_candidate_is_not_safe(tmp_path):
    live = tmp_path / "live"
    cand = tmp_path / "cand"
    home = tmp_path / "home"
    target = live / "config" / "hyprland" / "hyprland.legacy.conf"
    target.parent.mkdir(parents=True)
    target.write_text("live\n")
    cand.mkdir()
    home.mkdir()
    link = home / "hyprland.conf"
    link.symlink_to(target)

    row = contracts.compare_link(link, live, cand)

    assert row["relative"] == "config/hyprland/hyprland.legacy.conf"
    assert row["result"] == "MISSING"
    assert os.readlink(link) == str(target)


def test_type_change_and_safe_file(tmp_path):
    live = tmp_path / "live"
    cand = tmp_path / "cand"
    home = tmp_path / "home"
    (live / "a").mkdir(parents=True)
    (cand / "a").mkdir(parents=True)
    (live / "a" / "f").write_text("same")
    (cand / "a" / "f").write_text("same")
    (live / "a" / "d").mkdir()
    (cand / "a" / "d").symlink_to(cand / "a" / "f")
    home.mkdir()
    ok = home / "ok"
    bad = home / "bad"
    ok.symlink_to(live / "a" / "f")
    bad.symlink_to(live / "a" / "d")

    assert contracts.compare_link(ok, live, cand)["result"] == "SAFE"
    assert contracts.compare_link(bad, live, cand)["result"] == "TYPE_CHANGED"


def test_chained_link_uses_final_repo_path(tmp_path):
    live = tmp_path / "live"
    cand = tmp_path / "cand"
    home = tmp_path / "home"
    (live / "config").mkdir(parents=True)
    (cand / "config").mkdir(parents=True)
    (live / "config" / "real").write_text("v")
    (cand / "config" / "real").write_text("v")
    home.mkdir()
    (home / "mid").symlink_to(live / "config" / "real")
    (home / "outer").symlink_to(home / "mid")

    row = contracts.compare_link(home / "outer", live, cand)
    assert row["relative"] == "config/real"
    assert row["result"] == "SAFE"


def test_candidate_preserves_hyprland_legacy_pathname():
    path = ROOT / "config" / "hyprland" / "hyprland.legacy.conf"
    assert path.is_file()
    assert not path.is_symlink()
