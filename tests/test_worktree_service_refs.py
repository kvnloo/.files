"""Systemd owns service worktrees even between timer activations."""
import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('service_reaper', str(ROOT / 'scripts/worktree-reap'))
reaper = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(reaper)


class ServiceReferences(unittest.TestCase):
    def test_reference_keeps_idle_or_finished_worktree(self):
        live = dict(head='abc123', linked=False, main=False, locked=False, pid=None,
                    outside=False, dirty=False, unpushed=0, registered=True, idle=22,
                    systemd='supervisor.service')
        for proofs in ([], ['ancestor:main']):
            with self.subTest(proofs=proofs):
                row = dict(head='abc123', worktree='/fixture/supervisor', finished=proofs)
                action, reason = reaper.decide(row, lambda _: live)
                self.assertEqual(action, 'keep')
                self.assertIn('systemd', reason)

    def test_child_reference_and_symlinked_dropin(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            units = root / 'units'
            units.mkdir()
            worktree = root / 'worker'
            release = root / 'release.conf'
            release.write_text(f'[Service]\nEnvironment="PYTHONPATH={worktree}/src"\n')
            dropin = units / 'worker.service.d'
            dropin.mkdir()
            (dropin / '50-backend.conf').symlink_to(release)
            self.assertEqual(reaper.systemd_reference(worktree, roots=[units]),
                             str(dropin / '50-backend.conf'))

    def test_common_prefix_does_not_protect_unrelated_worktree(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            units = root / 'units'
            units.mkdir()
            (units / 'worker.service').write_text(f'WorkingDirectory={root}/worker-other\n')
            self.assertIsNone(reaper.systemd_reference(root / 'worker', roots=[units]))

    def test_unreadable_reference_is_not_ignored(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / 'broken.service').symlink_to(root / 'missing')
            with self.assertRaises(FileNotFoundError):
                reaper.systemd_reference(root / 'worker', roots=[root])

    def test_apply_refuses_before_any_mutation(self):
        row = dict(commondir='/fixture/repo/.git', branch='worker', worktree='/fixture/worker')
        with patch.object(reaper, 'systemd_reference', return_value='worker.service', create=True), \
             patch.object(reaper, 'git') as git, patch.object(reaper, 'snapshot') as snapshot:
            for action in ('idle', 'worktree'):
                result = reaper.apply(row, action)
                self.assertIn('systemd', result['kept'])
            git.assert_not_called()
            snapshot.assert_not_called()

    def test_reference_created_during_snapshot_prevents_removal(self):
        row = dict(commondir='/fixture/repo/.git', branch='worker', worktree='/fixture/worker')
        with patch.object(reaper, 'systemd_reference', side_effect=[None, 'worker.service'], create=True), \
             patch.object(reaper, 'snapshot', return_value='refs/reaped/worker'), \
             patch.object(reaper, 'archive_ignored', return_value=None), \
             patch.object(reaper, 'size_kib', return_value=1), patch.object(reaper, 'git') as git:
            result = reaper.apply(row, 'idle')
            self.assertIn('systemd', result['kept'])
            git.assert_not_called()
