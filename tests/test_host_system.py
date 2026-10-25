"""Offline render/diff/idempotence and separate oomd-stage contract."""
import contextlib
import importlib.machinery
import importlib.util
import io
from pathlib import Path
import tempfile
import unittest

SOURCE = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('host_system', str(SOURCE / 'scripts/apply-host-system'))
spec = importlib.util.spec_from_loader(loader.name, loader)
host = importlib.util.module_from_spec(spec)
loader.exec_module(host)


class HostSystemTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def run_install(self, apply=False, oomd=False):
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            result = host.install(SOURCE, self.root, apply, oomd)
        self.assertEqual(result, 0)
        return stream.getvalue()

    def test_dry_run_does_not_create_any_files(self):
        output = self.run_install()
        self.assertIn('WOULD INSTALL /etc/sysctl.d/99-groot.conf', output)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_apply_render_backup_and_idempotence(self):
        old = self.root / 'etc/sysctl.d/99-performance-tuning.conf'
        old.parent.mkdir(parents=True)
        old.write_text('vm.dirty_ratio = 20\n')
        output = self.run_install(True)
        self.assertIn('retired=1', output)
        self.assertFalse(old.exists())
        for e in host.load(SOURCE, False):
            self.assertEqual((self.root / e['live'].lstrip('/')).read_bytes(), e['payload'])
        backups = list((self.root / 'var/backups/files-host').iterdir())
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / 'etc/sysctl.d/99-performance-tuning.conf').read_text(), 'vm.dirty_ratio = 20\n')
        output = self.run_install(True)
        self.assertIn('changed=0 retired=0', output)
        self.assertEqual(list((self.root / 'var/backups/files-host').iterdir()), backups)
        self.assertFalse((self.root / 'etc/systemd/system/system.slice.d/99-host-oomd.conf').exists())

    def test_oomd_stage_is_separate_and_never_installs_memory_policy(self):
        output = self.run_install(True, True)
        self.assertIn('stage=oomd', output)
        self.assertFalse((self.root / 'etc/sysctl.d').exists())
        entries = host.load(SOURCE, True)
        self.assertEqual(len(entries), 5)
        for e in entries:
            text = (self.root / e['live'].lstrip('/')).read_text()
            self.assertIn('ManagedOOMSwap=auto', text)
            self.assertIn('ManagedOOMMemoryPressure=auto', text)
            self.assertNotIn('=kill', text)
        self.assertIn('changed=0 retired=0', self.run_install(True, True))

    def test_symlink_target_backed_up_not_followed(self):
        victim = self.root / 'do-not-write'
        victim.write_text('original')
        p = self.root / 'etc/sysctl.d/99-groot.conf'
        p.parent.mkdir(parents=True)
        p.symlink_to(victim)
        self.run_install(True)
        self.assertEqual(victim.read_text(), 'original')
        self.assertFalse(p.is_symlink())

    def test_escaping_parent_rejected_before_any_write(self):
        with tempfile.TemporaryDirectory() as outside:
            (self.root / 'etc').symlink_to(outside)
            with self.assertRaisesRegex(ValueError, 'escapes root'):
                self.run_install(True)
            self.assertEqual(list(Path(outside).iterdir()), [])

    def test_audit_never_prints_env_or_credential_values(self):
        p = self.root / 'etc/systemd/system/k3s.service.env'
        p.parent.mkdir(parents=True)
        p.write_text('SECRET_VALUE=must-not-be-printed\n')
        boot = self.root / 'boot'
        boot.mkdir()
        (boot / 'limine.conf').write_text('private boot config')
        with contextlib.redirect_stdout(io.StringIO()) as stream:
            self.assertEqual(host.audit(self.root), 0)
        output = stream.getvalue()
        self.assertIn('k3s.service.env', output)
        self.assertIn('sha256', output)
        self.assertNotIn('must-not-be-printed', output)
        self.assertNotIn('private boot config', output)
        self.assertEqual(p.read_text(), 'SECRET_VALUE=must-not-be-printed\n')

    def test_policy_has_no_dead_scheduler_sysctls_or_ratio_storms(self):
        text = (SOURCE / 'config/host/etc/sysctl.d/99-groot.conf').read_text()
        self.assertNotIn('vm.dirty_ratio', text)
        self.assertNotIn('sched_latency_ns', text)
        self.assertIn('vm.dirty_bytes = 268435456', text)
        self.assertIn('vm.dirty_background_bytes = 67108864', text)
        zram = (SOURCE / 'config/host/etc/systemd/zram-generator.conf').read_text()
        self.assertIn('zram-size = ram / 8', zram)
        self.assertIn('zram-resident-limit = ram / 8', zram)
        self.assertNotIn('oomd stops', zram)



class EarlyoomSelectionTests(unittest.TestCase):
    def test_exact_harness_avoid_and_no_worker_preference(self):
        import re
        text = (SOURCE / 'config/host/etc/default/earlyoom').read_text()
        args = host.earlyoom_args(text)
        self.assertNotIn('--prefer', args)
        self.assertEqual(args[args.index('-m') + 1], '5')
        self.assertEqual(args[args.index('-s') + 1], '65')
        pattern = args[args.index('--avoid') + 1]
        self.assertTrue(pattern.startswith('^(') and pattern.endswith(')$'))
        for comm in ('omp', 'hermes', 'tern', 'node-MainThread', 'claude', 'codex',
                     'omp daemon brok', 'sway', 'qs', 'Hyprland', 'tmux: server',
                     'pipewire', 'sshd'):
            with self.subTest(comm=comm):
                self.assertIsNotNone(re.fullmatch(pattern, comm))
        for comm in ('python', 'python3', 'node', 'llama-server', 'cargo',
                     'cc1plus', 'omp-worker', 'not-hermes', 'codex-tool'):
            with self.subTest(comm=comm):
                self.assertIsNone(re.fullmatch(pattern, comm))
if __name__ == '__main__':
    unittest.main()
