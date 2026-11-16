"""`uv cache prune` holds uv's exclusive cache lock for its whole walk.

Every other uv/uvx call waits for that lock and gives up after UV_LOCK_TIMEOUT
(300 s by default). Run from an idle-IO unit against the HDD cache after a boot,
prune held the lock for 30+ minutes, and n722bd-collector and the phone nudges
failed in the meantime. So each scheduled prune must be killed well before readers
time out.
"""

import re
from pathlib import Path

UNITS = Path(__file__).resolve().parents[1] / "config/systemd/user"
READER_TIMEOUT = 300


def prune_lines():
    for unit in sorted(UNITS.rglob("*")):
        if unit.is_file():
            for line in unit.read_text(errors="replace").splitlines():
                if line.startswith("Exec") and "uv cache prune" in line:
                    yield unit.name, line


def test_scheduled_uv_prunes_release_the_lock_before_readers_time_out():
    lines = list(prune_lines())
    assert lines, "no scheduled uv cache prune found; update this test"
    for name, line in lines:
        m = re.search(r"/usr/bin/timeout (?:-s \w+ )?(?:-k \d+ )?(\d+)\s+\S*uv cache prune", line)
        assert m, f"{name}: unbounded prune: {line}"
        assert int(m.group(1)) < READER_TIMEOUT, f"{name}: {line}"
