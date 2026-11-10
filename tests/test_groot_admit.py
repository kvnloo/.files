#!/usr/bin/env python3
"""groot-admit holds on any exhausted resource, says who holds it, and records every verdict."""
import importlib.machinery
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('groot_admit', str(ROOT / 'scripts/groot-admit'))
admit = importlib.util.module_from_spec(importlib.util.spec_from_loader('groot_admit', loader))
loader.exec_module(admit)
ROOMY = {'MemAvailable': 12 << 20, 'SwapTotal': 24 << 20, 'SwapFree': 20 << 20}


class GrootAdmit(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        admit.VERDICTS = Path(self.tmp.name) / 'state/verdicts.jsonl'
        admit.meminfo, admit.full_psi_avg60, admit.zram_fill = lambda: dict(ROOMY), lambda: 0.0, lambda: 0.3

    def verdicts(self):
        return [json.loads(line) for line in admit.VERDICTS.read_text().splitlines()]

    def test_admits_with_headroom_and_records_it(self):
        self.assertEqual(admit.main(['--need-mb', '2000']), 0)
        self.assertEqual([(v['ok'], v['need_mb']) for v in self.verdicts()], [(True, 2000)])

    def test_holds_when_the_job_would_eat_the_desktop_reserve(self):
        admit.meminfo = lambda: dict(ROOMY, MemAvailable=7 << 20)
        self.assertEqual(admit.main(['--need-mb', '2000']), 75)
        self.assertFalse(self.verdicts()[0]['ok'])

    def test_holds_when_swap_is_full(self):
        admit.meminfo = lambda: dict(ROOMY, SwapFree=2 << 20)
        self.assertEqual(admit.main([]), 75)
        self.assertIn('swap', self.verdicts()[0]['reason'])

    def test_holds_when_zram_store_is_full_though_swap_looks_free(self):
        admit.zram_fill = lambda: 0.95
        self.assertEqual(admit.main([]), 75)
        self.assertIn('zram', self.verdicts()[0]['reason'])

    def test_every_user_unit_reports_disk_io_on_stop(self):
        installer_text = (ROOT / 'scripts/apply-agent-oom').read_text()
        for rel, section in (('service.d', 'Service'), ('scope.d', 'Scope')):
            text = (ROOT / 'config/systemd/user' / rel / '55-io-accounting.conf').read_text()
            self.assertIn(f'[{section}]\nIOAccounting=yes', text)
            self.assertIn(f"config/systemd/user/{rel}/55-io-accounting.conf'", installer_text)


if __name__ == '__main__':
    unittest.main()
