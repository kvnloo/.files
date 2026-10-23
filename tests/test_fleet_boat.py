"""Behavior tests for public-source transfer, output retrieval and routing."""
import base64
import hashlib
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

    def test_large_source_uses_signed_raw_upload_without_account_authorization(self):
        from unittest.mock import MagicMock
        content = b"public" * (5 * 1024 * 1024 // 6 + 1)
        self.archive.write_bytes(content)
        response = {"method": "PUT", "url": "https://uploads.boat.dev/example?signed=private"}
        with patch.object(adapter.boat, "api", return_value=response) as api, \
                patch.object(adapter.urllib.request, "urlopen", return_value=MagicMock()) as upload:
            adapter.upload_source("/sandboxes/bx_23456789", self.archive)
        self.assertEqual(api.call_args.args[:2], ("/sandboxes/bx_23456789/files/upload-url", "POST"))
        request = upload.call_args.args[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.data, content)
        self.assertFalse(request.has_header("Authorization"))

    def test_signed_upload_failure_does_not_disclose_url(self):
        self.archive.write_bytes(b"x" * (5 * 1024 * 1024 + 1))
        url = "https://uploads.boat.dev/example?signed=private"
        with patch.object(adapter.boat, "api", return_value={"method": "PUT", "url": url}), \
                patch.object(adapter.urllib.request, "urlopen", side_effect=adapter.urllib.error.URLError(url)):
            with self.assertRaises(adapter.boat.BoatError) as error:
                adapter.upload_source("/sandboxes/bx_23456789", self.archive)
        self.assertNotIn(url, str(error.exception))

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

    def callback(self, output_name="src/result.txt", job_rc=17, fetch_error=False):
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
            if "/files?" in path:
                return {"encoding": "base64", "size": len(bundle.getvalue()), "content": base64.b64encode(bundle.getvalue()).decode()}
            if path.endswith("/files"):
                with tarfile.open(fileobj=io.BytesIO(base64.b64decode(body["content"]))) as tar:
                    self.assertEqual(tar.extractfile("src/public.py").read(), b"print('public')\n")
                return {}
            return {"exitCode": job_rc, "stdout": "job output\n", "stderr": ""}
        def remote(sid, command):
            if fetch_error and command.startswith("tar -C"):
                raise adapter.boat.BoatError("Missing requested artifact")
            if command.startswith("tar -C"):
                return json.dumps({"size": len(bundle.getvalue()), "sha256": hashlib.sha256(bundle.getvalue()).hexdigest()})
            return ""
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

    def test_failed_job_missing_output_preserves_command_exit(self):
        rc, dest, receipt = self.callback(fetch_error=True)
        self.assertEqual(rc, 17)
        self.assertEqual(json.loads(receipt.read_text())["exit_code"], 17)
        self.assertFalse((dest / "src/result.txt").exists())

    def test_successful_job_missing_output_is_still_an_error(self):
        with self.assertRaisesRegex(adapter.boat.BoatError, "Missing requested artifact"):
            self.callback(job_rc=0, fetch_error=True)

    def test_fetched_archive_cannot_escape_destination(self):
        with self.assertRaises(tarfile.FilterError):
            self.callback("../../escaped")
        self.assertFalse((self.root / "escaped").exists())

    def test_large_output_uses_signed_download_and_checks_sha256(self):
        from unittest.mock import MagicMock
        content = os.urandom(6 * 1024 * 1024)
        bundle = io.BytesIO()
        with tarfile.open(fileobj=bundle, mode="w:gz") as tar:
            member = tarfile.TarInfo("src/random.bin")
            member.size = len(content)
            tar.addfile(member, io.BytesIO(content))
        archive = bundle.getvalue()
        digest = hashlib.sha256(archive).hexdigest()
        response = MagicMock()
        response.__enter__.return_value = io.BytesIO(archive)
        dest = self.root / "large"
        with patch.object(adapter.boat, "remote", side_effect=[json.dumps({"size": len(archive), "sha256": digest}), ""]), \
                patch.object(adapter.boat, "api", return_value={"method": "GET", "url": "https://downloads.boat.dev/file?signed=private"}) as api, \
                patch.object(adapter.urllib.request, "urlopen", return_value=response) as download:
            receipt = adapter.fetch_output("bx_23456789", "src/random.bin", dest)
        self.assertEqual((dest / "src/random.bin").read_bytes(), content)
        self.assertEqual(receipt["archive_sha256"], digest)
        self.assertEqual(receipt["transport"], "signed-download")
        self.assertTrue(api.call_args.args[0].endswith("/files/download-url"))
        self.assertFalse(download.call_args.args[0].has_header("Authorization"))

    def test_checksum_mismatch_refuses_extraction(self):
        with patch.object(adapter.boat, "remote", return_value=json.dumps({"size": 3, "sha256": "0" * 64})), \
                patch.object(adapter.boat, "api", return_value={"content": base64.b64encode(b"bad").decode()}):
            with self.assertRaisesRegex(adapter.boat.BoatError, "SHA256"):
                adapter.fetch_output("bx_23456789", "src/result", self.root / "refused")
        self.assertFalse((self.root / "refused").exists())

    def test_signed_download_failure_withholds_url(self):
        url = "https://downloads.boat.dev/file?signed=private"
        with patch.object(adapter.boat, "remote", return_value=json.dumps({"size": 6000000, "sha256": "0" * 64})), \
                patch.object(adapter.boat, "api", return_value={"method": "GET", "url": url}), \
                patch.object(adapter.urllib.request, "urlopen", side_effect=adapter.urllib.error.URLError(url)):
            with self.assertRaises(adapter.boat.BoatError) as error:
                adapter.fetch_output("bx_23456789", "src/result", self.root / "refused")
        self.assertNotIn(url, str(error.exception))

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

    def test_local_data_rejects_explicit_avrea(self):
        result, calls = self.invoke('--local-data', '--node', 'avrea')
        self.assertEqual(result.returncode, 2)
        self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
