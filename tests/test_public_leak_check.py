"""The public leak guard: the tracked tree is clean and the hook blocks a tailnet leak."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
CHECK = ROOT / 'scripts/public-leak-check'
SKIP = 'personal-path,mount-path,personal-email'  # same list as .githooks/pre-commit and CI
# Leak-shaped values are assembled at run time so this file itself stays clean.
LEAKS = {'tailnet-ipv4': '100.' + '99.1.2', 'tailnet-name': 'groot.' + 'tailnet-x' + '.ts.net',
         'tailnet-id': 'tail' + 'abc123'}


def check(*args, cwd=ROOT):
    return subprocess.run([sys.executable, '-I', str(CHECK), *args], cwd=cwd, capture_output=True, text=True)


class LeakCheck(unittest.TestCase):
    def test_tracked_tree_has_no_tailnet_or_secret_findings(self):
        result = check('--skip', SKIP)
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertIn(' 0 finding(s)', result.stderr)

    def test_detects_tailnet_values_and_allows_documentation_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            for rule, value in LEAKS.items():
                path = Path(tmp) / f'{rule}.txt'
                path.write_text(f'host = {value}\n')
                result = check('--skip', SKIP, str(path))
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout.strip(), f'{path}:1: {rule}')
                self.assertNotIn(value, result.stdout + result.stderr)
            ok = Path(tmp) / 'ok.txt'
            ok.write_text('a 100.64.0.10 b host.example.ts.net c 100.64.0.0/10 ${GROOT_TAILNET_IP}\n')
            for rule in LEAKS:
                (Path(tmp) / f'{rule}.txt').unlink()
            self.assertEqual(check('--skip', SKIP, tmp).returncode, 0)

    def test_unknown_skip_rule_is_a_usage_error(self):
        self.assertEqual(check('--skip', 'not-a-rule').returncode, 2)

    def test_pre_commit_hook_blocks_a_tailnet_address(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            repo, tools = base / 'repo', base / 'bin'
            (repo / 'scripts').mkdir(parents=True)
            tools.mkdir()
            guard = tools / 'z0-guard'
            guard.write_text('#!/bin/sh\necho guard-ran\n')
            guard.chmod(0o755)
            shutil.copy2(CHECK, repo / 'scripts/public-leak-check')
            subprocess.run(['git', 'init', '-q', str(repo)], check=True)
            (repo / 'unit.service').write_text('ExecStart=srv --host ${GROOT_TAILNET_IP}\n')
            subprocess.run(['git', '-C', str(repo), 'add', '-A'], check=True)
            env = {**os.environ, 'PATH': f'{tools}{os.pathsep}{os.environ["PATH"]}'}
            hook = [str(ROOT / '.githooks/pre-commit')]
            clean = subprocess.run(hook, cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(clean.returncode, 0, clean.stderr)
            self.assertIn('guard-ran', clean.stdout)
            (repo / 'unit.service').write_text(f'ExecStart=srv --host {LEAKS["tailnet-ipv4"]}\n')
            leaked = subprocess.run(hook, cwd=repo, env=env, capture_output=True, text=True)
            self.assertEqual(leaked.returncode, 1)
            self.assertIn('unit.service:1: tailnet-ipv4', leaked.stdout)
            self.assertNotIn('guard-ran', leaked.stdout)

    def test_ci_and_hook_run_the_same_rules(self):
        workflow = (ROOT / '.github/workflows/public-leak-check.yml').read_text()
        self.assertIn(f'scripts/public-leak-check --skip {SKIP}', workflow)
        self.assertIn(f'scripts/public-leak-check --skip {SKIP}', (ROOT / '.githooks/pre-commit').read_text())


if __name__ == '__main__':
    unittest.main()
