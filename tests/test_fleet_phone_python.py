"""Phone Python lane policy; no Android or guest services required by these tests."""
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import time
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import fleet_phone_python as python_jobs

loader = importlib.machinery.SourceFileLoader('fleet_python_under_test', str(ROOT / 'scripts/fleet'))
spec = importlib.util.spec_from_loader(loader.name, loader)
fleet = importlib.util.module_from_spec(spec)
loader.exec_module(fleet)


class GuestLifetimeTests(unittest.TestCase):
    def before(self):
        return {'uptime': 1000.0, 'boot_id': 'android-boot', 'guest_identity': [200, '1234']}

    def test_uninterrupted_guest_covers_whole_job(self):
        before = self.before()
        self.assertFalse(python_jobs.restarted(before, {**before, 'uptime': 1060.0}, 60.0))

    def test_uptime_reset_boot_change_and_proot_restart_fail(self):
        before = self.before()
        for changes in ({'uptime': 3.0}, {'boot_id': 'new-boot'},
                        {'guest_identity': [201, '1260']}, {'uptime': 1020.0}):
            with self.subTest(changes=changes):
                self.assertTrue(python_jobs.restarted(before, {**before, **changes}, 60.0))

    def test_missing_guest_identity_fails_closed(self):
        result = subprocess.CompletedProcess([], 0, json.dumps({**self.before(), 'guest_identity': None}), '')
        with patch.object(python_jobs.subprocess, 'run', return_value=result):
            with self.assertRaises(ValueError):
                python_jobs.snapshot(['ssh', 'guest'])

    def test_setup_uses_job_venv_guest_cache_and_preserves_argv_and_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            # Execute only the setup orchestration with subprocess calls intercepted.
            with patch.dict(os.environ, {'HOME': tmp}), \
                 patch.object(Path, 'cwd', return_value=Path(tmp) / 'src'), \
                 patch.object(python_jobs.subprocess, 'run', side_effect=[
                     subprocess.CompletedProcess([], 0), subprocess.CompletedProcess([], 0),
                     subprocess.CompletedProcess([], 7)]) as run, \
                 patch.object(sys, 'argv', ['-c', tmp + '/.cache/pip', 'python3', '-m', 'pytest', 'tests/space name.py']):
                with self.assertRaises(SystemExit) as exit:
                    exec(python_jobs.SETUP, {})
                self.assertEqual(exit.exception.code, 7)
                self.assertEqual(run.call_args_list[0].args[0], ['python3', '-m', 'venv', tmp + '/venv'])
                self.assertEqual(run.call_args_list[1].args[0][-3:], ['pip', 'install', 'pytest'])
                self.assertEqual(run.call_args_list[2].args[0], ['python3', '-m', 'pytest', 'tests/space name.py'])
                self.assertEqual(os.environ['PIP_CACHE_DIR'], tmp + '/.cache/pip')
                self.assertTrue(os.environ['PATH'].startswith(tmp + '/venv/bin:'))


class GuestAdmissionTests(unittest.TestCase):
    def test_phone_disk_space_is_not_an_agent_admission_limit(self):
        for name in ('omarchy-phone', 'galaxy-s22plus'):
            node = fleet.registry()[1][name]
            self.assertNotIn('min_disk_free_gb', node['health'])
            reasons, _ = fleet.judge(node, {
                'ts': time.time(), 'disk_root': {'free_gb': 0},
                'disk_lane': {'free_gb': 0}, 'disk_k3s': {'free_gb': 0}}, {}, {}, {})
            self.assertEqual(reasons, [])

    def test_android_battery_gate_precedes_ssh(self):
        node = fleet.registry()[1]['omarchy-phone']
        android = {'transport': 'adb', 'power': {'on_ac': False, 'batteries': [{'pct': 1}]}}
        with patch.object(fleet, 'probe', return_value=android) as probe:
            self.assertIn('battery', fleet.probe_python_guest(node)['error'])
            self.assertEqual(probe.call_count, 1)

    def test_healthy_adb_still_requires_guest_ssh(self):
        node = fleet.registry()[1]['omarchy-phone']
        android = {'transport': 'adb', 'power': {'on_ac': True, 'batteries': [{'pct': 1}]}}
        with patch.object(fleet, 'probe', side_effect=[android, {'error': 'SSH unavailable'}]) as probe:
            self.assertEqual(fleet.probe_python_guest(node), {'error': 'SSH unavailable'})
            self.assertEqual(probe.call_args.kwargs, {'guest': True})

    def test_guest_receives_current_android_power_not_stale_guest_power(self):
        node = fleet.registry()[1]['omarchy-phone']
        android = {'transport': 'adb', 'power': {'on_ac': False, 'batteries': [{'pct': 80}]}}
        with patch.object(fleet, 'probe', side_effect=[android, {'load1': 0, 'power': {}}]):
            self.assertEqual(fleet.probe_python_guest(node)['power'], android['power'])


class GuestExecutionTests(unittest.TestCase):
    def test_receipt_rejects_restart_and_missing_final_evidence(self):
        before = {'uptime': 1000.0, 'boot_id': 'boot', 'guest_identity': [200, '1'],
                  'pip_cache': '/root/.cache/pip'}
        cases = [(0, {**before, 'uptime': 1100.0}, 0, 'succeeded'),
                 (7, {**before, 'uptime': 1100.0}, 7, 'failed'),
                 (0, {**before, 'uptime': 3.0}, 76, 'guest_restarted'),
                 (0, subprocess.TimeoutExpired('ssh', 30), 255, 'guest_unavailable')]
        for command_rc, after, expected, status in cases:
            with self.subTest(status=status), tempfile.TemporaryDirectory() as tmp:
                args = SimpleNamespace(node='omarchy-phone', cls=None, arch=None, tolerate=[],
                                       cmd=['python3', '-m', 'pytest'], no_src=True, src=None,
                                       mem=None, cpus=None, timeout=30, idempotent=False,
                                       fetch=[], input=[], guest=True, python_venv=True)
                probe = {'ts': time.time(), 'load1': 0, 'ncpu': 8, 'mem_available_mb': 0}
                with patch.object(fleet, 'STATE', Path(tmp)), \
                     patch.object(fleet, 'k8s_nodes', return_value={}), \
                     patch.object(fleet, 'probe_python_guest', return_value=probe), \
                     patch.object(fleet.subprocess, 'run'), \
                     patch.object(python_jobs, 'snapshot', side_effect=[before, after]), \
                     patch.object(fleet.phone_controller, 'run', return_value=command_rc) as execute:
                    self.assertEqual(fleet.cmd_run(args), expected)
                logs = list((Path(tmp) / 'runs').glob('*.log'))
                self.assertEqual(len(logs), 1)
                text = logs[0].read_text()
                self.assertIn('# guest_before=', text)
                self.assertIn('status=%s exit=%s' % (status, expected), text)
                payload = execute.call_args.args[3]
                self.assertEqual(payload['argv'][3], '/root/.cache/pip')
                self.assertNotIn('mem_mb', payload)
                self.assertEqual(payload['max_attempts'], 1)


class BuildDispatchTests(unittest.TestCase):
    def test_phone_nodes_and_health_selected_pool_use_uncapped_guest_venv(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            build = root / 'fleet-build'
            build.write_bytes((ROOT / 'scripts/fleet-build').read_bytes())
            fake = root / 'fleet'
            fake.write_text('#!%s\nimport json,sys\nprint(json.dumps(sys.argv[1:]))\n' % sys.executable)
            fake.chmod(0o700)
            for node in ('s25', 's22', 'phones'):
                with self.subTest(node=node):
                    result = subprocess.run(['bash', str(build), '--node', node, '--src', tmp,
                                             '--wait', '0', '--', 'python3', '-m', 'pytest'],
                                            capture_output=True, text=True, cwd=tmp, timeout=10)
                    self.assertEqual(result.returncode, 0, result.stderr)
                    argv = json.loads(result.stdout)
                    self.assertIn('--guest', argv)
                    self.assertIn('--python-venv', argv)
                    for cap in ('--mem', '--cpus', '--class'):
                        self.assertNotIn(cap, argv)
                    self.assertEqual('--node' in argv, node != 'phones')
                    self.assertEqual(argv[-3:], ['python3', '-m', 'pytest'])

    def test_phone_resource_flags_and_android_builds_are_rejected(self):
        for options in (['--mem', '1G'], ['--cpus', '2'], ['--android'], ['--jdk', '17']):
            with self.subTest(options=options):
                result = subprocess.run(['bash', str(ROOT / 'scripts/fleet-build'), '--node', 's25',
                                         *options, '--', 'true'], capture_output=True, text=True, timeout=10)
                self.assertEqual(result.returncode, 2, result.stderr)


if __name__ == '__main__':
    unittest.main()
