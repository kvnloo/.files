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

    def test_hardware_identity_required(self):
        with patch.object(c, 'run', side_effect=['List of devices attached\nwrong device\n', 'OTHER\nSM-S938U\n']):
            with self.assertRaises(RuntimeError):
                c.native_transport({'serial': 'R5CY93G2WNH', 'model': 'SM-S938U'})

    def test_native_unknown_visibility_never_deletes(self):
        node = {'serial': 'R5CY93G2WNH', 'model': 'SM-S938U'}
        with patch.object(c, 'native_transport', return_value='transport'), patch.object(c, 'run', return_value='IDENTITY\tR5CY93G2WNH\tSM-S938U\nKEEP\t/data/local/tmp/fleet-jobs/j1\t1\n') as call:
            report = c.native_inventory(node, True)
        self.assertEqual(report['would_reap_bytes'], 0)
        self.assertEqual(report['proc_visibility'], 'unknown')
        self.assertEqual(report['decision'], 'KEEP')
        self.assertNotIn('rm ', call.call_args.args[1])

    def test_native_identity_race_closed(self):
        with patch.object(c, 'native_transport', return_value='transport'), patch.object(c, 'run', return_value='IDENTITY\tOTHER\tSM-S938U\n'):
            with self.assertRaises(RuntimeError): c.native_inventory({'serial': 'R5CY93G2WNH', 'model': 'SM-S938U'}, True)

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

    def test_observed_native_visibility_is_not_canned_unknown(self):
        node = {'serial': 'R5CY93G2WNH', 'model': 'SM-S938U'}
        with patch.object(c, 'native_transport', return_value='transport'), patch.object(c, 'run', return_value='IDENTITY\tR5CY93G2WNH\tSM-S938U\nPROC_VISIBILITY\tobserved\n'):
            self.assertEqual(c.native_inventory(node, False)['proc_visibility'], 'observed')

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


if __name__ == '__main__':
    unittest.main()
