import importlib.machinery
import importlib.util
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('apply_ctx_stopgap', str(ROOT / 'scripts/apply-ctx-stopgap'))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)


class StopgapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.home = root / 'home'
        self.store = root / 'data-releases'
        self.source = root / 'source'
        for relative in [installer.RELATIVE, 'scripts/apply-ctx-policy']:
            target = self.source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / relative, target)
        self.binary = root / 'built-ctx'
        self.binary.write_bytes(b'owned executable fixture\n')
        self.binary.chmod(0o755)
        self.managed = self.home / '.local/bin/ctx'
        self.managed.parent.mkdir(parents=True)
        self.managed.write_bytes(b'original managed binary\n')

    @patch.object(installer.subprocess, 'run')
    def test_stage_has_no_live_side_effects(self, run):
        self.assertEqual(installer.install(self.source, self.home, self.binary, False, self.store), 0)
        run.assert_not_called()
        self.assertFalse((self.home / '.local/lib').exists())
        self.assertFalse((self.home / '.config').exists())

    @patch.object(installer.subprocess, 'run')
    def test_install_stamps_binary_backs_up_managed_and_never_restarts(self, run):
        self.assertEqual(installer.install(self.source, self.home, self.binary, True, self.store), 0)
        sha, binary = installer.release_target(self.source, self.home)
        self.assertEqual(len(sha), 40)
        self.assertEqual(binary.read_bytes(), self.binary.read_bytes())
        self.assertTrue(binary.parent.is_symlink())
        self.assertEqual(binary.resolve(), self.store / sha / 'ctx')
        self.assertEqual(self.managed.read_bytes(), b'original managed binary\n')
        saved = list((self.store / 'backups').glob('*/ctx.managed'))
        self.assertEqual(len(saved), 1)
        self.assertEqual(saved[0].read_bytes(), self.managed.read_bytes())
        policy = (self.home / installer.DESTINATION).resolve()
        self.assertTrue(policy.is_relative_to(self.home / '.local/lib/files-live'))
        self.assertEqual(policy.read_bytes(), (self.source / installer.RELATIVE).read_bytes())
        run.assert_called_once_with(['systemctl', '--user', 'daemon-reload'], check=True)

    @patch.object(installer.subprocess, 'run')
    def test_immutable_release_collision_fails_before_live_changes(self, run):
        sha, _ = installer.release_target(self.source, self.home)
        target = self.store / sha / 'ctx'
        target.parent.mkdir(parents=True)
        target.write_bytes(b'wrong binary')
        with self.assertRaisesRegex(ValueError, 'release mismatch'):
            installer.install(self.source, self.home, self.binary, True, self.store)
        run.assert_not_called()
        self.assertFalse((self.home / installer.DESTINATION).exists())


if __name__ == '__main__':
    unittest.main()
