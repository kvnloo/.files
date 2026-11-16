import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class BurnPaceTests(unittest.TestCase):
    """2026-10-25: codexbar broke and burn-pace reported 'no budget' for 19 h instead of 'unknown'."""

    def run_pace(self, codexbar_stdout):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            (base / 'bin').mkdir()
            fake = base / 'bin/codexbar'
            fake.write_text('#!/bin/sh\ncat <<"JSON"\n' + codexbar_stdout + '\nJSON\n')
            fake.chmod(0o755)
            posture = base / 'src/z0int'
            posture.mkdir(parents=True)
            (posture / '__init__.py').write_text('')
            (posture / 'posture.py').write_text(
                'def pools_from_codexbar(rows, now):\n    return rows\n'
                'def evaluate(pools, now):\n    return {"factory": {"rule": "stub", "pools": len(pools)}}\n')
            # XDG_RUNTIME_DIR too: burn-pace reads the live bws token file there and would probe for real.
            env = dict(os.environ, PATH=f'{base / "bin"}:{os.environ["PATH"]}', HOME=str(base),
                       Z0INT_SRC=str(base / 'src'), XDG_RUNTIME_DIR=str(base))
            for name in [k for k in env if k.startswith(('ANTHROPIC', 'CLAUDE', 'CODEXBAR'))]:
                env.pop(name)
            proc = subprocess.run([sys.executable, str(ROOT / 'scripts/burn-pace'), '--json'],
                                  capture_output=True, text=True, env=env, timeout=60)
            self.assertEqual(proc.returncode, 0, proc.stderr)
            return json.loads(proc.stdout)

    def test_probe_error_is_unknown_not_no_budget(self):
        out = self.run_pace('[{"provider":"cli","error":{"message":"Failed to decode CodexBar config"}}]')
        self.assertEqual(out.get('status'), 'unknown')
        self.assertTrue(out['probe_errors'])
        self.assertEqual(out['lanes'], {})

    def test_empty_output_is_unknown(self):
        out = self.run_pace('')
        self.assertEqual(out.get('status'), 'unknown')

    def test_healthy_probe_has_no_errors(self):
        row = {"provider": "claude", "usage": {"secondary": {"usedPercent": 50, "windowMinutes": 10080,
                                                            "resetsAt": "2099-01-01T00:00:00Z"}}}
        out = self.run_pace(json.dumps([row]))
        # The extra subscriptions (claude2/claude3) have no token in this empty HOME: that stays loud.
        self.assertEqual({e['provider'] for e in out.get('probe_errors', [])} - {'claude2', 'claude3'}, set())
        self.assertIn('claude', out['lanes'])


if __name__ == '__main__':
    unittest.main()
