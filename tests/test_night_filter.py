"""Exercise the real CLI with an isolated Hyprland IPC boundary, never the host."""
import json
import os
from pathlib import Path
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/night-filter"


@pytest.fixture
def backend(tmp_path):
    binary = tmp_path / "bin"
    binary.mkdir()
    adapter = binary / "hyprctl"
    adapter.write_text('''#!/usr/bin/env python3
import json, os, pathlib, sys
root = pathlib.Path(os.environ["FILTER_TEST_ROOT"])
shader = root / "shader"
with (root / "calls").open("a") as out: out.write(json.dumps(sys.argv[1:]) + "\\n")
if (root / "fail").exists():
    print("isolated IPC failure", file=sys.stderr)
    sys.exit(1)
if sys.argv[1] == "-j":
    print(json.dumps({"str": shader.read_text() if shader.exists() else ""}))
else:
    shader.write_text(sys.argv[-1])
    print("ok")
''')
    adapter.chmod(0o755)
    env = os.environ | {"PATH": f"{binary}:{os.environ['PATH']}", "FILTER_TEST_ROOT": str(tmp_path),
                       "HOME": str(tmp_path), "XDG_STATE_HOME": str(tmp_path / "state"),
                       "XDG_CONFIG_HOME": str(tmp_path / "config"),
                       "NIGHT_FILTER_SHADER": str(ROOT / "config/hyprland/shaders/night.frag")}
    env.pop("HYPRLAND_INSTANCE_SIGNATURE", None)
    def invoke(*args, success=True):
        result = subprocess.run([str(SCRIPT), *map(str, args), "--json"], env=env,
                                text=True, capture_output=True)
        assert (result.returncode == 0) == success, result.stderr or result.stdout
        return json.loads(result.stdout)
    return tmp_path, env, invoke


def test_off_levels_persist_without_enabling(backend):
    root, _, call = backend
    assert call("status")["darkness"] == 45
    assert call("set-blue-light", 63)["blue_light"] == 63
    assert call("set-darkness", 28)["darkness"] == 28
    assert not call("status")["enabled"]
    assert not (root / "shader").exists()
    assert not any(json.loads(line)[0] == "keyword" for line in (root / "calls").read_text().splitlines())
    assert call("on")["enabled"]
    assert call("status")["blue_light"] == 63


def test_independent_live_values_reload_and_restore(backend):
    root, _, call = backend
    call("on")
    first = (root / "shader").read_text()
    state = call("set-blue-light", 20)
    second = (root / "shader").read_text()
    assert first != second
    assert state["darkness"] == 45
    state = call("set-darkness", 90)
    assert state["blue_light"] == 20
    shader = Path((root / "shader").read_text()).read_text()
    assert "const float DIM = 0.10;" in shader
    assert "const float BLUE_LIGHT = 0.20;" in shader
    assert not call("off")["enabled"]
    assert call("toggle")["enabled"]
    assert call("status")["darkness"] == 90


def test_external_state_and_foreign_shader_ownership(backend):
    root, _, call = backend
    call("on")
    (root / "shader").write_text("")
    assert not call("status")["enabled"]
    (root / "shader").write_text("/another/tool.frag")
    assert call("status")["foreign_shader"]
    assert call("on", success=False)["error"]
    call("off")
    assert (root / "shader").read_text() == "/another/tool.frag"
    assert call("set-darkness", 30)["darkness"] == 30
    assert (root / "shader").read_text() == "/another/tool.frag"


def test_missing_active_shader_can_still_be_disabled(backend):
    root, _, call = backend
    call("on")
    Path((root / "shader").read_text()).unlink()
    assert call("status")["enabled"]
    assert not call("off")["enabled"]


def test_unavailable_backend_reports_failure(backend):
    root, _, call = backend
    (root / "fail").touch()
    state = call("status", success=False)
    assert not state["available"]
    assert "isolated IPC failure" in state["error"]


@pytest.mark.parametrize("command,value", [("set-blue-light", -1), ("set-blue-light", 101), ("set-darkness", 91)])
def test_invalid_levels_rejected_before_ipc(backend, command, value):
    root, env, _ = backend
    result = subprocess.run([str(SCRIPT), command, str(value)], env=env, capture_output=True)
    assert result.returncode == 2
    assert not (root / "calls").exists()


def test_schedule_uses_saved_levels_and_existing_timers(backend):
    root, env, call = backend
    # Deliberately synthetic location, not the user's private configuration.
    config = root / "config"
    config.mkdir()
    (config / "night-filter.conf").write_text("NIGHT_LAT=0\nNIGHT_LON=0\n")
    for name in ("systemctl", "systemd-run"):
        tool = root / "bin" / name
        tool.write_text('#!/usr/bin/env python3\nimport os, pathlib, sys\np = pathlib.Path(os.environ["FILTER_TEST_ROOT"]) / "timers"\nwith p.open("a") as out: out.write(" ".join(sys.argv) + "\\n")\n')
        tool.chmod(0o755)
    call("set-blue-light", 58)
    call("set-darkness", 32)
    state = call("schedule")
    assert (state["blue_light"], state["darkness"]) == (58, 32)
    timers = (root / "timers").read_text()
    assert "night-filter-sunset.timer" in timers
    assert "night-filter-sunrise.timer" in timers
    assert "reset-failed" in timers
    # A manual toggle must not touch timers.
    call("toggle")
    assert (root / "timers").read_text() == timers
