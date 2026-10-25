"""Exercise enrollment argv and the real hardening plan's generated kubelet YAML."""
import io
import os
from pathlib import Path
import runpy
import shlex
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))


class WorkerDiskPolicyTests(unittest.TestCase):
    def test_enroll_forwards_disk_gc_and_eviction_policy_to_real_plan_consumer(self):
        namespace = runpy.run_path(str(ROOT / 'scripts/fleet'))
        enroll = namespace['cmd_enroll']
        commands = []
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            key = root / 'controller'
            key.with_suffix('.pub').write_text('ssh-ed25519 fixture-only')
            def run(argv, **kwargs):
                commands.append(argv)
                return subprocess.CompletedProcess(argv, 0)
            sender = SimpleNamespace(stdout=io.BytesIO(), wait=lambda: 0)
            with patch.dict(enroll.__globals__, {
                    'KEY': str(key), 'ssh_cmd': lambda *a, **k: ['ssh', 'root@fixture'],
                    'subprocess': SimpleNamespace(run=run, Popen=lambda *a, **k: sender, PIPE=-1)}):
                self.assertEqual(enroll(SimpleNamespace(node='mbp', port=None)), 0)
            remote = next(shlex.split(argv[-1]) for argv in commands
                          if argv[-1].startswith('bash /opt/dotfiles-k3s/scripts/fleet-harden.sh worker'))
            kubelet = [remote[index + 1] for index, value in enumerate(remote) if value == '--kubelet-arg']
            arguments = dict(value.split('=', 1) for value in kubelet)
            self.assertEqual(arguments['image-gc-high-threshold'], '80')
            self.assertEqual(arguments['image-gc-low-threshold'], '70')
            self.assertIn('nodefs.available<10%', arguments['eviction-hard'].split(','))
            self.assertIn('nodefs.available<12%', arguments['eviction-soft'].split(','))
            self.assertIn('nodefs.available=2m', arguments['eviction-soft-grace-period'].split(','))
            plan = ['bash', str(ROOT / 'scripts/fleet-harden.sh'), 'plan', 'worker']
            for value in kubelet:
                plan += ['--kubelet-arg', value]
            result = subprocess.run(plan, env={**os.environ, 'TMPDIR': str(root)},
                                    capture_output=True, text=True, timeout=30)
            self.assertEqual(result.returncode, 0, result.stderr)
            rendered = list(root.glob('*/etc/rancher/k3s/config.yaml.d/50-fleet.yaml'))
            self.assertEqual(len(rendered), 1)
            document = yaml.safe_load(rendered[0].read_text())
            actual = dict(value.split('=', 1) for value in document['kubelet-arg+'])
            self.assertEqual(actual, arguments)


if __name__ == '__main__':
    unittest.main()
