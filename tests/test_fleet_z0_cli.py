"""Exercise the executable adapter with a bounded local doctor transport fixture."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('status,doctor_exit,adapter_exit', [
    ('MATCH', 0, 0), ('DRIFT', 1, 1), ('UNKNOWN', 0, 2), ('ERROR', 1, 2),
])
def test_executable_status_and_argv(tmp_path, status, doctor_exit, adapter_exit):
    fleet = tmp_path / 'fleet.toml'
    fleet.write_text('[hosts.local]\nmatch_hostnames = '+json.dumps([socket.gethostname()])+
                     '\n[hosts.local.z0_components]\ncomponents = []\n')
    doctor = tmp_path / 'z0'
    doctor.write_text('#!'+sys.executable+'\nimport json,sys,socket\n'
                      'assert sys.argv[1:5] == ["doctor","--bindings","--json","--host-profile"]\n'
                      'assert len(sys.argv) == 6\n'
                      'report = {"host":socket.gethostname(),"status":'+repr(status)+','
                      '"configs":[{"harness":"codex","profile":"global","status":'+repr(status)+','
                      '"desired":[],"bound":[],"findings":[]}],"findings":[],"env":"PRIVATE"}\n'
                      'print(json.dumps(report))\nsys.exit('+str(doctor_exit)+')\n')
    doctor.chmod(0o700)
    proc = subprocess.run([sys.executable, str(ROOT / 'scripts/fleet-z0-health'),
                           '--json', '--host-profile', str(fleet)],
                          env={**os.environ, 'Z0_BIN': str(doctor)},
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == adapter_exit, proc.stderr
    result = json.loads(proc.stdout)
    assert result['status'] == status
    assert result['healthy'] is (status == 'MATCH')
    assert 'PRIVATE' not in proc.stdout


def test_unreadable_manifest_is_structured_error(tmp_path):
    proc = subprocess.run([sys.executable, str(ROOT / 'scripts/fleet-z0-health'),
                           '--json', '--host-profile', str(tmp_path / 'missing.toml')],
                          capture_output=True, text=True, timeout=10)
    assert proc.returncode == 2
    assert json.loads(proc.stdout)['status'] == 'ERROR'
