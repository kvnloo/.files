"""Keep the S25 supervisor in the desktop fleet's deployable configuration."""
import configparser
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
UNIT = 'z0live-fulltime.service'


class Z0liveFulltimeUnitTests(unittest.TestCase):
    def test_desktop_fleet_includes_supervisor(self):
        fleet = tomllib.loads((ROOT / 'fleet.toml').read_text())
        self.assertIn(UNIT, fleet['hosts']['desktop']['user_services'])

    def test_unit_runs_existing_supervisor_without_shell_or_root(self):
        path = ROOT / 'config/systemd/user' / UNIT
        self.assertTrue(path.is_file(), f'Missing deployable unit: {path}')
        unit = configparser.ConfigParser(interpolation=None)
        unit.read(path)
        service = unit['Service']
        self.assertEqual(service['Type'], 'simple')
        self.assertEqual(service['WorkingDirectory'], '/mnt/zer0models/github/autokernel/mobile')
        self.assertEqual(service['ExecStart'],
                         '/usr/bin/python3 /mnt/zer0models/github/autokernel/mobile/fulltime.py')
        self.assertEqual(service['Restart'], 'on-failure')
        self.assertEqual(service['RestartSec'], '120')
        self.assertEqual(unit['Install']['WantedBy'], 'default.target')
        self.assertNotIn('User', service)
        self.assertNotIn('ExecStartPre', service)
        self.assertNotIn('CPUQuota', service)


if __name__ == '__main__':
    unittest.main()
