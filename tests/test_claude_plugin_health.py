"""Coverage for scripts/claude-plugin-health.py.

The break this guards against is invisible to every other check on the host: a
config dir enables a plugin whose marketplace checkout is gone, so Claude Code
registers no hooks and the tick that reads the captured rows just reports zeros.
"""
import json
import os
import stat
import subprocess
import sys
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path

import pytest

SPEC = spec_from_loader(
    "claude_plugin_health",
    SourceFileLoader(
        "claude_plugin_health",
        str(Path(__file__).resolve().parents[1] / "scripts" / "claude-plugin-health.py"),
    ),
)
assert SPEC is not None and SPEC.loader is not None
cph = module_from_spec(SPEC)
SPEC.loader.exec_module(cph)

Z0INT = "z0intelligence@z0intelligence"
CATALOG = Path(".claude-plugin") / "marketplace.json"


def write_settings(config: Path, enabled=(Z0INT,), marketplaces=("z0intelligence",)):
    settings = {
        "enabledPlugins": {name: True for name in enabled},
        "extraKnownMarketplaces": {
            name: {"source": "github", "repo": f"kvnloo/{name}"}
            for name in marketplaces
        },
    }
    (config / "settings.json").write_text(json.dumps(settings, indent=2))


def write_registry(config: Path, plugins=(Z0INT,)):
    payload = {"version": 2, "plugins": {p: [{"scope": "user"}] for p in plugins}}
    plugins_dir = config / "plugins"
    plugins_dir.mkdir(parents=True, exist_ok=True)
    (plugins_dir / "installed_plugins.json").write_text(json.dumps(payload))


def register_marketplace(config: Path, name="z0intelligence", repo=None, install=True):
    """Record the marketplace where Claude Code writes it, and seed its checkout."""
    root = config / "plugins" / "marketplaces" / name
    registry = {"name": {"source": {"source": "github", "repo": repo or f"kvnloo/{name}"},
                         "installLocation": str(root)}}
    known = config / "plugins" / "known_marketplaces.json"
    known.parent.mkdir(parents=True, exist_ok=True)
    known.write_text(json.dumps(registry))
    if install:
        (root / CATALOG).parent.mkdir(parents=True, exist_ok=True)
        (root / CATALOG).write_text(json.dumps({"name": name, "plugins": []}))
        (root / "README.md").write_text("seed\n")
    return root


def fake_claude(tmp_path: Path, rows):
    """A claude CLI stub whose `plugin list --json` is canned."""
    script = tmp_path / "fake-claude"
    script.write_text(
        "#!/usr/bin/env python3\n"
        "import json, os, sys\n"
        f"rows = {rows!r}\n"
        "if sys.argv[1:] != ['plugin', 'list', '--json']:\n"
        "    sys.exit(64)\n"
        "assert os.environ.get('CLAUDE_CONFIG_DIR'), 'CLAUDE_CONFIG_DIR not passed'\n"
        "print(json.dumps(rows))\n"
    )
    script.chmod(script.stat().st_mode | stat.S_IEXEC)
    return str(script)


def ok_rows(config: Path):
    return [{"id": Z0INT, "enabled": True, "errors": []}]


def broken_rows(config: Path):
    return [{"id": Z0INT, "enabled": True,
             "errors": ["Marketplace z0intelligence failed to load: cache-miss"]}]


def make_config(tmp_path: Path, name, *, settings=True, registry=True,
                marketplace=True, rows=None, claude=True):
    config = tmp_path / name
    config.mkdir(parents=True, exist_ok=True)
    if settings:
        write_settings(config)
    if registry:
        write_registry(config)
    root = register_marketplace(config, install=marketplace)
    if claude:
        rows = rows if rows is not None else (
            ok_rows(config) if marketplace else broken_rows(config))
        fake_claude(tmp_path, rows)
    return config, root


def base_args(configs, command):
    args = [command]
    for config in configs:
        args += ["--config-dir", str(config)]
    return args


def test_check_passes_when_every_enabled_plugin_is_loaded(tmp_path, capsys):
    config, _ = make_config(tmp_path, "healthy")
    code = cph.main(base_args([config], "check") + ["--claude", str(tmp_path / "fake-claude")])
    assert code == cph.CLEAN
    assert "ok:" in capsys.readouterr().out


def test_check_fails_on_marketplace_cache_miss(tmp_path, capsys):
    config, _ = make_config(tmp_path, "cache-miss", marketplace=False)
    code = cph.main(base_args([config], "check") + ["--claude", str(tmp_path / "fake-claude")])
    assert code == cph.BROKEN
    out = capsys.readouterr().out
    assert "cache-miss" in out
    assert str(config) in out


def test_check_fails_when_the_marketplace_tree_is_gone_even_if_silent(tmp_path, capsys):
    """Claude says 'enabled', but the catalog on disk is the invariant."""
    config, _ = make_config(tmp_path, "silent", marketplace=False, rows=ok_rows(tmp_path))
    code = cph.main(base_args([config], "check") + ["--claude", str(tmp_path / "fake-claude")])
    assert code == cph.BROKEN
    assert "no checkout" in capsys.readouterr().out


def test_check_fails_when_an_enabled_plugin_is_not_listed(tmp_path, capsys):
    config, _ = make_config(tmp_path, "absent", rows=[])
    code = cph.main(base_args([config], "check") + ["--claude", str(tmp_path / "fake-claude")])
    assert code == cph.BROKEN
    assert "not listed" in capsys.readouterr().out


def test_check_ignores_plugins_never_installed_here(tmp_path, capsys):
    """An enabledPlugins entry with no install record is orphaned, not broken."""
    config = tmp_path / "orphan"
    config.mkdir()
    write_settings(config)
    register_marketplace(config, install=True)
    fake_claude(tmp_path, [])
    code = cph.main(base_args([config], "check") + ["--claude", str(tmp_path / "fake-claude")])
    assert code == cph.CLEAN


def test_check_reports_json(tmp_path, capsys):
    config, _ = make_config(tmp_path, "jsondir")
    code = cph.main(base_args([config], "check") + ["--claude", str(tmp_path / "fake-claude"),
                                                    "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == cph.CLEAN
    assert payload["ok"] is True
    assert payload["faults"][0]["config_dir"] == str(config)


def test_check_reports_unusable_when_claude_cannot_run(tmp_path, capsys):
    config, _ = make_config(tmp_path, "nocli", claude=False)
    fake_claude(tmp_path, [{"id": Z0INT, "enabled": True}])
    code = cph.main(base_args([config], "check") + ["--claude", str(tmp_path / "no-such-claude")])
    assert code == cph.UNUSABLE


def test_ensure_seeds_from_another_config_dir(tmp_path, capsys):
    source, _ = make_config(tmp_path, "source-dir")
    target = tmp_path / "target-dir"
    target.mkdir()
    write_settings(target)
    write_registry(target)
    register_marketplace(target, install=False)

    code = cph.main(base_args([source, target], "ensure"))
    healed = target / "plugins" / "marketplaces" / "z0intelligence"
    assert code == cph.CLEAN
    assert (healed / CATALOG).exists()
    assert (healed / "README.md").read_text() == "seed\n"
    assert "re-created" in capsys.readouterr().out


def test_ensure_leaves_a_healthy_checkout_alone(tmp_path, capsys):
    config, root = make_config(tmp_path, "healthy-ensure")
    (root / "sentinel.txt").write_text("do not touch\n")
    code = cph.main(base_args([config], "ensure"))
    assert code == cph.CLEAN
    assert (root / "sentinel.txt").exists()
    assert "healthy" in capsys.readouterr().out


def test_ensure_replaces_an_unreadable_checkout_without_deleting_it(tmp_path, capsys):
    config, root = make_config(tmp_path, "corrupt")
    (root / CATALOG).write_text("{ not json")
    (root / "operator-note.txt").write_text("kept\n")

    code = cph.main(base_args([config], "ensure"))
    assert code == cph.CLEAN
    assert (root / CATALOG).exists()
    assert not list(root.glob("*.broken-*"))
    spares = list((config / "plugins" / "marketplaces").glob("z0intelligence.broken-*"))
    assert spares and (spares[0] / "operator-note.txt").exists(), \
        "the unusable checkout must be set aside, not destroyed"


def test_ensure_clones_the_registered_repo_when_no_local_seed(tmp_path, monkeypatch, capsys):
    config, root = make_config(tmp_path, "clone", claude=False, marketplace=False)
    register_marketplace(config, install=False)
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        (Path(cmd[-1]) / CATALOG).parent.mkdir(parents=True, exist_ok=True)
        (Path(cmd[-1]) / CATALOG).write_text(json.dumps({"name": "z0intelligence"}))
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr(cph.subprocess, "run", fake_run)
    code = cph.main(base_args([config], "ensure"))
    assert code == cph.CLEAN
    assert (root / CATALOG).exists()
    assert calls and calls[0][:3] == ["git", "clone", "--depth"]
    assert calls[0][-2] == "https://github.com/kvnloo/z0intelligence.git"


def test_ensure_fails_loudly_without_any_source(tmp_path, monkeypatch, capsys):
    config, _ = make_config(tmp_path, "nosource", claude=False, registry=False, marketplace=False)
    config_dir = cph.ConfigDir(config)
    config_dir.settings = {"enabledPlugins": {Z0INT: True}}
    # No registry -> nothing installed -> nothing to ensure.
    assert config_dir.needed_marketplaces() == set()

    # Installed, enabled, registered, but nothing on disk and nowhere to seed from.
    write_registry(config)
    (config / "plugins" / "known_marketplaces.json").unlink()

    def fail_run(cmd, **kwargs):
        return subprocess.CompletedProcess(cmd, 1, "", "network unreachable")

    monkeypatch.setattr(cph.subprocess, "run", fail_run)
    code = cph.main(base_args([config], "ensure"))
    assert code == cph.BROKEN
    assert "UNHEALED" in capsys.readouterr().out


def test_missing_config_dir_is_not_a_fault(tmp_path, capsys):
    code = cph.main(base_args([tmp_path / "never-existed"], "ensure"))
    assert code == cph.CLEAN


def test_catalog_ok_rejects_a_directory_and_a_missing_manifest(tmp_path):
    assert cph.catalog_ok(tmp_path / "nothing")[0] is False
    (tmp_path / CATALOG).parent.mkdir(parents=True)
    assert cph.catalog_ok(tmp_path)[0] is False


def test_default_config_dirs_cover_the_dirs_claude_runs_in():
    assert cph.DEFAULT_CONFIG_DIRS == ("~/.claude", "~/.claude-sub2",
                                      "~/.claude-ultra", "~/.claude-work")
