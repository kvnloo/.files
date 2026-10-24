#!/usr/bin/env python3
"""Executable timer installation and normalized systemd semantics acceptance."""
import configparser
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PacketTimerTests(unittest.TestCase):
    def test_stamped_install_preserves_previous_unit(self):
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            units = home / '.config/systemd/user'
            units.mkdir(parents=True)
            prior = units / 'z0-state-packet.service'
            prior.write_text('prior content\n')
            subprocess.run(['bash', str(ROOT / 'scripts/install-state-packet-timer.sh')],
                env={**os.environ, 'HOME': str(home)}, check=True)
            self.assertTrue(prior.is_symlink())
            self.assertTrue(str(prior.resolve()).startswith(str(home / '.local/lib/z0-state-packet-units')))
            self.assertNotIn(str(ROOT), str(prior.resolve()))
            backups = list((home / '.local/state/z0int/startup-packet-unit-backups').glob('*/z0-state-packet.service'))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), 'prior content\n')
            service = configparser.ConfigParser(interpolation=None)
            service.read(prior)
            self.assertEqual(service['Service']['Type'], 'oneshot')
            self.assertEqual(service['Service']['ExecStart'], '%h/.local/lib/z0-state-packet/current/bin/generate-packet')
            self.assertEqual(service['Service']['UMask'], '0077')
            timer = configparser.ConfigParser(interpolation=None)
            timer.read(units / 'z0-state-packet.timer')
            self.assertEqual(timer['Timer']['OnCalendar'], '*:0/15')
            self.assertTrue(timer['Timer'].getboolean('Persistent'))
            self.assertEqual(timer['Timer']['Unit'], 'z0-state-packet.service')
            subprocess.run(['systemd-analyze', 'calendar', timer['Timer']['OnCalendar']], check=True)
            self.assertFalse((units / 'timers.target.wants').exists())


if __name__ == '__main__':
    unittest.main()
