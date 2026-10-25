import importlib.machinery
import importlib.util
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('apply_ctx_policy', str(ROOT / 'scripts/apply-ctx-policy'))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)


class CtxPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        root = Path(self.temporary.name)
        self.home = root / 'home'
        self.source = root / 'source'
        source = self.source / installer.RELATIVE
        source.parent.mkdir(parents=True)
        source.write_bytes((ROOT / installer.RELATIVE).read_bytes())
        self.control = self.home / '.config/systemd/user.control/ctx.service.d'
        self.control.mkdir(parents=True)
        for name in installer.OVERRIDES:
            (self.control / name).write_text('old property\n')
        (self.control / 'unrelated.conf').write_text('keep\n')
        self.unit = self.home / '.config/systemd/user/ctx.service'
        self.unit.parent.mkdir(parents=True)
        self.unit.write_text('generated unit\n')

    @patch.object(installer.subprocess, 'run')
    def test_dry_run_does_not_change_live_state(self, run):
        self.assertEqual(installer.install(self.source, self.home, False), 0)
        run.assert_not_called()
        self.assertFalse((self.home / '.local').exists())
        self.assertTrue(all((self.control / name).exists() for name in installer.OVERRIDES))

    @patch.object(installer.subprocess, 'run')
    def test_apply_preserves_generated_unit_and_unowned_overrides(self, run):
        self.assertEqual(installer.install(self.source, self.home, True), 0)
        self.assertEqual(self.unit.read_text(), 'generated unit\n')
        self.assertEqual((self.control / 'unrelated.conf').read_text(), 'keep\n')
        for name in installer.OVERRIDES:
            self.assertFalse((self.control / name).exists())
            saved = list((self.home / '.local/state/ctx-policy/backups').glob(f'*/user.control/{name}'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_text(), 'old property\n')
        target = (self.home / installer.DESTINATION).resolve()
        self.assertTrue(target.is_relative_to(self.home / '.local/lib/files-live'))
        self.assertEqual(target.read_bytes(), (self.source / installer.RELATIVE).read_bytes())
        run.assert_called_once_with(['systemctl', '--user', 'daemon-reload'], check=True)

    def test_stamp_is_immutable_and_rejects_tampering(self):
        release = installer.stamp_release(self.source, self.home)
        before = (release / installer.RELATIVE).read_bytes()
        (self.source / installer.RELATIVE).write_text('changed\n')
        self.assertEqual((release / installer.RELATIVE).read_bytes(), before)
        self.assertNotEqual(installer.stamp_release(self.source, self.home), release)
        (release / installer.RELATIVE).write_text('tampered\n')
        (self.source / installer.RELATIVE).write_bytes(before)
        with self.assertRaisesRegex(ValueError, 'release mismatch'):
            installer.stamp_release(self.source, self.home)

    def test_policy_has_hard_budget_without_execstart_override(self):
        policy = (ROOT / installer.RELATIVE).read_text()
        for value in ['MemoryHigh=infinity', 'MemoryMax=5G', 'MemorySwapMax=2G',
                      'OOMPolicy=stop', 'Restart=on-failure', 'StartLimitBurst=3']:
            self.assertIn(value, policy)
        self.assertNotIn('ExecStart=', policy)


if __name__ == '__main__':
    unittest.main()
