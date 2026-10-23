"""Wrapper-only regressions: fake fleet/sleep, no SSH, packages, builds or tests dispatched."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import uuid

ROOT = Path(__file__).resolve().parents[1]


class FleetBuild(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.wrapper = self.bin / "fleet-build"
        shutil.copyfile(ROOT / "scripts/fleet-build", self.wrapper)
        self.capture = self.root / "calls.jsonl"
        self.repo = self.root / "arbitrary-worktree-name"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        self.set_origin("git@github.com:kvnloo/noop-oura.git")
        (self.repo / "android").mkdir()
        self.executable("sleep", "#!/bin/sh\nexit 0\n")
        self.executable("fleet", f"#!{sys.executable}\n" + '''import json, os, pathlib, sys
p = pathlib.Path(os.environ["CAPTURE"])
calls = p.read_text().splitlines() if p.exists() else []
with p.open("a") as f:
    f.write(json.dumps({"args": sys.argv[1:], "queued": os.environ.get("FLEET_QUEUED_TS"),
                        "attempt": os.environ.get("FLEET_ATTEMPT_ID")}) + "\\n")
if not calls and os.environ.get("FIRST_RC"):
    if os.environ.get("ADMITTED"):
        print("fleet: job 20261022-000000-abcd -> mbp", file=sys.stderr)
    else:
        print("fleet: no room now", file=sys.stderr)
    sys.exit(int(os.environ["FIRST_RC"]))
''')

    def executable(self, name, content):
        path = self.bin / name
        path.write_text(content)
        path.chmod(0o755)

    def set_origin(self, origin):
        subprocess.run(["git", "-C", str(self.repo), "config", "remote.origin.url", origin], check=True)

    def call(self, *options, cwd=None, env=None, cmd=("bash", "-c", "true")):
        clean = {key: value for key, value in os.environ.items()
                 if not key.startswith("FLEET_") and key not in ("FIRST_RC", "ADMITTED")}
        clean.update(PATH=f"{self.bin}:{os.environ['PATH']}", CAPTURE=str(self.capture))
        clean.update(env or {})
        result = subprocess.run(["bash", str(self.wrapper), "--src", str(self.repo), *options, "--", *cmd],
                                cwd=cwd or self.repo, env=clean, capture_output=True, text=True)
        calls = [json.loads(line) for line in self.capture.read_text().splitlines()]
        return result, calls

    def option(self, call, option):
        args = call["args"]
        return args[args.index(option) + 1]

    def test_noop_android_shell_uses_scoped_candidate_budget(self):
        result, calls = self.call(cwd=self.repo / "android")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.option(calls[0], "--mem"), "6G")
        self.assertEqual(self.option(calls[0], "--class"), "build")

    def test_explicit_memory_and_timeout_win(self):
        result, calls = self.call("--mem", "1G", "--timeout", "900", cwd=self.repo / "android")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.option(calls[0], "--mem"), "1G")
        self.assertEqual(self.option(calls[0], "--timeout"), "900")

    def test_other_noop_builds_keep_generic_budget(self):
        result, calls = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.option(calls[0], "--mem"), "3G")

    def test_other_repos_do_not_inherit_noop_budget(self):
        self.set_origin("https://github.com/example/another-repo.git")
        result, calls = self.call(cwd=self.repo / "android")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.option(calls[0], "--mem"), "3G")

    def test_light_keeps_small_budget_even_in_android(self):
        result, calls = self.call("--light", cwd=self.repo / "android")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.option(calls[0], "--mem"), "512M")

    def test_direct_gradle_keeps_android_envelope(self):
        result, calls = self.call(cmd=("./gradlew", "assembleDebug"))
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.option(calls[0], "--mem"), "6G")
        self.assertEqual(self.option(calls[0], "--class"), "android-build")

    def test_git_is_opt_in(self):
        result, calls = self.call("--git")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--git", calls[0]["args"])
        self.assertEqual(calls[0]["args"].count("--git"), 1)

    def test_default_has_no_git_metadata_request(self):
        result, calls = self.call()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--git", calls[0]["args"])

    def test_queue_identity_is_stable_across_admission_retries(self):
        result, calls = self.call("--wait", "120", env={"FIRST_RC": "75"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0]["queued"], calls[1]["queued"])
        self.assertGreater(int(calls[0]["queued"]), 0)
        self.assertEqual(calls[0]["attempt"], calls[1]["attempt"])
        uuid.UUID(calls[0]["attempt"])

    def test_upstream_queue_identity_is_preserved(self):
        result, calls = self.call(env={"FLEET_QUEUED_TS": "1792700000", "FLEET_ATTEMPT_ID": "original-attempt"})
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls[0]["queued"], "1792700000")
        self.assertEqual(calls[0]["attempt"], "original-attempt")

    def test_allocated_exit75_is_not_replayed(self):
        result, calls = self.call("--wait", "120", env={"FIRST_RC": "75", "ADMITTED": "1"})
        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertEqual(len(calls), 1)

    def test_exit1_is_not_an_admission_hold(self):
        result, calls = self.call("--wait", "1800", env={"FIRST_RC": "1"})
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(len(calls), 1)


if __name__ == "__main__":
    unittest.main()
