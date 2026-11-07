"""z0live keeps its :8791 Tailscale Serve route: re-applied on start, healed by a timer."""
import json
import re
import shlex
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
UNITS = ROOT / 'config/systemd/user'
ROUTE = '--https=8791 http://127.0.0.1:8791'


def test_broker_reapplies_route_on_start_without_failing():
    unit = (UNITS / 'z0live.service').read_text()
    assert f'ExecStartPost=-/usr/bin/tailscale serve --bg {ROUTE}' in unit


def test_check_timer_is_declared_and_enabled():
    rows = {row['live']: row['source'] for row in
            tomllib.loads((ROOT / 'config/host/groot.toml').read_text())['user']}
    base = '~/.config/systemd/user/'
    assert rows[base + 'z0live-serve-check.service'] == 'config/systemd/user/z0live-serve-check.service'
    assert rows[base + 'z0live-serve-check.timer'] == 'config/systemd/user/z0live-serve-check.timer'
    assert rows[base + 'timers.target.wants/z0live-serve-check.timer'] == 'config/systemd/user/z0live-serve-check.timer'
    timer = (UNITS / 'z0live-serve-check.timer').read_text()
    assert 'OnUnitActiveSec=5min' in timer and 'WantedBy=timers.target' in timer


def _jq_filter() -> str:
    line = next(l for l in (UNITS / 'z0live-serve-check.service').read_text().splitlines()
                if l.startswith('ExecStart='))
    # systemd unquotes the outer "..." and \" escapes the same way POSIX sh does.
    script = shlex.split(line.removeprefix('ExecStart='))[2]
    assert ROUTE in script and 'healed' in script
    return re.search(r"jq -e '([^']+)'", script).group(1)


@pytest.mark.skipif(not shutil.which('jq'), reason='jq not installed')
@pytest.mark.parametrize('web, present', [
    ({'h.ts.net:8791': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8791'}}}}, True),
    ({'h.ts.net:18791': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:8791'}}}}, False),
    ({'h.ts.net:8791': {'Handlers': {'/': {'Proxy': 'http://127.0.0.1:1'}}}}, False),
    (None, False),
])
def test_check_detects_missing_or_wrong_route(web, present):
    status = json.dumps({'Web': web} if web is not None else {})
    result = subprocess.run(['jq', '-e', _jq_filter()], input=status, text=True,
                            capture_output=True, check=False)
    assert (result.returncode == 0) is present
