"""Storage guard contracts (11-16 incident): a disk that refuses writes pauses work at once.
Execute on MBP, never on the desktop."""
import errno
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('service_watch', ROOT / 'scripts/service-watch.py')
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


class FakeSystemd:
    def __init__(self, timers=(), scopes=(), slices=()):
        self.timers, self.scopes, self.slices = list(timers), list(scopes), list(slices)
        self.calls = []

    def __call__(self, *argv):
        self.calls.append(argv)
        out = ''
        if argv[:2] == ('list-units', '--type=timer'):
            out = ''.join(f'{t} loaded active waiting x\n' for t in self.timers)
        elif argv[:2] == ('list-units', '--type=scope'):
            out = ''.join(f'{s} loaded active running x\n' for s in self.scopes)
        elif argv[:2] == ('list-units', '--type=slice'):
            out = ''.join(f'{s} loaded active active x\n' for s in self.slices)
        return 0, out


class Guard(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.disk = self.root / 'disk'
        self.disk.mkdir()
        self.full = False
        real = sw.probe_write
        probe = patch.object(sw, 'probe_write', lambda d, size=sw.STORAGE_PROBE_BYTES:
                             errno.ENOSPC if self.full else real(d, size))
        probe.start(); self.addCleanup(probe.stop)
        self.systemd = FakeSystemd(timers=['factory-tick.timer', 'service-watch-heartbeat.timer'],
                                   scopes=['hermes-worker-kanban-t_1-run-2.scope', 'hermes-turn-local-x.scope'],
                                   slices=['app-factory\\x2dlane.slice', 'session.slice'])
        self.pushes = []
        self.guard = sw.StorageGuard(self.root / 'run/storage-pause.json', dirs=(self.disk, self.root / 'absent'),
                                     systemctl=self.systemd, push=lambda kind, title, body: self.pushes.append(kind) or True)

    def test_real_write_probe_reports_success_and_cleans_up(self):
        self.assertIsNone(sw.probe_write(self.disk))
        self.assertEqual(list(self.disk.iterdir()), [])

    def test_probe_ignores_errors_that_are_not_storage_full(self):
        self.assertIsNone(sw.probe_write(self.root / 'absent'))

    def test_full_disk_pauses_background_work_once_and_pushes_once(self):
        self.full = True
        self.assertFalse(self.guard.check(now=100))
        self.assertFalse(self.guard.check(now=115))
        stops = [c for c in self.systemd.calls if c[0] == 'stop']
        freezes = [c for c in self.systemd.calls if c[0] == 'freeze']
        self.assertEqual(stops, [('stop', 'factory-tick.timer')])  # alert/recovery timers stay live
        self.assertEqual(sorted(c[1] for c in freezes),
                         ['app-factory\\x2dlane.slice', 'hermes-worker-kanban-t_1-run-2.scope'])  # never Kevin's turns
        self.assertEqual(self.pushes, ['blocked'])
        saved = json.loads((self.root / 'run/storage-pause.json').read_text())
        self.assertTrue(saved['paused'])
        self.assertIn(str(self.disk), saved['failed'])

    def test_recovery_needs_two_good_probes_then_resumes_exactly_what_it_paused(self):
        self.full = True
        self.guard.check(now=100)
        self.full = False
        self.assertFalse(self.guard.check(now=115))  # one good write is not recovery
        self.assertTrue(self.guard.check(now=130))
        self.assertIn(('start', 'factory-tick.timer'), self.systemd.calls)
        self.assertEqual(sorted(c[1] for c in self.systemd.calls if c[0] == 'thaw'),
                         ['app-factory\\x2dlane.slice', 'hermes-worker-kanban-t_1-run-2.scope'])
        self.assertEqual(self.pushes, ['blocked', 'resolved'])
        self.assertFalse(json.loads((self.root / 'run/storage-pause.json').read_text()).get('paused'))

    def test_pause_survives_daemon_restart(self):
        self.full = True
        self.guard.check(now=100)
        self.full = False
        again = sw.StorageGuard(self.root / 'run/storage-pause.json', dirs=(self.disk,),
                                systemctl=self.systemd, push=lambda *a: True)
        again.check(now=200); again.check(now=215)
        self.assertIn(('start', 'factory-tick.timer'), self.systemd.calls)

    def test_failed_push_retries_at_most_every_ten_minutes(self):
        tries = []
        self.guard.push = lambda kind, title, body: tries.append(kind) and False
        self.full = True
        for t in (100, 115, 130, 701):
            self.guard.check(now=t)
        self.assertEqual(len(tries), 2)

    def test_healthy_disk_touches_nothing(self):
        self.assertTrue(self.guard.check(now=100))
        self.assertEqual([c for c in self.systemd.calls if c[0] in ('stop', 'freeze')], [])
        self.assertEqual(self.pushes, [])


class WatchIntegration(unittest.TestCase):
    def test_blocked_scan_skips_all_database_work(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        with patch.object(sw, 'STORAGE_PROBE_DIRS', ()), patch.object(sw, 'KEVIN_PUSH', root / 'none'):
            watch = sw.Watch(root / 'state', root / 'inventory.json')
        watch.storage.check = lambda now=None: False
        watch.drain_spool = lambda: self.fail('drained spool while storage is blocked')
        watch.discover = lambda: self.fail('discovered while storage is blocked')
        watch.scan()


if __name__ == '__main__':
    unittest.main()
