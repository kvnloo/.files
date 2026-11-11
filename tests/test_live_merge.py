#!/usr/bin/env python3
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "live-merge"
IDENTITY = "Kevin Rajan <7121943+kvnloo@users.noreply.github.com>"


class LiveMergeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.repo = self.root / "repo"
        self.repo.mkdir()
        self.env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
        self.env.update(GIT_CONFIG_NOSYSTEM="1", GIT_CONFIG_GLOBAL=os.devnull)
        self.git("init", "-b", "main")
        self.git("config", "user.name", "Test User")
        self.git("config", "user.email", "test@example.com")
        (self.repo / "value").write_text("base\n")
        self.git("add", ".")
        self.git("commit", "-m", "base")
        self.base = self.git("rev-parse", "HEAD")
        self.git("branch", "live")
        self.git("checkout", "-b", "candidate")
        (self.repo / "value").write_text("candidate\n")
        self.git("commit", "-am", "candidate")
        self.candidate = self.git("rev-parse", "HEAD")
        self.git("checkout", "main")

    def git(self, *args, cwd=None):
        result = subprocess.run(
            ["git", *args], cwd=cwd or self.repo, env=self.env,
            text=True, capture_output=True, check=True,
        )
        return result.stdout.strip()

    def command(self, code):
        return f"{shlex.quote(sys.executable)} -c {shlex.quote(code)}"

    def invoke(self, *args, expected=0):
        before = self.git("worktree", "list", "--porcelain")
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *map(str, args)], env=self.env,
            text=True, capture_output=True, timeout=30,
        )
        self.assertEqual(result.returncode, expected, result.stdout + result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 1, result.stdout)
        data = json.loads(result.stdout)
        self.assertEqual(set(data), {"status", "merge", "base"})
        after = self.git("worktree", "list", "--porcelain")
        self.assertEqual(
            [line for line in after.splitlines() if line.startswith("worktree ")],
            [line for line in before.splitlines() if line.startswith("worktree ")],
        )
        return data

    def merge(self, code="pass", expected=0):
        return self.invoke(self.repo, "candidate", "--test", self.command(code), expected=expected)

    def serving_checkout(self):
        serving = self.root / "serving checkout"
        self.git("worktree", "add", str(serving), "live")
        return serving

    def test_passing_test_advances_live_and_tests_merged_tree(self):
        (self.repo / "live-only").write_text("live\n")
        self.git("add", ".")
        self.git("commit", "-m", "live-only change")
        self.git("branch", "-f", "live", "HEAD")
        base = self.git("rev-parse", "live")
        data = self.merge(
            "from pathlib import Path; "
            "assert Path('value').read_text() == 'candidate\\n'; "
            "assert Path('live-only').read_text() == 'live\\n'; "
            "Path('test-artifact').write_text('temporary'); print('test output')"
        )
        self.assertEqual(data["base"], base)
        self.assertEqual(data["merge"], self.git("rev-parse", "live"))
        self.assertEqual(self.git("show", "-s", "--format=%P", "live"), f"{base} {self.candidate}")
        self.assertEqual(self.git("show", "-s", "--format=%an <%ae>", "live"), IDENTITY)
        self.assertEqual(self.git("show", "-s", "--format=%cn <%ce>", "live"), IDENTITY)

    def test_failing_test_leaves_live_unchanged(self):
        data = self.merge("raise SystemExit(1)", expected=5)
        self.assertEqual(data["base"], self.base)
        self.assertEqual(self.git("rev-parse", "live"), self.base)

    def test_conflict_leaves_live_unchanged(self):
        (self.repo / "value").write_text("conflicting\n")
        self.git("commit", "-am", "conflict")
        self.git("branch", "-f", "live", "HEAD")
        base = self.git("rev-parse", "live")
        marker = self.root / "test-ran"
        self.merge(f"from pathlib import Path; Path({str(marker)!r}).touch()", expected=4)
        self.assertFalse(marker.exists())
        self.assertEqual(self.git("rev-parse", "live"), base)

    def test_missing_live_exits_3_without_creating_it(self):
        self.git("branch", "-D", "live")
        data = self.merge(expected=3)
        self.assertIsNone(data["base"])
        self.assertEqual(self.git("branch", "--list", "live"), "")

    def test_dirty_serving_checkout_exits_6(self):
        serving = self.serving_checkout()
        for filename in ("value", "untracked"):
            with self.subTest(filename=filename):
                path = serving / filename
                path.write_text("owner changes\n")
                self.merge(expected=6)
                self.assertEqual(self.git("rev-parse", "live"), self.base)
                self.assertEqual(path.read_text(), "owner changes\n")
                if filename == "value":
                    path.write_text("base\n")
                else:
                    path.unlink()

    def test_clean_serving_checkout_is_fast_forwarded(self):
        serving = self.serving_checkout()
        data = self.merge()
        self.assertEqual(self.git("rev-parse", "HEAD", cwd=serving), data["merge"])
        self.assertEqual((serving / "value").read_text(), "candidate\n")
        self.assertEqual(self.git("status", "--porcelain", cwd=serving), "")

    def test_revert_restores_tree(self):
        serving = self.serving_checkout()
        merged = self.merge()["merge"]
        data = self.invoke("--revert", self.repo, merged)
        self.assertEqual(data["base"], merged)
        self.assertEqual(data["merge"], self.git("rev-parse", "live"))
        self.assertEqual(self.git("rev-parse", "live^{tree}"), self.git("rev-parse", f"{self.base}^{{tree}}"))
        self.assertEqual((serving / "value").read_text(), "base\n")

    def test_revert_can_test_before_publishing(self):
        merged = self.merge()["merge"]
        self.invoke("--revert", self.repo, merged, "--test", self.command("raise SystemExit(1)"), expected=5)
        self.assertEqual(self.git("rev-parse", "live"), merged)


if __name__ == "__main__":
    unittest.main()
