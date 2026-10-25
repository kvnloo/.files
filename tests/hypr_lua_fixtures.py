"""Repository-backed inputs for Lua inventory and monitor generators."""

import json
import runpy
import shutil
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
GLASS_FRAGMENT = ROOT / "tests/fixtures/hypr/liquid-glass.conf"


@pytest.fixture
def hypr_inventory(tmp_path, monkeypatch):
    home = tmp_path / "home"
    monkeypatch.setenv("HOME", str(home))
    checkout = home / "workspace/.files"
    checkout.parent.mkdir(parents=True)
    checkout.symlink_to(ROOT, target_is_directory=True)
    config = home / ".config/hypr"
    config.mkdir(parents=True)
    entry = ROOT / "config/hyprland/hyprland.legacy.conf"
    (config / "hyprland.conf").symlink_to(entry)
    cache = home / ".cache/wal"
    cache.mkdir(parents=True)
    (cache / "colors.json").write_text(json.dumps({
        "special": {"background": "#181f23", "foreground": "#d1deda"},
        "colors": {f"color{i}": f"#{i:02x}8c3e{(i * 17) % 256:02x}" for i in range(16)},
    }))
    subprocess.run([sys.executable, str(ROOT / "scripts/sync-pywal-theme.py")], check=True)
    monitors = config / "monitors.conf"
    monitor_lines = [line for line in entry.read_text().splitlines() if line.startswith("monitor =")]
    monitors.write_text("# Generated from the live layout by persist-monitor-layout.py.\n" + "\n".join(monitor_lines) + "\n")
    generator = runpy.run_path(str(ROOT / "scripts/build-hypr-lua-ownership-map"))
    output = tmp_path / "lua-ownership-map.json"
    generator["main"].__globals__["OUT"] = output
    original_expand = generator["expand"]

    def expand(raw):
        prefix = "/home/kvn/workspace/.files/"
        if raw.strip() == prefix + "config/hermes-liquid-glass/hypr/liquid-glass.conf":
            return GLASS_FRAGMENT
        if raw.strip().startswith(prefix):
            return ROOT / raw.strip()[len(prefix):]
        return original_expand(raw)

    generator["build"].__globals__["expand"] = expand
    assert generator["main"]() == 0
    return SimpleNamespace(path=output, entry=entry, monitors=monitors, home=home)


@pytest.fixture
def migration_inventory(tmp_path):
    sandbox = tmp_path / "inventory"
    scripts = sandbox / "scripts"
    scripts.mkdir(parents=True)
    for name in ("build-hypr-lua-inventory", "hypr_lua_semantics.py", "hypr_lua_static.py"):
        shutil.copy2(ROOT / "scripts" / name, scripts / name)
    config = sandbox / "config/hyprland"
    config.mkdir(parents=True)
    for name in ("hyprland.legacy.conf", "lua", "hyprglass.conf", "phantomat"):
        (config / name).symlink_to(ROOT / "config/hyprland" / name)
    subprocess.run([sys.executable, str(scripts / "build-hypr-lua-inventory")], check=True)
    return config / "migration-inventory.json"
