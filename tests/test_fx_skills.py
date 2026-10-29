import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("apply_fx_skills", str(ROOT / "scripts/apply-fx-skills"))
spec = importlib.util.spec_from_loader(loader.name, loader)
repair = importlib.util.module_from_spec(spec)
loader.exec_module(repair)
POLICY = json.loads((ROOT / "config/fx-skills.json").read_text())


def fixture(tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    external = tmp_path / "offload/codex/skills"
    external.mkdir(parents=True)
    (home / ".codex").symlink_to(external.parent)
    for name in POLICY["media_skills"]:
        source = home / ".agents/skills" / name
        source.mkdir(parents=True)
        (source / "SKILL.md").write_text("---\nname: " + name + "\n---\n")
        for relative, prefix in POLICY["stale_alias_roots"].items():
            link = home / relative / name
            link.parent.mkdir(parents=True, exist_ok=True)
            link.symlink_to(prefix + name)
    settings = home / ".fx/settings.json"
    settings.parent.mkdir()
    original = {"models": {"codex": "preserve-model"}, "provider": "codex", "credential_source": "fx_login", "fast_mode": False, "effort": "medium", "skill_symlink_authorities": ["/opt/existing-skills"]}
    settings.write_text(json.dumps(original))
    return home, external, settings, original


def test_repairs_all_known_aliases_preserves_preferences_and_is_idempotent(tmp_path):
    home, external, settings, original = fixture(tmp_path)
    before = settings.read_bytes()
    repair.apply(home, POLICY)
    result = json.loads(settings.read_text())
    assert result.pop("skill_symlink_authorities") == ["/opt/existing-skills", str(external)]
    assert result == {k: v for k, v in original.items() if k != "skill_symlink_authorities"}
    assert settings.with_name("settings.json.fx-skills-backup.0").read_bytes() == before
    assert settings.with_name("settings.json.fx-skills-backup.0").stat().st_mode & 0o777 == 0o600
    for relative in POLICY["stale_alias_roots"]:
        for name in POLICY["media_skills"]:
            assert (home / relative / name).resolve() == home / ".agents/skills" / name
    records = list((home / ".local/state/dotfiles/fx-skills").glob("*.json"))
    assert len(records) == 24
    assert all(json.loads(p.read_text())["target"].endswith(Path(json.loads(p.read_text())["path"]).name) for p in records)
    snapshot = settings.read_bytes()
    repair.apply(home, POLICY)
    assert settings.read_bytes() == snapshot
    assert len(list((home / ".local/state/dotfiles/fx-skills").glob("*.json"))) == 24
    assert not settings.with_name("settings.json.fx-skills-backup.1").exists()
    assert not any("backup" in p.name for p in external.iterdir())


def test_dry_run_has_no_writes(tmp_path):
    home, external, settings, original = fixture(tmp_path)
    before = settings.read_bytes()
    repair.apply(home, POLICY, dry_run=True)
    assert settings.read_bytes() == before
    assert not (home / ".local").exists()
    assert not (external / "general-video").exists()


def test_changed_live_and_directory_entries_are_preserved(tmp_path):
    home, external, settings, original = fixture(tmp_path)
    changed = external / "general-video"
    changed.unlink()
    changed.symlink_to("/missing/user-selected-skill")
    live = external / "hyperframes"
    live.unlink()
    live.symlink_to(home / ".agents/skills/hyperframes")
    directory = external / "hyperframes-core"
    directory.unlink()
    directory.mkdir()
    repair.apply(home, POLICY)
    assert os.readlink(changed) == "/missing/user-selected-skill"
    assert os.readlink(live) == str(home / ".agents/skills/hyperframes")
    assert directory.is_dir() and not directory.is_symlink()


def test_missing_source_fails_before_any_changes(tmp_path):
    home, external, settings, original = fixture(tmp_path)
    before = settings.read_bytes()
    (home / ".agents/skills/media-use/SKILL.md").unlink()
    with pytest.raises(ValueError, match="Missing intended skill source"):
        repair.apply(home, POLICY)
    assert settings.read_bytes() == before
    assert not (home / ".local").exists()


@pytest.mark.parametrize("invalid", ["/mnt", ["relative"], ["/opt/../etc"], [42]])
def test_invalid_existing_authority_fails_closed(tmp_path, invalid):
    home, external, settings, original = fixture(tmp_path)
    original["skill_symlink_authorities"] = invalid
    settings.write_text(json.dumps(original))
    with pytest.raises(ValueError, match="Invalid existing"):
        repair.apply(home, POLICY)
    assert not (home / ".local").exists()


def test_symlinked_settings_are_not_replaced(tmp_path):
    home, external, settings, original = fixture(tmp_path)
    elsewhere = tmp_path / "private-settings.json"
    settings.rename(elsewhere)
    settings.symlink_to(elsewhere)
    with pytest.raises(ValueError, match="symlinked fx settings"):
        repair.apply(home, POLICY)
    assert settings.is_symlink()


def test_exact_external_skill_authorities_are_canonical_and_deduplicated(tmp_path):
    home, external, settings, original = fixture(tmp_path)
    source = tmp_path / "known-source/skill"
    source.mkdir(parents=True)
    (source / "SKILL.md").write_text("skill")
    alias = tmp_path / "source-alias"
    alias.symlink_to(source)
    policy = dict(POLICY)
    policy["external_skills"] = {
        ".agents/skills/known": str(alias),
        ".config/opencode/skills/known": str(alias),
    }
    for relative in policy["external_skills"]:
        (home / relative).symlink_to(alias)
    repair.apply(home, policy)
    assert json.loads(settings.read_text())["skill_symlink_authorities"] == [
        "/opt/existing-skills", str(external), str(source)
    ]
    assert os.readlink(home / ".agents/skills/known") == str(alias)


def test_changed_external_identity_is_not_granted_authority(tmp_path):
    home, external, settings, original = fixture(tmp_path)
    source = tmp_path / "user-source"
    source.mkdir()
    (source / "SKILL.md").write_text("skill")
    link = home / ".agents/skills/known"
    link.symlink_to(source)
    policy = dict(POLICY)
    policy["external_skills"] = {".agents/skills/known": str(tmp_path / "old-source")}
    repair.apply(home, policy)
    assert str(source) not in json.loads(settings.read_text())["skill_symlink_authorities"]
    assert os.readlink(link) == str(source)
