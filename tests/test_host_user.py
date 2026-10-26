import hashlib
import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('host_user_installer', str(ROOT / 'scripts/apply-agent-oom'))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)


class UserLayerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.source = Path(self.tmp.name) / 'source'
        self.unit = 'config/systemd/user/session.slice.d/50-desktop.conf'
        self.live = self.home / '.config/systemd/user/session.slice.d/50-desktop.conf'
        source_file = self.source / self.unit
        source_file.parent.mkdir(parents=True)
        source_file.write_text('[Slice]\nMemoryHigh=infinity\nCPUWeight=1000\n')
        self.live.parent.mkdir(parents=True)
        self.live.write_text('previous declaration\n')
        self.control = self.home / '.config/systemd/user.control/session.slice.d/50-CPUWeight.conf'
        self.control.parent.mkdir(parents=True)
        self.control.write_text('[Slice]\nCPUWeight=1000\n')
        manifest = self.source / 'config/host/groot.toml'
        manifest.parent.mkdir(parents=True)
        h = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
        manifest.write_text('user_control_cleanup = [{live="~/.config/systemd/user.control/session.slice.d/50-CPUWeight.conf", sha256=' + json.dumps(h(self.control)) + '}]\n'
                            '[[user]]\nlive="~/.config/systemd/user/session.slice.d/50-desktop.conf"\nsource=' + json.dumps(self.unit) + '\nowner="scripts/apply-agent-oom"\nmigration_sha256=' + json.dumps(h(self.live)) + '\n'
                            '[[user]]\nlive="~/.config/environment.d/private.conf"\nsource="never-open-this"\nowner="private-secret-owner"\nsecret="private-exception"\n')
        self.response = subprocess.CompletedProcess([], 0, 'MemoryCurrent=1024\nMemorySwapCurrent=0\n', '')

    @patch.object(installer.subprocess, 'run')
    def test_dry_run_preserves_links_controls_and_private_paths(self, run):
        run.return_value = self.response
        self.assertEqual(installer.install_user_layer(self.source, self.home, False), 0)
        self.assertFalse(self.live.is_symlink())
        self.assertTrue(self.control.exists())
        self.assertFalse((self.home / '.local').exists())
        self.assertEqual(run.call_count, 1)

    @patch.object(installer.subprocess, 'run')
    def test_apply_backs_up_and_stamps_closure_without_restart(self, run):
        run.return_value = self.response
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 0)
        self.assertTrue(self.live.is_symlink())
        self.assertIn('/.local/lib/files-live/', str(self.live.resolve()))
        self.assertFalse(self.control.exists())
        backups = self.home / '.local/state/host-user/backups'
        self.assertEqual(len(list(backups.glob('*/controls/**/50-CPUWeight.conf'))), 1)
        self.assertEqual(len(list(backups.glob('*/home/**/50-desktop.conf'))), 1)
        before = self.live.read_bytes()
        (self.source / self.unit).write_text('mutated checkout')
        self.assertEqual(self.live.read_bytes(), before)
        self.assertEqual(run.call_args.args[0], ['systemctl', '--user', 'daemon-reload'])
        self.assertEqual(run.call_count, 2)

    @patch.object(installer.subprocess, 'run')
    def test_changed_control_or_live_file_fails_before_mutation(self, run):
        run.return_value = self.response
        self.control.write_text('new lease or operator change')
        with self.assertRaisesRegex(ValueError, 'control changed'):
            installer.install_user_layer(self.source, self.home, True)
        self.assertFalse(self.live.is_symlink())
        self.assertEqual(run.call_count, 0)
        self.live.write_text('new operator declaration')
        with self.assertRaisesRegex(ValueError, 'live file changed'):
            installer.install_user_layer(self.source, self.home, True)

    @patch.object(installer.subprocess, 'run')
    def test_insufficient_headroom_fails_closed(self, run):
        run.return_value = subprocess.CompletedProcess([], 0, 'MemoryCurrent=3221225472\nMemorySwapCurrent=0\n', '')
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 75)
        self.assertTrue(self.control.exists())
        self.assertFalse(self.live.is_symlink())

    @patch.object(installer.subprocess, 'run')
    def test_mask_remains_dev_null_and_second_apply_is_safe(self, run):
        run.return_value = self.response
        manifest = self.source / 'config/host/groot.toml'
        (self.source / 'mask').write_text('')
        with manifest.open('a') as f:
            f.write('[[user]]\nlive="~/.config/systemd/user/dunst.service"\nsource="mask"\nowner="scripts/apply-agent-oom"\nmask=true\n')
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 0)
        mask = self.home / '.config/systemd/user/dunst.service'
        self.assertTrue(mask.is_symlink())
        self.assertEqual(mask.resolve(), Path('/dev/null'))
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 0)
        self.assertEqual(mask.resolve(), Path('/dev/null'))


    @patch.object(installer.subprocess, 'run')
    def test_upgrade_accepts_intact_previous_stamp_but_rejects_tampering(self, run):
        run.return_value = self.response
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 0)
        old_target = self.live.resolve()
        (self.source / self.unit).write_text('next tracked declaration')
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 0)
        self.assertNotEqual(self.live.resolve(), old_target)
        self.assertEqual(self.live.read_text(), 'next tracked declaration')
        self.live.resolve().write_text('operator changed a stamped file')
        (self.source / self.unit).write_text('third tracked declaration')
        with self.assertRaisesRegex(ValueError, 'live file changed'):
            installer.install_user_layer(self.source, self.home, True)

    @patch.object(installer.subprocess, 'run')
    def test_explicit_obsolete_file_is_backed_up_and_removed(self, run):
        run.return_value = self.response
        obsolete = self.home / '.config/systemd/user/obsolete.service'
        obsolete.write_text('retired declaration')
        digest = hashlib.sha256(obsolete.read_bytes()).hexdigest()
        manifest = self.source / 'config/host/groot.toml'
        manifest.write_text('user_retired_files=[{live=\"~/.config/systemd/user/obsolete.service\",sha256=' +
                            json.dumps(digest) + '}]' + chr(10) + manifest.read_text())
        self.assertEqual(installer.install_user_layer(self.source, self.home, True), 0)
        self.assertFalse(obsolete.exists())
        saved = list((self.home / '.local/state/host-user/backups').glob('*/retired/**/obsolete.service'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_text(), 'retired declaration')


if __name__ == '__main__':
    unittest.main()
