"""Exercise the actual fleet health callback without cluster or host mutations."""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('fleet_z0_integration', str(ROOT / 'scripts/fleet'))
spec = importlib.util.spec_from_loader(loader.name, loader)
fleet = importlib.util.module_from_spec(spec)
loader.exec_module(fleet)


@pytest.mark.parametrize('scenario,expected', [
    ('drift', 'DRIFT'), ('timeout', 'UNKNOWN'), ('malformed', 'UNKNOWN'),
    ('invalid-status', 'UNKNOWN'), ('conflicting-exit', 'UNKNOWN'),
])
def test_bindings_remain_server_only_and_never_drive_compute_health(tmp_path, scenario, expected):
    nodes = {name: {'name': name, 'role': role, 'kind': 'linux', 'k8s': role == 'worker',
                    'tailnet_ip': name, 'health': {'strikes': 1, 'on_unhealthy': 'cordon'}}
             for name, role in [('groot', 'server'), ('mbp', 'worker')]}
    (tmp_path / 'health').mkdir()
    prior = '{"mbp":{"bad":0,"good":0,"paused":false}}\n'
    (tmp_path / 'health/state.json').write_text(prior)
    calls = []

    def run(argv, **kwargs):
        calls.append(argv)
        if str(argv[1]).endswith('fleet-z0-health'):
            assert argv[2:] == ['--json', '--host-profile', str(ROOT / 'fleet.toml')]
            assert kwargs['timeout'] == 45
            if scenario == 'timeout':
                raise subprocess.TimeoutExpired(argv, 45)
            if scenario == 'malformed':
                return subprocess.CompletedProcess(argv, 0, 'not-json')
            status = 'invalid' if scenario == 'invalid-status' else 'MATCH' if scenario == 'conflicting-exit' else 'DRIFT'
            return subprocess.CompletedProcess(argv, 1, json.dumps({
                'status': status, 'healthy': status == 'MATCH', 'available': True,
                'host_id': 'desktop', 'configs': [], 'findings': [], 'reason': 'bindings-differ'}))
        return subprocess.CompletedProcess(argv, 0)

    args = argparse.Namespace(node=None, set=[], strikes=None, dry_run=True)
    with patch.object(fleet, 'STATE', tmp_path), \
         patch.object(fleet, 'registry', return_value=({'nodes': {}}, nodes)), \
         patch.object(fleet, 'k8s_nodes', return_value={'mbp': {'unschedulable': False}}), \
         patch.object(fleet, 'tailnet_online', return_value={}), \
         patch.object(fleet, 'node_events', return_value=[]), \
         patch.object(fleet, 'probe', return_value={'max_temp_c': 40}), \
         patch.object(fleet, 'judge', return_value=([], [])), \
         patch.object(fleet, 'kc') as kubectl, \
         patch.object(fleet.subprocess, 'run', side_effect=run):
        assert fleet.cmd_health(args) == 0
    kubectl.assert_not_called()
    assert (tmp_path / 'health/state.json').read_text() == prior
    server = json.loads((tmp_path / 'health/groot.json').read_text())
    worker = json.loads((tmp_path / 'health/mbp.json').read_text())
    assert server['bindings']['status'] == expected
    assert server['healthy'] and server['action'] == 'none'
    assert worker['bindings'] is None and worker['healthy']
    assert len([a for a in calls if str(a[1]).endswith('fleet-z0-health')]) == 1
    if expected == 'UNKNOWN':
        assert server['bindings']['healthy'] is False
        assert server['bindings']['available'] is False
