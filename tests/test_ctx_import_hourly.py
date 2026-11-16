"""ctx-import-hourly must not spend a run on a ctx daemon that is switched off on purpose."""
import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/ctx-import-hourly"


def run(tmp_path, off_switch):
    calls = tmp_path / "calls"
    ctx = tmp_path / "ctx"
    ctx.write_text(f"#!/bin/sh\necho \"$@\" >> {calls}\necho '{{\"lexical\":{{}}}}'\n")
    ctx.chmod(0o755)
    off = tmp_path / "ctx-daemon-off"
    if off_switch:
        off.touch()
    log = tmp_path / "ctx-import.log"
    env = dict(os.environ, CTX_BIN=str(ctx), CTX_IMPORT_LOG=str(log), CTX_DAEMON_OFF=str(off))
    r = subprocess.run(["bash", str(SCRIPT)], env=env, capture_output=True, text=True, timeout=60)
    return r, (calls.read_text() if calls.exists() else ""), (log.read_text() if log.exists() else "")


def test_daemon_off_switch_fails_fast_without_touching_ctx(tmp_path):
    r, calls, log = run(tmp_path, off_switch=True)
    assert r.returncode == 2
    assert calls == ""  # no index scan, no auto-mode attempt
    assert "ctx-daemon-off" in r.stderr and "parked" in log
