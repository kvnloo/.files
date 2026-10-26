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
        for rel in (*installer.LINKS, *installer.CLOSURE):
            path = self.source / rel
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('tracked source\n')
        self.control = self.home / '.config/systemd/user.control/agent.slice.d'
        self.control.mkdir(parents=True)
        for name in installer.OVERRIDES:
            (self.control / name).write_text('old cap\n')
        (self.control / 'unrelated.conf').write_text('keep\n')

    def test_new_groot_stamp_uses_bulk_bytes_and_home_alias(self):
        bulk = Path(self.tmp.name) / 'bulk'
        with patch.object(installer, 'GROOT_HOME', self.home), patch.object(installer, 'BULK_RELEASES', bulk), patch.object(installer.os.path, 'ismount', return_value=True):
            release = installer.stamp_release(self.source, self.home)
        self.assertEqual(release.parent, bulk)
        alias = self.home / '.local/lib/files-live' / release.name
        self.assertTrue(alias.is_symlink())
        self.assertEqual(alias.resolve(), release)

    def test_intact_prior_bulk_stamp_is_upgradeable(self):
        bulk = Path(self.tmp.name) / 'bulk'
        relative = Path('scripts/agent-launch')
        with patch.object(installer, 'GROOT_HOME', self.home), patch.object(installer, 'BULK_RELEASES', bulk), patch.object(installer.os.path, 'ismount', return_value=True):
            release = installer.stamp_release(self.source, self.home)
            live = self.home / 'probe'
            live.symlink_to(release / relative)
            (self.source / relative).write_text('new source')
            replacement = installer.stamp_release(self.source, self.home)
            self.assertNotEqual(replacement, release)
            self.assertTrue(installer.intact_installed_release(live, self.home, relative, {}))

    def test_interpreter_bytecode_cache_is_not_tampering(self):
        # Running a stamped Python helper writes scripts/__pycache__/*.pyc into the release;
        # that generated cache must not block every later upgrade, but any other byte still does.
        bulk = Path(self.tmp.name) / 'bulk'
        relative = Path('scripts/agent-launch')
        with patch.object(installer, 'GROOT_HOME', self.home), patch.object(installer, 'BULK_RELEASES', bulk), patch.object(installer.os.path, 'ismount', return_value=True):
            release = installer.stamp_release(self.source, self.home)
            live = self.home / 'probe'
            live.symlink_to(release / relative)
            cache = release / 'scripts/__pycache__'
            cache.mkdir()
            (cache / 'workspace_flow.cpython-314.pyc').write_bytes(b'\x00bytecode')
            self.assertTrue(installer.intact_installed_release(live, self.home, relative, {}))
            (cache / 'planted.py').write_text('not bytecode')
            self.assertFalse(installer.intact_installed_release(live, self.home, relative, {}))

    def test_tampered_bulk_stamp_cannot_authorize_upgrade(self):
        bulk = Path(self.tmp.name) / 'bulk'
        relative = Path('scripts/agent-launch')
        with patch.object(installer, 'GROOT_HOME', self.home), patch.object(installer, 'BULK_RELEASES', bulk), patch.object(installer.os.path, 'ismount', return_value=True):
            release = installer.stamp_release(self.source, self.home)
            live = self.home / 'probe'
            live.symlink_to(release / relative)
            (release / relative).write_text('tampered')
            self.assertFalse(installer.intact_installed_release(live, self.home, relative, {}))

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
        calls = [c.args[0] for c in run.call_args_list]
        self.assertEqual(calls[2:], [['systemctl', '--user', 'daemon-reload'],
                                     ['systemctl', '--user', 'enable', installer.GUARD],
                                     ['systemctl', '--user', 'restart', installer.GUARD]])
        # The policy module ships inside the stamped release next to the linked helpers.
        guard = (self.home / installer.LINKS['scripts/agent-oom-guard']).resolve()
        for rel in installer.CLOSURE:
            self.assertEqual((guard.parent.parent / rel).read_bytes(), (self.source / rel).read_bytes())

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
        for prop in ('MemoryHigh=infinity', 'MemoryMax=6G', 'MemorySwapMax=1G', 'ManagedOOMPreference=none',
                     'OOMPolicy=continue'):
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

    def test_only_the_guard_writes_oom_scores(self):
        # Two writers fought before: agent-launch raised every process but its own PID
        # (the Hermes TUI renderer included) while the classifier raised others.
        writers = []
        for path in sorted((ROOT / 'scripts').iterdir()):
            if not path.is_file() or path.name in {'agent_oom_policy.py', 'agent-oom-guard'}:
                continue
            try:
                text = path.read_text()
            except UnicodeDecodeError:
                continue
            code = [line for line in text.splitlines()
                    if 'oom_score_adj' in line and not line.lstrip().startswith('#')]
            if code:
                writers.append((path.name, code[:2]))
        self.assertEqual(writers, [])

    def test_every_user_service_and_scope_survives_one_oom_kill(self):
        for rel, section in (('service.d', 'Service'), ('scope.d', 'Scope')):
            text = (ROOT / 'config/systemd/user' / rel / '50-oom-continue.conf').read_text()
            self.assertIn(f'[{section}]\nOOMPolicy=continue', text)
            self.assertIn(f'config/systemd/user/{rel}/50-oom-continue.conf', installer.LINKS)

    def test_source_envelope(self):
        policy = (ROOT / 'config/systemd/user/agent.slice.d/60-oomd-desktop-guard.conf').read_text()
        self.assertIn('MemoryHigh=infinity', policy)
        self.assertIn('MemoryMax=10G', policy)
        # oomd kills whole cgroups, i.e. the harness with all its subagents.
        self.assertIn('ManagedOOMMemoryPressure=auto', policy)
        self.assertNotIn('ManagedOOMMemoryPressure=kill', policy)
        self.assertNotIn('ManagedOOMPreference=avoid', policy)
        self.assertNotIn('ManagedOOMPreference=prefer', policy)


if __name__ == '__main__':
    unittest.main()
