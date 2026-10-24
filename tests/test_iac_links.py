import importlib.util
import json
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = ROOT / "scripts" / "iac" / "links.py"

spec = importlib.util.spec_from_file_location("iac_links", MODULE_PATH)
links = importlib.util.module_from_spec(spec)
assert spec.loader is not None
spec.loader.exec_module(links)


def test_scan_is_read_only_and_maps_identity(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    external = tmp_path / "home"
    (old / "config").mkdir(parents=True)
    (new / "config").mkdir(parents=True)
    external.mkdir()
    (old / "config" / "x").write_text("old")
    (new / "config" / "x").write_text("new")
    link = external / "x"
    link.symlink_to(old / "config" / "x")

    plan = links.build_plan(old, new, [external])

    assert os.readlink(link) == str(old / "config" / "x")
    assert len(plan["links"]) == 1
    row = plan["links"][0]
    assert row["old_relative"] == "config/x"
    assert row["new_relative"] == "config/x"
    assert row["stage_target"] == str(new / "config" / "x")
    assert row["final_target"] == str(old / "config" / "x")


def test_prefix_move_mapping(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    external = tmp_path / "home"
    (old / "migration").mkdir(parents=True)
    (new / "transitions" / "legacy").mkdir(parents=True)
    external.mkdir()
    (old / "migration" / "run.sh").write_text("old")
    (new / "transitions" / "legacy" / "run.sh").write_text("new")
    (external / "run").symlink_to(old / "migration" / "run.sh")

    plan = links.build_plan(
        old, new, [external],
        moves=[{"from": "migration", "to": "transitions/legacy"}],
    )
    row = plan["links"][0]
    assert row["new_relative"] == "transitions/legacy/run.sh"
    assert row["stage_target"] == str(new / "transitions" / "legacy" / "run.sh")
    assert row["final_target"] == str(old / "transitions" / "legacy" / "run.sh")


def test_bundle_contains_frozen_plan_and_three_scripts(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    external = tmp_path / "home"
    old.mkdir()
    new.mkdir()
    external.mkdir()
    plan = links.build_plan(old, new, [external])
    out = tmp_path / "bundle"

    links.write_bundle(plan, out)

    assert json.loads((out / "plan.json").read_text())["schema_version"] == 1
    for name in ("stage.py", "cutover.py", "rollback.py"):
        assert (out / name).is_file()


def test_scan_excludes_links_inside_the_repo(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    external = tmp_path / "home"
    old.mkdir()
    new.mkdir()
    external.mkdir()
    (old / "target").write_text("x")
    (old / "internal").symlink_to(old / "target")
    (external / "external").symlink_to(old / "target")

    plan = links.build_plan(old, new, [old, external])

    assert [Path(row["link"]).name for row in plan["links"]] == ["external"]


def test_relative_directory_space_and_dangling_links(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    external = tmp_path / "home"
    (old / "dir with space").mkdir(parents=True)
    (new / "dir with space").mkdir(parents=True)
    (old / "dir with space" / "file").write_text("x")
    (new / "dir with space" / "file").write_text("x")
    external.mkdir()
    (external / "rel").symlink_to(Path("..") / "old" / "dir with space" / "file")
    (external / "dirlink").symlink_to(old / "dir with space")
    (external / "gone").symlink_to(old / "missing-target")
    nested = old / "chain-dir"
    nested.mkdir()
    (nested / "leaf").write_text("leaf")
    (external / "mid").symlink_to(old / "chain-dir" / "leaf")
    (external / "chain").symlink_to(external / "mid")

    plan = links.build_plan(old, new, [external])
    by_name = {Path(row["link"]).name: row for row in plan["links"]}

    assert by_name["rel"]["old_relative"] == "dir with space/file"
    assert by_name["dirlink"]["old_relative"] == "dir with space"
    assert by_name["gone"]["old_relative"] == "missing-target"
    assert by_name["gone"]["dangling"] == "true"
    assert by_name["chain"]["old_relative"] == "chain-dir/leaf"
    assert os.readlink(external / "chain") == str(external / "mid")


def test_hyprland_legacy_contract_shape(tmp_path):
    old = tmp_path / "workspace" / ".files"
    new = tmp_path / "workspace" / ".files-rollout"
    home = tmp_path / "home" / ".config" / "hypr"
    legacy = old / "config" / "hyprland" / "hyprland.legacy.conf"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("live\n")
    (new / "config" / "hyprland").mkdir(parents=True)
    (new / "config" / "hyprland" / "hyprland.legacy.conf").write_text("live\n")
    home.mkdir(parents=True)
    link = home / "hyprland.conf"
    link.symlink_to(legacy)

    plan = links.build_plan(old, new, [tmp_path / "home"])

    assert len(plan["links"]) == 1
    row = plan["links"][0]
    assert row["old_relative"] == "config/hyprland/hyprland.legacy.conf"
    assert os.readlink(link) == str(legacy)


def test_move_classifier_matches_live_evidence():
    blocked = links.classify_move("migration", {
        "present": True, "hot_writes": True, "content_understood": True, "rollback_possible": True,
    })
    eligible = links.classify_move("idle", {
        "present": True, "content_understood": True, "rollback_possible": True,
    })
    polybar = links.classify_move("POLYBAR_PYWAL_USAGE.md", {
        "present": True, "warm_writes": True, "content_understood": True, "rollback_possible": True,
    })
    claude = links.classify_move("claudedocs", {
        "present": True, "inspection_gap": True, "content_understood": True, "rollback_possible": True,
    })
    missing = links.classify_move("proposal_codexbar_aggregate.md", {"present": False})
    assert blocked["classification"] == "BLOCKED"
    assert polybar["classification"] == "DEFER"
    assert claude["classification"] == "DEFER"
    assert missing["classification"] == "NOT_PRESENT"
    assert eligible["classification"] == "ELIGIBLE"
