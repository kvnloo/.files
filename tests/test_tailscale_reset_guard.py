"""~/.local/bin/tailscale refuses host-wide serve/funnel resets; route owners re-apply on start."""
import os
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
GUARD = ROOT / 'scripts/tailscale-guard'


@pytest.fixture
def run(tmp_path):
    calls = tmp_path / 'real-calls'
    real = tmp_path / 'tailscale-real'
    real.write_text(f'#!/bin/sh\necho "$*" >>{calls}\nexit 7\n')
    real.chmod(0o755)
    bindir = tmp_path / 'bin'
    bindir.mkdir()
    (bindir / 'systemctl').write_text('#!/bin/sh\nexit 0\n')
    (bindir / 'systemctl').chmod(0o755)

    def _run(*args, **env):
        e = {'HOME': str(tmp_path), 'TAILSCALE_REAL': str(real),
             'PATH': f'{bindir}:/usr/bin:/bin', **env}
        r = subprocess.run(['sh', str(GUARD), *args], env=e, text=True, capture_output=True)
        log = tmp_path / '.local/state/hermes-mobile-serve/serve-calls.log'
        return (r, calls.read_text().splitlines() if calls.exists() else [],
                log.read_text() if log.exists() else '')
    return _run


@pytest.mark.parametrize('args', [('serve', 'reset'), ('funnel', 'reset'), ('serve', '--yes', 'reset'),
                                  ('--socket=/x', 'serve', 'reset')])
def test_reset_is_refused_and_logged(run, args):
    r, calls, log = run(*args)
    assert r.returncode == 3 and calls == []
    assert '--https=<port> off' in r.stderr and 'REFUSED tailscale' in log


def test_reset_passes_with_explicit_override(run):
    r, calls, log = run('serve', 'reset', TAILSCALE_ALLOW_SERVE_RESET='1')
    assert r.returncode == 7 and calls == ['serve reset'] and 'REFUSED' not in log


def test_own_port_change_passes_and_is_logged(run):
    r, calls, log = run('serve', '--bg', '--https=18806', 'http://127.0.0.1:43195')
    assert r.returncode == 7 and calls == ['serve --bg --https=18806 http://127.0.0.1:43195']
    assert ':: tailscale serve --bg --https=18806' in log


@pytest.mark.parametrize('args', [('serve', 'status', '--json'), ('status',), ('version',)])
def test_reads_pass_through_unlogged(run, args):
    r, calls, log = run(*args)
    assert r.returncode == 7 and calls == [' '.join(args)] and log == ''


def test_guard_is_installed_as_local_bin_tailscale():
    rows = {row['live']: row['source'] for row in
            tomllib.loads((ROOT / 'config/host/groot.toml').read_text())['user']}
    assert rows['~/.local/bin/tailscale'] == 'scripts/tailscale-guard'
    assert os.access(GUARD, os.X_OK)


@pytest.mark.parametrize('unit, route', [
    ('garden-room.service', '--https=8790 http://127.0.0.1:8790'),
    ('temple-guard-story-preview.service', '--https=8447 http://127.0.0.1:4176'),
    ('lumenfold-final-origin.service', '--set-path=/lumenfold http://127.0.0.1:9153'),
    ('lumenfold-study-origin.service', '--set-path=/lumenfold-study http://127.0.0.1:9152'),
])
def test_route_owner_reapplies_its_route_on_start(unit, route):
    text = (ROOT / 'config/systemd/user' / unit).read_text()
    assert f'ExecStartPost=-/usr/bin/tailscale serve --bg {route}' in text
