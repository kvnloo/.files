"""Execute the declared service command with controlled dependency executables."""
import configparser
import os
from pathlib import Path
import shlex
import subprocess

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('failure,expected',[(0,['python3 -m z0int.policy.autoeval tick','z0int policy ingest','z0int policy compile']),
                                             (1,['python3 -m z0int.policy.autoeval tick'])])
def test_policy_timer_orders_discovery_and_stops_on_failure(tmp_path,failure,expected):
    unit = configparser.ConfigParser(interpolation=None,strict=False)
    unit.read(ROOT/'config/systemd/user/z0int-policy.service')
    command = shlex.split(unit['Service']['ExecStart'])
    assert command[:2]==['/bin/sh','-ec']
    trace = tmp_path/'trace'
    for name in ('python3','z0int'):
        executable = tmp_path/name
        executable.write_text('#!/bin/sh\nprintf "%s %s\\n" "'+name+'" "$*" >> "$TRACE"\n'+
                              ('exit "$FAIL_DISCOVERY"\n' if name=='python3' else 'exit 0\n'))
        executable.chmod(0o755)
    result = subprocess.run(command,env={**os.environ,'PATH':str(tmp_path)+':/usr/bin:/bin',
                                        'TRACE':str(trace),'FAIL_DISCOVERY':str(failure)},check=False)
    assert result.returncode==failure
    assert trace.read_text().splitlines()==expected
