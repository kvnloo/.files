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
