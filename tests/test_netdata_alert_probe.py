import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('netdata_alert_probe', Path(__file__).parents[1] / 'config/netdata/test-alert.py')
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class AlertProbeTests(unittest.TestCase):
    def test_native_warning_observed_and_temporary_config_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.conf'
            alarms = {'alarms': {'system.cpu.test': {'name': probe.NAME, 'status': 'WARNING', 'chart': 'system.cpu'}}}
            reloads = []
            def reload(command, check):
                reloads.append(path.exists())
            with patch.object(probe, 'PATH', path), patch.object(probe.os, 'geteuid', return_value=0), \
                 patch.object(probe.subprocess, 'run', side_effect=reload), \
                 patch.object(probe.urllib.request, 'urlopen', return_value=io.BytesIO(json.dumps(alarms).encode())), \
                 contextlib.redirect_stdout(io.StringIO()) as output:
                probe.main()
            self.assertFalse(path.exists())
            self.assertEqual(reloads, [True, False])
            self.assertEqual(json.loads(output.getvalue())['status'], 'WARNING')

    def test_existing_user_configuration_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.conf'
            path.write_text('user-owned existing health rule')
            with patch.object(probe, 'PATH', path), patch.object(probe.os, 'geteuid', return_value=0):
                with self.assertRaisesRegex(RuntimeError, 'not an owned probe'):
                    probe.main()
            self.assertEqual(path.read_text(), 'user-owned existing health rule')

    def test_nonroot_invocation_has_no_filesystem_effect(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'test.conf'
            with patch.object(probe, 'PATH', path), patch.object(probe.os, 'geteuid', return_value=1000):
                with self.assertRaises(SystemExit):
                    probe.main()
            self.assertFalse(path.exists())


if __name__ == '__main__':
    unittest.main()
