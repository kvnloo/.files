"""Routing must use the installed backend, not a temporary source checkout."""
import configparser
from pathlib import Path
import unittest


class RoutingUnit(unittest.TestCase):
    def test_routing_uses_stamped_launcher(self):
        root = Path(__file__).resolve().parents[1]
        unit = configparser.ConfigParser(interpolation=None)
        unit.read(root / 'config/systemd/user/z0-guard-routing.service')
        self.assertEqual(unit['Service']['ExecStart'], '%h/.local/bin/z0-guard routing')
        self.assertNotIn('PYTHONPATH', unit['Service'].get('Environment', ''))
        self.assertEqual(unit['Service']['ProtectSystem'], 'strict')
        self.assertEqual(unit['Service']['ReadWritePaths'], '%h/.local/state/z0-guard')
