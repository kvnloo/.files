"""User guards must use installed code and preserve the declared memory policy."""
from pathlib import Path
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]


class UserGuardContracts(unittest.TestCase):
    def test_gateway_watch_uses_installed_guard(self):
        unit = (ROOT / 'config/systemd/user/z0-guard-gateway-watch.service').read_text()
        self.assertIn('ExecStart=%h/.local/bin/z0-guard gateway-watch\n', unit)
        self.assertNotIn('PYTHONPATH=', unit)
        self.assertNotIn('z0-wt/', unit)

    def test_agent_policy_matches_owner_approved_intent(self):
        intent = tomllib.loads((ROOT / 'config/host/groot-memory-intent.toml').read_text())
        policy = (ROOT / 'config/systemd/user/agent.slice.d/60-oomd-desktop-guard.conf').read_text()
        expected = {'MemoryHigh': '13G', 'MemoryMax': '16G', 'MemorySwapMax': '6G'}
        for key, value in expected.items():
            with self.subTest(property=key):
                row = next(row for row in intent['unit']
                           if row['unit'] == 'agent.slice' and row['property'] == key)
                self.assertEqual(row['equals'], value)
                self.assertEqual(row['owner'], '60-oomd-desktop-guard.conf')
                self.assertIn(f'{key}={value}\n', policy)


if __name__ == '__main__':
    unittest.main()
