import importlib.util
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import fleet_paths


class FleetPathsTests(unittest.TestCase):
    def test_explicit_run_override(self):
        with patch.dict(os.environ, {'FLEET_RUNS': '/bulk/custom', 'FLEET_STATE': '/state'}, clear=True):
            self.assertEqual(fleet_paths.runs_dir(), Path('/bulk/custom'))

    def test_isolated_state_override(self):
        with patch.dict(os.environ, {'FLEET_STATE': '/test/state'}, clear=True):
            self.assertEqual(fleet_paths.runs_dir(), Path('/test/state/runs'))

    def test_groot_fails_closed_without_mount(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(fleet_paths.socket, 'gethostname', return_value='groot'), patch.object(os.path, 'ismount', return_value=False):
            with self.assertRaisesRegex(RuntimeError, 'not mounted'):
                fleet_paths.runs_dir()

    def test_groot_uses_bulk_disk(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(fleet_paths.socket, 'gethostname', return_value='groot'), patch.object(os.path, 'ismount', return_value=True):
            self.assertEqual(fleet_paths.runs_dir(), Path('/mnt/zer0models/host-offload/home_kvn_.local_state_fleet_runs'))

    def test_other_host_keeps_home_state(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(fleet_paths.socket, 'gethostname', return_value='other'):
            self.assertEqual(fleet_paths.runs_dir(), Path.home() / '.local/state/fleet/runs')


if __name__ == '__main__':
    unittest.main()
