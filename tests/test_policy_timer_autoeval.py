"""Execute the declared service command with controlled dependency executables."""
import configparser
import os
from pathlib import Path
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('failure,expected',[(0,['python -m z0int.policy.autoeval tick','python -m z0int.cli policy ingest','python -m z0int.cli policy compile']),
                                             (1,['python -m z0int.policy.autoeval tick'])])
def test_policy_timer_orders_discovery_and_stops_on_failure(tmp_path,failure,expected):
    unit = configparser.ConfigParser(interpolation=None,strict=False)
    unit.read(ROOT/'config/systemd/user/z0int-policy.service')
    command = shlex.split(unit['Service']['ExecStart'])
    assert command[:2]==['/bin/sh','-ec']
    trace = tmp_path/'trace'
    executable = tmp_path/'python'
    executable.write_text('#!/bin/sh\nprintf "python %s\\n" "$*" >> "$TRACE"\n'+
                          'if [ "$*" = "-m z0int.policy.autoeval tick" ]; then exit "$FAIL_DISCOVERY"; fi\nexit 0\n')
    executable.chmod(0o755)
    result = subprocess.run(command,env={**os.environ,'PATH':str(tmp_path)+':/usr/bin:/bin',
                                        'TRACE':str(trace),'FAIL_DISCOVERY':str(failure)},check=False)
    assert result.returncode==failure
    assert trace.read_text().splitlines()==expected


def test_identity_hasher_is_separate_idle_and_bounded():
    unit = configparser.ConfigParser(interpolation=None, strict=False)
    unit.read(ROOT/'config/systemd/user/z0int-model-identity.service')
    service = unit['Service']
    assert shlex.split(service['ExecStart']) == ['python', '-m', 'z0int.policy.autoeval', 'identities']
    assert service['Nice'] == '19'
    assert service['IOSchedulingClass'] == 'idle'
    assert service['MemoryMax'] == '256M'
    assert 'CPUQuota' not in service
    policy = configparser.ConfigParser(interpolation=None, strict=False)
    policy.read(ROOT/'config/systemd/user/z0int-policy.service')
    assert policy['Service']['TimeoutStartSec'] == '5min'
    for suffix, section in [('path', 'Path'), ('timer', 'Timer')]:
        trigger = configparser.ConfigParser(interpolation=None, strict=False)
        trigger.read(ROOT/f'config/systemd/user/z0int-model-identity.{suffix}')
        assert trigger[section]['Unit'] == 'z0int-model-identity.service'
    assert trigger['Timer']['OnCalendar'] == 'daily'
