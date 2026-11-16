"""User units resolve ~/.local/bin tools by bare name (groot-admit, kevin-push, ...).

The user manager's PATH is /usr/local/bin:/usr/bin, so every unit that calls a
~/.local/bin tool had to re-add it by hand; the ones that did not (systemd-run
jobs, library code) failed with "No such file or directory". Appending keeps
every name that resolves today resolving to the same binary.
"""
import os
from pathlib import Path
import subprocess
import tomllib

import pytest

ROOT = Path(__file__).resolve().parents[1]
GENERATOR = Path("/usr/lib/systemd/user-environment-generators/30-systemd-environment-d-generator")


@pytest.mark.skipif(not GENERATOR.exists(), reason="systemd environment.d generator not installed")
def test_user_manager_path_appends_local_bin(tmp_path):
    config = tmp_path / "config"
    (config / "environment.d").mkdir(parents=True)
    for conf in (ROOT / "config/environment.d").glob("*.conf"):
        (config / "environment.d" / conf.name).write_bytes(conf.read_bytes())
    home = tmp_path / "home"
    out = subprocess.run([str(GENERATOR)], capture_output=True, text=True, check=True,
                         env={"HOME": str(home), "PATH": "/usr/local/bin:/usr/bin",
                              "XDG_CONFIG_HOME": str(config)}).stdout
    path = dict(line.split("=", 1) for line in out.splitlines() if "=" in line)["PATH"]
    assert path.split(":") == ["/usr/local/bin", "/usr/bin", f"{home}/.local/bin"]


def test_local_bin_path_is_deployed():
    rows = tomllib.loads((ROOT / "config/host/groot.toml").read_text())["user"]
    sources = {row.get("source") for row in rows}
    assert "config/environment.d/05-local-bin-path.conf" in sources
