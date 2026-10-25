import importlib.machinery
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader('apply_agent_oom', str(ROOT / 'scripts/apply-agent-oom'))
spec = importlib.util.spec_from_loader(loader.name, loader)
installer = importlib.util.module_from_spec(spec)
loader.exec_module(installer)


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name) / 'home'
        self.source = Path(self.tmp.name) / 'live source'
        for rel in installer.LINKS:
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('tracked source\n')
        self.control = self.home / '.config/systemd/user.control/agent.slice.d'
        self.control.mkdir(parents=True)
        for name in installer.OVERRIDES:
            (self.control / name).write_text('old cap\n')
        (self.control / 'unrelated.conf').write_text('keep\n')

    def response(self, current=1, swap=0, code=0):
        return subprocess.CompletedProcess([], code, f'MemoryCurrent={current}\nMemorySwapCurrent={swap}\n', '')

    def test_gate_edges_and_missing_accounting(self):
        self.assertTrue(installer.safe_usage(f'MemoryCurrent={8 * installer.GIB}\nMemorySwapCurrent={installer.GIB}'))
        for text in ('', 'MemoryCurrent=[not set]\nMemorySwapCurrent=0',
                     'MemoryCurrent=-1\nMemorySwapCurrent=0',
                     f'MemoryCurrent={8 * installer.GIB + 1}\nMemorySwapCurrent=0',
                     f'MemoryCurrent={8 * installer.GIB}\nMemorySwapCurrent={installer.GIB + 1}'):
            self.assertFalse(installer.safe_usage(text))

    @patch.object(installer.subprocess, 'run')
    def test_dry_run_never_mutates(self, run):
        run.return_value = self.response()
        self.assertEqual(installer.install(self.source, self.home, False), 0)
        self.assertEqual(run.call_count, 1)
        self.assertFalse((self.home / '.local').exists())
        self.assertTrue((self.control / installer.OVERRIDES[0]).exists())

    @patch.object(installer.subprocess, 'run')
    def test_unsafe_and_failed_manager_never_link_or_reload(self, run):
        for response in (self.response(9 * installer.GIB), self.response(code=1)):
            run.reset_mock()
            run.return_value = response
            self.assertEqual(installer.install(self.source, self.home, True), 75)
            self.assertEqual(run.call_count, 1)
            self.assertFalse((self.home / '.local').exists())
            self.assertTrue((self.control / installer.OVERRIDES[0]).exists())

    @patch.object(installer.subprocess, 'run')
    def test_apply_backs_up_exact_overrides_links_live_source_no_restarts(self, run):
        run.return_value = self.response()
        self.assertEqual(installer.install(self.source, self.home, True), 0)
        for name in installer.OVERRIDES:
            self.assertFalse((self.control / name).exists())
            saved = list((self.home / '.local/state/agent-oom/backups').glob(f'*/{name}'))
            self.assertEqual(len(saved), 1)
            self.assertEqual(saved[0].read_text(), 'old cap\n')
        self.assertEqual((self.control / 'unrelated.conf').read_text(), 'keep\n')
        for rel, dest in installer.LINKS.items():
            target = (self.home / dest).resolve()
            self.assertTrue(target.is_relative_to(self.home / '.local/lib/files-live'))
            self.assertNotEqual(target, self.source / rel)
            self.assertEqual(target.read_bytes(), (self.source / rel).read_bytes())
        self.assertEqual(run.call_args.args[0], ['systemctl', '--user', 'daemon-reload'])
        self.assertEqual(run.call_count, 2)

    def test_release_survives_source_change_and_rejects_tampering(self):
        release = installer.stamp_release(self.source, self.home)
        old = (release / 'scripts/agent-launch').read_bytes()
        (self.source / 'scripts/agent-launch').write_text('new source')
        self.assertEqual((release / 'scripts/agent-launch').read_bytes(), old)
        self.assertNotEqual(installer.stamp_release(self.source, self.home), release)
        (release / 'scripts/agent-launch').write_text('tampered')
        (self.source / 'scripts/agent-launch').write_bytes(old)
        with self.assertRaisesRegex(ValueError, 'release mismatch'):
            installer.stamp_release(self.source, self.home)


class LauncherTests(unittest.TestCase):
    def launch(self, manager_ok=True, nested=False):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            capture = base / 'argv.json'
            scripts = {
                'grep': f'#!{sys.executable}\nimport sys\nsys.exit({0 if nested else 1})\n',
                'systemctl': f'#!{sys.executable}\nimport sys\nsys.exit({0 if manager_ok else 1})\n',
                'systemd-run': f'#!{sys.executable}\nimport json,os,sys\nopen(os.environ["CAPTURE"],"w").write(json.dumps(sys.argv[1:]))\nsys.exit(23)\n',
                'command with spaces': f'#!{sys.executable}\nimport sys\nsys.exit(99)\n',
            }
            for name, body in scripts.items():
                path = base / name
                path.write_text(body)
                path.chmod(0o755)
            env = dict(os.environ, PATH=f'{base}:{os.environ["PATH"]}', CAPTURE=str(capture))
            env.pop('AGENT_LAUNCH_INLINE', None)
            result = subprocess.run([shutil.which('bash'), str(ROOT / 'scripts/agent-launch'), 'test name',
                                     'command with spaces', 'one two', 'literal;$value'],
                                    env=env, capture_output=True, text=True)
            return result, json.loads(capture.read_text()) if capture.exists() else None, base

    def test_resolved_command_argv_spaces_and_exit_status(self):
        result, argv, base = self.launch()
        self.assertEqual(result.returncode, 23)
        split = argv.index('--')
        self.assertEqual(argv[split + 1:], [str(base / 'command with spaces'), 'one two', 'literal;$value'])
        for prop in ('MemoryHigh=2G', 'MemoryMax=4G', 'MemorySwapMax=512M', 'ManagedOOMPreference=none'):
            self.assertIn('--property=' + prop, argv)
        self.assertIn('--slice=agent.slice', argv)

    def test_unavailable_manager_fails_closed(self):
        result, argv, _ = self.launch(False)
        self.assertNotEqual(result.returncode, 0)
        self.assertIsNone(argv)
        self.assertIn('refusing unbounded launch', result.stderr)

    def test_existing_agent_scope_does_not_nest(self):
        result, argv, _ = self.launch(nested=True)
        self.assertEqual(result.returncode, 99)
        self.assertIsNone(argv)

    def test_hud_and_shell_use_executable_scope_seam(self):
        hud = (ROOT / 'scripts/omp-hud').read_text()
        self.assertIn('--json -- "$HOME/.local/bin/agent-launch" omp $OMP_CMD', hud)
        self.assertIn('-e "$HOME/.local/bin/agent-launch" omp $OMP_CMD', hud)
        self.assertIn('agent-launch\\\\s+omp', hud)
        scopes = (ROOT / 'config/zsh/agent-scopes.zsh').read_text()
        self.assertIn('commands[', scopes)
        self.assertNotIn(' command ${_agent_cli}', scopes)

    def test_source_envelope(self):
        policy = (ROOT / 'config/systemd/user/agent.slice.d/60-oomd-desktop-guard.conf').read_text()
        self.assertIn('MemoryHigh=8G', policy)
        self.assertIn('MemoryMax=10G', policy)
        self.assertNotIn('ManagedOOMPreference=avoid', policy)
        self.assertNotIn('ManagedOOMPreference=prefer', policy)


if __name__ == '__main__':
    unittest.main()
