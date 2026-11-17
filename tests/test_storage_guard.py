"""Storage hold contracts (11-16 incident): a unit dying on a refused write pauses work at once,
with no polling. Execute on MBP, never on the desktop."""
import errno
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('service_watch', ROOT / 'scripts/service-watch.py')
assert spec and spec.loader
sw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(sw)


class FakeSystemd:
    def __init__(self, timers=(), scopes=(), slices=(), transient=()):
        self.timers, self.scopes, self.slices = list(timers), list(scopes), list(slices)
        self.transient = set(transient)
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
        elif argv[:2] == ('show', '--property=Id,Transient'):
            out = '\n\n'.join('Id=%s\nTransient=%s' % (u, 'yes' if u in self.transient else 'no') for u in argv[2:])
        return 0, out


class Hold(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(); self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.disk = self.root / 'disk'; self.disk.mkdir()
        self.logs = {'factory-tick.service': "OSError: [Errno 28] No space left on device: 'state.json'",
                     'flaky.service': 'ConnectionResetError: peer reset'}
        self.systemd = FakeSystemd(timers=['factory-tick.timer', 'service-watch-heartbeat.timer', 'run-r1.timer'],
                                   transient=['run-r1.timer'],
                                   scopes=['hermes-worker-kanban-t_1-run-2.scope', 'hermes-turn-local-x.scope'],
                                   slices=['app-factory\\x2dlane.slice', 'session.slice'])
        self.pushes, self.sleeps = [], []
        self.full = []
        real = sw.probe_write
        probe = patch.object(sw, 'probe_write', lambda d, size=0: self.full.pop(0) if self.full else real(d, 4096))
        probe.start(); self.addCleanup(probe.stop)
        self.hold = sw.StorageHold(self.root / 'run/hold.json', dirs=(self.disk,), systemctl=self.systemd,
                                   push=lambda t, b: self.pushes.append(t) or True,
                                   journal=lambda unit: self.logs.get(unit, ''), sleep=self.sleeps.append)

    def test_real_write_probe_succeeds_and_cleans_up(self):
        self.assertIsNone(sw.probe_write(self.disk, 4096))
        self.assertEqual(list(self.disk.iterdir()), [])

    def test_kernel_enospc_is_reported(self):
        link = self.disk / ('.service-watch-probe-%d' % __import__('os').getpid())
        link.symlink_to('/dev/full')
        self.assertEqual(sw.probe_write(self.disk, 4096), errno.ENOSPC)

    def test_unrelated_failure_touches_nothing(self):
        self.assertFalse(self.hold.on_failure('flaky.service'))
        self.assertEqual([c for c in self.systemd.calls if c[0] in ('stop', 'freeze', 'start')], [])

    def test_write_failure_pauses_at_once_without_pushing_inside_the_hook(self):
        self.assertTrue(self.hold.on_failure('factory-tick.service', now=100))
        self.assertEqual([c for c in self.systemd.calls if c[0] == 'stop'], [('stop', 'factory-tick.timer')])
        self.assertEqual(sorted(c[1] for c in self.systemd.calls if c[0] == 'freeze'),
                         ['app-factory\\x2dlane.slice', 'hermes-worker-kanban-t_1-run-2.scope'])  # never Kevin's turns
        self.assertIn(('start', '--no-block', 'service-watch-storage-wait.service'), self.systemd.calls)
        self.assertEqual(self.pushes, [])  # hook has a 15 s budget; the waiter pushes
        self.assertTrue(json.loads((self.root / 'run/hold.json').read_text())['held'])

    def test_second_failure_while_held_does_not_repause(self):
        self.hold.on_failure('factory-tick.service')
        n = len(self.systemd.calls)
        self.assertFalse(self.hold.on_failure('factory-tick.service'))
        self.assertEqual(len(self.systemd.calls), n)

    def test_waiter_pushes_then_resumes_exactly_the_paused_set_after_three_clean_writes(self):
        self.hold.on_failure('factory-tick.service', now=100)
        self.full = [errno.ENOSPC, None, None, errno.ENOSPC]  # flapping disk resets the streak
        self.assertEqual(self.hold.wait(interval=30, needed=3), 0)
        self.assertEqual(len(self.sleeps), 7)
        self.assertIn(('start', 'factory-tick.timer'), self.systemd.calls)
        self.assertNotIn(('start', 'run-r1.timer'), self.systemd.calls)
        self.assertEqual(sorted(c[1] for c in self.systemd.calls if c[0] == 'thaw'),
                         ['app-factory\\x2dlane.slice', 'hermes-worker-kanban-t_1-run-2.scope'])
        self.assertEqual([p.split(':')[0] for p in self.pushes], ['CRITICAL', 'Disk accepts writes again - work resumed'])
        self.assertFalse(json.loads((self.root / 'run/hold.json').read_text())['held'])

    def test_waiter_without_hold_exits_immediately(self):
        self.assertEqual(self.hold.wait(), 0)
        self.assertEqual(self.sleeps, [])


class NoPolling(unittest.TestCase):
    def test_scan_does_no_storage_io(self):
        self.assertNotIn('probe_write', Path(ROOT / 'scripts/service-watch.py').read_text().split('def scan(self)')[1].split('\n    def ')[0])

    def test_failure_hook_runs_storage_hold(self):
        unit = (ROOT / 'config/systemd/user/service-watch-failure@.service').read_text()
        self.assertIn('ExecStart=-%h/.local/bin/service-watch storage-hold %n', unit)


if __name__ == '__main__':
    unittest.main()
