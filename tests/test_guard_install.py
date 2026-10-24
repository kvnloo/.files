"""The installed guard remains usable after its source checkout disappears."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


class GuardInstall(unittest.TestCase):
    def test_backend_is_committed_and_survives_checkout_removal(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            backend = base / 'backend'
            backend.mkdir()
            def git(*args):
                return subprocess.run(['git', '-C', str(backend), *args], check=True,
                                      text=True, capture_output=True).stdout.strip()
            git('init', '-b', 'main')
            git('config', 'user.name', 'Test')
            git('config', 'user.email', 'test@example.invalid')
            module = backend / 'src/z0int/fsm/guard.py'
            module.parent.mkdir(parents=True)
            module.write_text("print('committed-backend')\n")
            git('add', '.')
            git('commit', '-m', 'backend')
            head = git('rev-parse', 'HEAD')
            module.write_text("print('uncommitted-backend')\n")
            home = base / 'home'
            home.mkdir()
            env = {**os.environ, 'HOME': str(home), 'Z0INT_BACKEND_REPO': str(backend)}
            env.pop('Z0INT_SRC', None)
            subprocess.run(['bash', str(root / 'scripts/install-z0-guard.sh')],
                           env=env, check=True, capture_output=True, text=True)
            launcher = home / '.local/bin/z0-guard'
            installed = launcher.resolve().parent
            self.assertEqual((installed / 'backend-head').read_text().strip(), head)
            shutil.rmtree(backend)
            result = subprocess.run([str(launcher), 'check'], env=env, check=True,
                                    capture_output=True, text=True)
            self.assertEqual(result.stdout.strip(), 'committed-backend')
            for unit in ('worktree-reaper.service', 'worktree-reaper.timer'):
                self.assertEqual((home / '.config/systemd/user' / unit).resolve().parent, installed)
            self.assertFalse((home / '.config/systemd/user/timers.target.wants').exists())

    def test_stamped_hooks_scan_the_calling_repository(self):
        source = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            stamped = base / 'release'
            stamped.mkdir()
            binary = base / 'bin'
            binary.mkdir()
            guard = binary / 'z0-guard'
            guard.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            guard.chmod(0o755)
            repo = base / 'committing-repo'
            repo.mkdir()
            subprocess.run(['git', 'init', str(repo)], check=True, capture_output=True)
            env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH']}
            for hook in ('pre-commit', 'pre-push'):
                shutil.copy2(source / '.githooks' / hook, stamped / hook)
                result = subprocess.run([str(stamped / hook)], cwd=repo, env=env,
                                        input='refs/heads/main abc refs/heads/main def\n',
                                        check=True, capture_output=True, text=True)
                self.assertEqual(result.stdout.splitlines(), ['phone-caps', '--root', str(repo)])
