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


class ProbeErrorTests(unittest.TestCase):
    def test_s22_ssh_timeout_is_not_an_empty_stdout_index_error(self):
        node = fleet.registry()[1]['galaxy-s22plus']
        result = subprocess.CompletedProcess([], 255, '', 'ssh: connect to host X port 8022: Connection timed out\nSECRET')
        with patch.object(fleet.subprocess, 'run', return_value=result):
            value = fleet.probe(node, guest=True)
        self.assertEqual(value['status'], 'probe_error')
        self.assertEqual(value['node'], 'galaxy-s22plus')
        self.assertIn('ssh probe exited 255: connection timed out', value['message'])
        self.assertNotIn('IndexError', value['message'])
        self.assertNotIn('SECRET', json.dumps(value))

    def test_empty_or_invalid_output_is_a_named_probe_error(self):
        node = fleet.registry()[1]['galaxy-s22plus']
        for output, message in (('', 'no JSON output'), ('[]', 'not an object'),
                                ('not JSON', 'JSONDecodeError')):
            with self.subTest(output=output):
                with patch.object(fleet.subprocess, 'run',
                                  return_value=subprocess.CompletedProcess([], 0, output, '')):
                    value = fleet.probe(node, guest=True)
                self.assertEqual(value['status'], 'probe_error')
                self.assertIn(message, value['message'])

    def test_probe_exceptions_cannot_escape_the_scheduler(self):
        node = fleet.registry()[1]['galaxy-s22plus']
        for error, message in ((OSError('probe executable missing'), 'probe executable missing'),
                               (IndexError('malformed probe'), 'malformed probe'),
                               (subprocess.TimeoutExpired('ssh', 90), 'timed out after 90s')):
            with self.subTest(error=type(error).__name__):
                with patch.object(fleet.subprocess, 'run', side_effect=error):
                    value = fleet.probe(node, guest=True)
                self.assertEqual(value['status'], 'probe_error')
                self.assertIn(message, value['message'])

    def test_adb_and_boat_failures_use_the_same_probe_error_contract(self):
        nodes = fleet.registry()[1]
        for node in (nodes['galaxy-s22plus'], nodes['boat']):
            with self.subTest(node=node['name']):
                with patch.object(fleet.subprocess, 'run', side_effect=OSError('unavailable')):
                    value = fleet.probe(node)
                self.assertEqual(value['status'], 'probe_error')
                self.assertEqual(value['node'], node['name'])


class StagingSelectionTests(unittest.TestCase):
    def test_git_staging_counts_selected_bytes_not_ignored_dependencies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            subprocess.run(['git', '-C', str(root), 'init', '--quiet'], check=True)
            (root / '.git/info/exclude').write_text('ignored.venv\n')
            (root / 'tracked.py').write_bytes(b'1234')
            (root / 'new file.py').write_bytes(b'567')
            (root / 'ignored.venv').write_bytes(b'x' * 100)
            (root / 'submodule').mkdir()
            (root / 'submodule' / 'data').write_bytes(b'89')
            subprocess.run(['git', '-C', str(root), 'add', 'tracked.py'], check=True)
            self.assertEqual(python_jobs.staging_bytes(root), 9)

    def test_non_git_source_and_explicit_inputs_have_measured_sizes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'source'
            source.mkdir()
            (source / 'a').write_bytes(b'1234')
            (source / 'subdir').mkdir()
            (source / 'subdir' / 'b').write_bytes(b'567')
            extra = root / 'input'
            extra.write_bytes(b'89')
            self.assertEqual(python_jobs.staging_bytes(source, inputs=[f'{extra}:fixtures/input']), 9)
            self.assertEqual(python_jobs.staging_bytes(source, no_source=True,
                                                      inputs=[f'{extra}:fixtures/input']), 2)

    def test_fresh_capacity_accepts_zero_without_an_arbitrary_disk_floor(self):
        result = subprocess.CompletedProcess([], 0, '{"path":"/root/fleet-jobs","free_bytes":0}', '')
        with patch.object(python_jobs.subprocess, 'run', return_value=result) as run:
            self.assertEqual(python_jobs.staging_capacity(['ssh', 'guest'])['free_bytes'], 0)
        self.assertIn('statvfs', run.call_args.args[0][-1])
        self.assertNotIn('mkdir', run.call_args.args[0][-1])

    def selection(self, capacities, pinned=False):
        with tempfile.TemporaryDirectory() as tmp:
            nodes = {name: fleet.registry()[1][name] for name in ('omarchy-phone', 'galaxy-s22plus')}
            args = SimpleNamespace(node='omarchy-phone' if pinned else None, cls=None,
                                   arch='arm64', tolerate=[], cmd=['true'], no_src=False,
                                   src=tmp, mem=None, cpus=None, timeout=30, idempotent=False,
                                   fetch=[], input=[], guest=True, python_venv=True)
            def health(node, staging=False):
                return {'ts': time.time(), 'load1': 0 if node['name'] == 'omarchy-phone' else 4,
                        'ncpu': 8, 'mem_available_mb': 0,
                        'staging_capacity': {'free_bytes': capacities[node['name']]}}
            with patch.object(fleet, 'STATE', Path(tmp)), \
                 patch.object(fleet, 'registry', return_value=({}, nodes)), \
                 patch.object(fleet, 'k8s_nodes', return_value={}), \
                 patch.object(fleet, 'probe_python_guest', side_effect=health), \
                 patch.object(python_jobs, 'staging_bytes', return_value=1024) as measure, \
                 patch.object(python_jobs, 'snapshot', side_effect=ValueError('stop before transfer')) as snapshot:
                with self.assertRaises(SystemExit) as failure:
                    fleet.cmd_run(args)
                self.assertEqual(failure.exception.code, 75)
            return snapshot.call_args.args[0][-1] if snapshot.called else None, measure.call_count

    def test_phone_pool_skips_full_guest_for_this_source_size(self):
        selected, measurements = self.selection({'omarchy-phone': 0, 'galaxy-s22plus': 1024})
        self.assertEqual(selected, 'root@100.97.11.22')
        self.assertEqual(measurements, 1)

    def test_phone_pool_accepts_exact_fit_and_holds_when_no_guest_fits(self):
        self.assertEqual(self.selection({'omarchy-phone': 1024, 'galaxy-s22plus': 2048})[0],
                         'root@100.104.42.85')
        self.assertIsNone(self.selection({'omarchy-phone': 0, 'galaxy-s22plus': 1023})[0])

    def test_pinned_phone_does_not_gain_a_resource_admission_floor(self):
        selected, measurements = self.selection({'omarchy-phone': 0, 'galaxy-s22plus': 1024}, pinned=True)
        self.assertEqual(selected, 'root@100.104.42.85')
        self.assertEqual(measurements, 0)


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

    def test_static_omalauncher_proc_uptime_does_not_report_restart(self):
        # Retained S25 49c1/66ad receipts had this frozen /proc/uptime value
        # and the same tracer identity, despite successful command completion.
        proc_reads = []
        def read_proc(path):
            proc_reads.append(str(path))
            return {
                '/proc/uptime': '292659.57 2341276.58',
                '/proc/self/status': 'TracerPid:\t2074\n',
                '/proc/2074/stat': '2074 (proot) ' + ' '.join(['0'] * 19 + ['27758720']),
                '/proc/sys/kernel/random/boot_id': 'c4719f5c-4da0-45d3-81d9-48d62e7f2ade',
            }[str(path)]
        receipts = []
        with patch.object(Path, 'read_text', read_proc), \
             patch.object(time, 'clock_gettime', side_effect=[301000.0, 301093.889]) as clock:
            for _ in range(2):
                with patch('builtins.print') as printed:
                    exec(python_jobs.SNAPSHOT, {})
                receipts.append(json.loads(printed.call_args.args[0]))
        self.assertNotIn('/proc/uptime', proc_reads)
        self.assertEqual(clock.call_args_list[0].args, (time.CLOCK_BOOTTIME,))
        self.assertFalse(python_jobs.restarted(*receipts, 93.889))
        for changes in ({'boot_id': 'new-boot'}, {'guest_identity': [2075, '30105000']},
                        {'guest_identity': [2074, '30105000']}, {'uptime': 3.0}):
            with self.subTest(changes=changes):
                self.assertTrue(python_jobs.restarted(
                    receipts[0], {**receipts[1], **changes}, 93.889))

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
    def test_pool_capacity_read_failure_is_a_probe_error_not_a_scheduler_exception(self):
        node = fleet.registry()[1]['omarchy-phone']
        android = {'transport': 'adb', 'power': {'on_ac': False, 'batteries': [{'pct': 80}]}}
        with patch.object(fleet, 'probe', side_effect=[android, {'load1': 0}]), \
             patch.object(python_jobs, 'staging_capacity', side_effect=ValueError('capacity unavailable')):
            value = fleet.probe_python_guest(node, staging=True)
        self.assertEqual(value['status'], 'probe_error')
        self.assertIn('capacity unavailable', value['message'])

    def test_python_guest_preserves_structured_native_probe_failure(self):
        node = fleet.registry()[1]['omarchy-phone']
        failure = fleet.probe_error(node, 'native transport unavailable', 'adb')
        with patch.object(fleet, 'probe', return_value=failure):
            self.assertEqual(fleet.probe_python_guest(node), failure)

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
                     patch('fleet_paths.runs_dir', return_value=Path(tmp) / 'runs'), \
                     patch.dict(os.environ, {'FLEET_TEST_PLACEMENT': json.dumps({
                         'selected_lane': 'phones', 'reason': 'mbp-owned-quota-unavailable'})}), \
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
                receipt = json.loads(next((Path(tmp) / 'runs').glob('*.json')).read_text())
                self.assertEqual(receipt['placement']['selected_node'], 'omarchy-phone')
                self.assertEqual(receipt['placement']['reason'], 'mbp-owned-quota-unavailable')
                durable = json.loads(next((Path(tmp) / 'phone-jobs/omarchy-phone').glob('*.json')).read_text())
                self.assertEqual(durable['placement'], receipt['placement'])


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
