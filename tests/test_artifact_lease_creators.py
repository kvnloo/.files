"""Creator contract tests; all remote shell publication runs in temporary dirs."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).resolve().parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
import artifact_lease


class CreatorTests(unittest.TestCase):
    def test_local_contract_and_no_renewal(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(artifact_lease.time, 'time', return_value=1234567890):
                self.assertTrue(artifact_lease.create(directory, 'job-1', 'groot', 'fleet-fetch', ['logs/result.json']))
            sidecar = Path(directory) / '.artifact-lease.json'
            first = sidecar.read_bytes()
            value = json.loads(first)
            self.assertEqual(value, dict(schema='z0.artifact-lease.v1', owner='job-1', node='groot',
                                         path=str(Path(directory).resolve()), kind='fleet-fetch',
                                         created_at=1234567890, ttl=604800, keep_receipts=['logs/result.json']))
            self.assertFalse(artifact_lease.create(directory, 'different-job', 'mbp', 'other'))
            self.assertEqual(first, sidecar.read_bytes())
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['.artifact-lease.json'])

    def test_unknown_existing_lease_is_not_replaced(self):
        with tempfile.TemporaryDirectory() as directory:
            sidecar = Path(directory) / '.artifact-lease.json'
            sidecar.write_text('unknown-format')
            self.assertFalse(artifact_lease.create(directory, 'job', 'groot', 'fleet-fetch'))
            self.assertEqual(sidecar.read_text(), 'unknown-format')

    def test_unsafe_receipts_rejected_before_publication(self):
        for receipt in ('../private', '/absolute', 'a/../../escape', 'a\\b', ''):
            with self.subTest(receipt=receipt), tempfile.TemporaryDirectory() as directory:
                with self.assertRaises(ValueError):
                    artifact_lease.create(directory, 'job', 'groot', 'fleet-fetch', [receipt])
                self.assertEqual(list(Path(directory).iterdir()), [])

    def test_portable_shell_publishes_without_replacement(self):
        with tempfile.TemporaryDirectory(prefix='lease space ') as directory:
            command = artifact_lease.shell_create(artifact_lease.shlex.quote(directory), 'job', 's22', 'fleet-adb')
            subprocess.run(['sh', '-c', command], check=True)
            sidecar = Path(directory) / '.artifact-lease.json'
            first = sidecar.read_bytes()
            self.assertEqual(json.loads(first)['path'], str(Path(directory).resolve()))
            subprocess.run(['sh', '-c', artifact_lease.shell_create(artifact_lease.shlex.quote(directory), 'other', 's25', 'other')], check=True)
            self.assertEqual(sidecar.read_bytes(), first)

    def test_terminal_receipt_contains_actual_return_code(self):
        with tempfile.TemporaryDirectory() as directory:
            result = subprocess.run(['sh', '-c', artifact_lease.terminal_command('(exit 17)', artifact_lease.shlex.quote(directory))])
            self.assertEqual(result.returncode, 17)
            self.assertEqual((Path(directory) / 'exit').read_text(), '17\n')
            self.assertEqual([p.name for p in Path(directory).iterdir()], ['exit'])

    def test_worktree_wrapper_requires_owner_and_leases_after_git(self):
        from importlib.machinery import SourceFileLoader
        loader = SourceFileLoader('agent_worktree_test', str(SCRIPTS / 'agent-worktree'))
        spec = importlib.util.spec_from_loader(loader.name, loader)
        wrapper = importlib.util.module_from_spec(spec)
        loader.exec_module(wrapper)
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(sys, 'argv', ['agent-worktree', '--owner', 'job', '--node', 'mbp', directory]), patch.object(wrapper.subprocess, 'run') as git:
                wrapper.main()
            git.assert_called_once_with(['git', 'worktree', 'add', '--', directory, 'HEAD'], check=True)
            self.assertEqual(json.loads((Path(directory) / '.artifact-lease.json').read_text())['owner'], 'job')


if __name__ == '__main__':
    unittest.main()
