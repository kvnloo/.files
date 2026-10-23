"""Behavior tests for public-source transfer, output retrieval and routing."""
import base64
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("fleet_boat_under_test", str(ROOT / "scripts/fleet-boat"))
spec = importlib.util.spec_from_loader(loader.name, loader)
adapter = importlib.util.module_from_spec(spec)
loader.exec_module(adapter)


class BoatTransferTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "repo"
        self.src.mkdir()
        subprocess.run(["git", "init", "-q", str(self.src)], check=True)
        (self.src / ".gitignore").write_text("ignored\n")
        (self.src / "public.py").write_text("print('public')\n")
        (self.src / "ignored").write_text("must stay local")
        self.archive = self.root / "source.tar.gz"

    def test_archive_ships_reviewed_git_files_and_exact_input(self):
        artifact = self.root / "artifact"
        artifact.write_bytes(b"exact artifact")
        adapter.pack_source(self.src, self.archive, [str(artifact) + ":data/input"])
        with tarfile.open(self.archive) as tar:
            self.assertEqual(set(tar.getnames()), {"src/.gitignore", "src/public.py", "src/data/input"})
            self.assertEqual(tar.extractfile("src/data/input").read(), b"exact artifact")

    def test_environment_files_refuse_shipping(self):
        (self.src / ".env").write_text("not a real key")
        with self.assertRaisesRegex(ValueError, "environment file"):
            adapter.pack_source(self.src, self.archive, [])

    def test_input_cannot_escape_source(self):
        artifact = self.root / "artifact"
        artifact.write_text("x")
        with self.assertRaises(ValueError):
            adapter.pack_source(self.src, self.archive, [str(artifact) + ":../../escape"])

    def test_no_src_does_not_require_git(self):
        adapter.pack_source(self.root, self.archive, [], no_src=True)
        with tarfile.open(self.archive) as tar:
            self.assertEqual(tar.getnames(), [])

    def callback(self, output_name="src/result.txt"):
        adapter.pack_source(self.src, self.archive, [])
        dest = self.root / "outputs"
        dest.mkdir()
        manifest = self.root / "manifest.json"
        receipt = self.root / "receipt.json"
        manifest.write_text(json.dumps(dict(archive=str(self.archive), command=["sh", "-c", "exit 17"],
            timeout=30, fetch=["src/result.txt"], dest=str(dest), receipt=str(receipt))))
        bundle = io.BytesIO()
        with tarfile.open(fileobj=bundle, mode="w:gz") as tar:
            member = tarfile.TarInfo(output_name)
            member.size = 6
            tar.addfile(member, io.BytesIO(b"result"))
        def api(path, method="GET", body=None):
            if path.endswith("/files"):
                with tarfile.open(fileobj=io.BytesIO(base64.b64decode(body["content"]))) as tar:
                    self.assertEqual(tar.extractfile("src/public.py").read(), b"print('public')\n")
                return {}
            return {"exitCode": 17, "stdout": "job output\n", "stderr": ""}
        def remote(sid, command):
            return base64.b64encode(bundle.getvalue()).decode() if "base64" in command else ""
        with patch.dict(os.environ, BOAT_SANDBOX_ID="bx_23456789"), \
                patch.object(adapter.boat, "api", side_effect=api), \
                patch.object(adapter.boat, "remote", side_effect=remote):
            rc = adapter.callback(manifest)
        return rc, dest, receipt

    def test_callback_fetches_outputs_and_preserves_failure_status(self):
        rc, dest, receipt = self.callback()
        self.assertEqual(rc, 17)
        self.assertEqual((dest / "src/result.txt").read_text(), "result")
        self.assertEqual(json.loads(receipt.read_text())["exit_code"], 17)

    def test_fetched_archive_cannot_escape_destination(self):
        with self.assertRaises(tarfile.FilterError):
            self.callback("../../escaped")
        self.assertFalse((self.root / "escaped").exists())

    def test_budget_hold_is_preadmission_and_does_not_create(self):
        args = SimpleNamespace(keep=False, mem_mb=512, cpus=None, timeout=30, fetch=[])
        with patch.object(adapter.boat, "check_capacity", side_effect=adapter.boat.BoatError("budget")), \
                patch.object(adapter.subprocess, "Popen") as create:
            self.assertEqual(adapter.run(args), 75)
        create.assert_not_called()

    def test_locked_creation_race_is_retryable_without_allocated_job(self):
        import contextlib
        denied = self.root / "denied.py"
        denied.write_text("raise SystemExit(75)\n")
        args = SimpleNamespace(keep=False, mem_mb=512, cpus=None, timeout=30,
            fetch=[], src=str(self.src), input=[], no_src=False, command=["true"])
        errors = io.StringIO()
        with patch.object(adapter.boat, "check_capacity"), \
                patch.dict(os.environ, OMP_BOAT=str(denied), FLEET_STATE=str(self.root / "state")), \
                contextlib.redirect_stderr(errors):
            self.assertEqual(adapter.run(args), 75)
        self.assertNotIn("fleet: job ", errors.getvalue())

    def test_resource_request_cannot_exceed_trial_shape(self):
        args = SimpleNamespace(keep=False, mem_mb=8000, cpus=None)
        with self.assertRaisesRegex(ValueError, "7168"):
            adapter.run(args)


class BuildRoutingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.build = self.root / "fleet-build"
        shutil.copy2(ROOT / "scripts/fleet-build", self.build)
        fake = self.root / "fleet"
        fake.write_text('''#!/usr/bin/env python3
import json,os,sys
from pathlib import Path
with Path(os.environ['CALLS']).open('a') as f: f.write(json.dumps(sys.argv[1:])+'\\n')
if '--node' in sys.argv and sys.argv[sys.argv.index('--node')+1]=='boat': sys.exit(0)
if os.environ.get('ALLOCATED'): print('fleet: job abc-123 -> mbp',file=sys.stderr)
sys.exit(75)
''')
        fake.chmod(0o700)
        self.calls = self.root / "calls"

    def invoke(self, *flags, allocated=False):
        env = dict(os.environ, CALLS=str(self.calls))
        if allocated:
            env['ALLOCATED'] = '1'
        result = subprocess.run([str(self.build), '--src', str(self.root), '--wait', '0', *flags,
            '--', 'python3', '-c', 'print(42)'], cwd=self.root, env=env, capture_output=True, text=True)
        calls = [json.loads(line) for line in self.calls.read_text().splitlines()] if self.calls.exists() else []
        return result, calls

    def test_public_job_overflows_after_preadmission_hold(self):
        result, calls = self.invoke('--public')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[1][1:3], ['--node', 'boat'])
        self.assertEqual(calls[1][-3:], ['python3', '-c', 'print(42)'])

    def test_private_and_local_data_jobs_never_overflow(self):
        for flags in ([], ['--public', '--local-data']):
            if self.calls.exists(): self.calls.unlink()
            result, calls = self.invoke(*flags)
            self.assertEqual(result.returncode, 75)
            self.assertEqual(len(calls), 1)
            self.assertNotIn('boat', calls[0])

    def test_allocated_job_is_never_replayed(self):
        result, calls = self.invoke('--public', allocated=True)
        self.assertEqual(result.returncode, 75)
        self.assertEqual(len(calls), 1)

    def test_x86_and_docker_prefer_boat(self):
        for flag in ('--x86', '--docker'):
            if self.calls.exists(): self.calls.unlink()
            result, calls = self.invoke(flag)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][calls[0].index('--node') + 1], 'boat')

    def test_local_data_rejects_explicit_boat(self):
        result, calls = self.invoke('--local-data', '--node', 'boat')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
