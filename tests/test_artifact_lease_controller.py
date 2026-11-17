import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('lease_controller', Path(__file__).resolve().parents[1] / 'scripts/artifact-lease-controller.py')
c = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(c)


class ControllerTests(unittest.TestCase):
    def test_strict_ssh(self):
        self.assertIn('StrictHostKeyChecking=yes', c.SSH)
        self.assertIn('BatchMode=yes', c.SSH)
        self.assertIn('ConnectTimeout=8', c.SSH)
        self.assertIn('ControlPath=none', c.SSH)

    def test_bounded_transport(self):
        with patch.object(c.subprocess, 'run', return_value=subprocess.CompletedProcess([], 0, '{}', '')) as call:
            self.assertEqual(c.run(['true']), '{}')
        self.assertEqual(call.call_args.kwargs['timeout'], 120)

    def test_failed_transport_closed(self):
        with patch.object(c.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '{}', 'failure')):
            with self.assertRaises(RuntimeError): c.run(['false'])

    def test_ssh_transport_flake_retried_once(self):
        # 2026-11-16: one 'banner exchange' timeout to a loaded MBP failed the whole 3-node report (7x/week).
        flake = subprocess.CompletedProcess([], 255, '', 'Connection timed out during banner exchange')
        ok = subprocess.CompletedProcess([], 0, '{}', '')
        with patch.object(c.time, 'sleep'), patch.object(c.subprocess, 'run', side_effect=[flake, ok]) as call:
            self.assertEqual(c.run(['ssh', 'mbp', 'true']), '{}')
        self.assertEqual(call.call_count, 2)
        with patch.object(c.time, 'sleep'), patch.object(c.subprocess, 'run', side_effect=[flake, flake]):
            with self.assertRaises(RuntimeError): c.run(['ssh', 'mbp', 'true'])
        remote = subprocess.CompletedProcess([], 1, '', 'remote failure')
        with patch.object(c.subprocess, 'run', side_effect=[remote]) as call:
            with self.assertRaises(RuntimeError): c.run(['ssh', 'mbp', 'false'])
        self.assertEqual(call.call_count, 1)

    def test_hardware_identity_required(self):
        with patch.object(c, 'run', side_effect=['List of devices attached\nwrong device\n', 'OTHER\nSM-S938U\n']):
            with self.assertRaises(RuntimeError):
                c.native_transport({'serial': 'R5CY93G2WNH', 'model': 'SM-S938U'})


    def test_single_core_and_classifier_shipped(self):
        node = {'transport': 'ssh', 'host': 'mbp', 'hostname': 'mbp', 'user': 'kvn'}
        with patch.object(c, 'run', return_value='{"would_reap_bytes": 0}') as call:
            c.execute('mbp', node, False, False, 'core source')
        argv, payload = call.call_args.args
        self.assertEqual(argv[:len(c.SSH)], c.SSH)
        self.assertEqual(json.loads(payload)['artifact-leases.py'], 'core source')
        self.assertIn('worktree-reaper.py', json.loads(payload))
        self.assertNotIn('--apply', argv[-1])
        self.assertIn('timeout 110s', argv[-1])
        self.assertIn('HUP INT TERM', argv[-1])

    def test_configured_pressure_is_not_cap(self):
        config = json.loads((c.ROOT / 'config/fleet/artifact-leases.json').read_text())
        self.assertEqual(config['pressure_free_percent'], 10)
        self.assertIn('not measured calibration or a resource cap', config['pressure_threshold_basis'])
        self.assertEqual(set(config['nodes']), {'groot', 'mbp', 's22', 's25'})


    def test_guest_report_is_aggregated(self):
        node = {'transport': 'adb', 'guest': {'transport': 'ssh', 'host': 's22', 'hostname': 'localhost', 'user': 'root'}}
        with patch.object(c, 'native_inventory', return_value={'would_reap_bytes': 0}), patch.object(c, 'run', return_value='{"would_reap_bytes": 42}'):
            report = c.execute('s22', node, False, False, 'core')
        self.assertEqual(report['would_reap_bytes'], 42)
        self.assertTrue(report['complete'])

    def test_unavailable_guest_retains_native_inventory(self):
        node = {'transport': 'adb', 'guest': {'transport': 'ssh', 'host': 's22', 'hostname': None, 'user': 'root'}}
        with patch.object(c, 'native_inventory', return_value={'would_reap_bytes': 0}), patch.object(c, 'run', side_effect=RuntimeError('offline')):
            report = c.execute('s22', node, False, False, 'core')
        self.assertFalse(report['complete'])
        self.assertEqual(report['native']['would_reap_bytes'], 0)

    def test_s25_mutation_hold_applies_to_both_lanes(self):
        node = {'transport': 'adb', 'apply_enabled': False,
                'guest': {'transport': 'ssh', 'host': 's25', 'hostname': 'localhost', 'user': 'root'}}
        with patch.object(c, 'native_inventory', return_value={'would_reap_bytes': 0}) as native, patch.object(c, 'run', return_value='{"would_reap_bytes": 0}') as guest:
            c.execute('s25', node, True, False, 'core')
        self.assertFalse(native.call_args.args[1])
        self.assertNotIn('--apply', guest.call_args.args[0][-1])


if __name__ == '__main__':
    unittest.main()
