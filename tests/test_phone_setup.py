"""Exercise the handoff with real local Git repositories and no Android device."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PhoneSetupTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="phone-handoff-")
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.home = self.root / "home"
        self.home.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        # Even if fleet has an adb on PATH, never contact a real device.
        self.adb_log = self.root / "adb.log"
        (self.bin / "adb").write_text(
            '#!/bin/sh\nprintf "%s\\n" "$*" >> "$ADB_LOG"\n'
            'if [ "$*" = devices ]; then printf "List of devices attached\\n\\n"; '
            'else echo "unexpected phone access" >&2; exit 99; fi\n'
        )
        (self.bin / "adb").chmod(0o755)
        self.source = self.root / "source"
        self.dest = self.root / "friend checkout"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "XDG_CONFIG_HOME": str(self.home / ".config"),
            "PATH": str(self.bin) + os.pathsep + os.environ["PATH"],
            "ADB_LOG": str(self.adb_log),
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_TERMINAL_PROMPT": "0",
            "GIT_AUTHOR_NAME": "Test",
            "GIT_AUTHOR_EMAIL": "test@example.invalid",
            "GIT_COMMITTER_NAME": "Test",
            "GIT_COMMITTER_EMAIL": "test@example.invalid",
            "PHONE_SETUP_REPO": str(self.source),
            "PHONE_SETUP_DIR": str(self.dest),
            "PHONE_SETUP_BRANCH": "master dev",
        }
        self.git(self.source, "init", "-q", "-b", "master", create=True)
        for name in ("scripts/phone-setup", "config/phone-setup/env.example"):
            target = self.source / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(ROOT / name, target)
        self.map = "docs/phone-setup/README.md"
        (self.source / self.map).parent.mkdir(parents=True)
        (self.source / self.map).write_text("Local fixture setup map\n")
        self.git(self.source, "add", ".")
        self.git(self.source, "commit", "-qm", "Initial setup")

    def git(self, repo, *args, create=False):
        if create:
            repo.mkdir()
        return subprocess.run(
            ["git", "-C", str(repo), *args], env=self.env,
            text=True, capture_output=True, check=True,
        ).stdout.strip()

    def run_handoff(self, success=True):
        result = subprocess.run(
            ["bash", str(ROOT / "scripts/phone-setup-handoff")],
            env=self.env, text=True, capture_output=True, timeout=20,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def test_fresh_clone_prints_map_and_runs_real_doctor_without_phone(self):
        result = self.run_handoff()
        self.assertTrue((self.dest / self.map).is_file())
        self.assertIn(str(self.dest / self.map), result.stdout)
        self.assertIn("no authorized phone", result.stdout)
        self.assertIn("never put passwords or pairing codes in chat", result.stdout)
        self.assertEqual(self.adb_log.read_text().splitlines(), ["devices"])
        self.assertFalse((self.home / ".config").exists())

    def test_rerun_preserves_head(self):
        self.run_handoff()
        head = self.git(self.dest, "rev-parse", "HEAD")
        self.run_handoff()
        self.assertEqual(self.git(self.dest, "rev-parse", "HEAD"), head)
        self.assertEqual(self.git(self.dest, "status", "--porcelain"), "")

    def test_rerun_fast_forwards_clean_checkout(self):
        self.run_handoff()
        (self.source / self.map).write_text("Updated map\n")
        self.git(self.source, "commit", "-qam", "Update map")
        self.run_handoff()
        self.assertEqual((self.dest / self.map).read_text(), "Updated map\n")

    def test_local_commit_is_not_reset(self):
        self.run_handoff()
        (self.dest / "friend.txt").write_text("Friend's local work\n")
        self.git(self.dest, "add", ".")
        self.git(self.dest, "commit", "-qm", "Friend's work")
        head = self.git(self.dest, "rev-parse", "HEAD")
        self.run_handoff(success=False)
        self.assertEqual(self.git(self.dest, "rev-parse", "HEAD"), head)
        self.assertTrue((self.dest / "friend.txt").is_file())

    def test_dirty_tracked_file_is_not_changed(self):
        self.run_handoff()
        (self.dest / self.map).write_text("Friend's edits\n")
        self.run_handoff(success=False)
        self.assertEqual((self.dest / self.map).read_text(), "Friend's edits\n")

    def test_untracked_file_blocks_rerun(self):
        self.run_handoff()
        (self.dest / "notes.txt").write_text("Keep me\n")
        self.run_handoff(success=False)
        self.assertEqual((self.dest / "notes.txt").read_text(), "Keep me\n")

    def test_another_branch_is_not_switched(self):
        self.run_handoff()
        self.git(self.dest, "switch", "-qc", "friend-work")
        self.run_handoff(success=False)
        self.assertEqual(self.git(self.dest, "branch", "--show-current"), "friend-work")

    def test_wrong_origin_is_not_reused(self):
        self.run_handoff()
        self.env["PHONE_SETUP_REPO"] = str(self.root / "different-source")
        self.assertIn("origin", self.run_handoff(success=False).stderr)

    def test_non_repository_directory_is_preserved(self):
        self.dest.mkdir()
        (self.dest / "keep.txt").write_text("Keep me\n")
        self.run_handoff(success=False)
        self.assertEqual((self.dest / "keep.txt").read_text(), "Keep me\n")

    def test_dev_fallback_when_master_has_no_map(self):
        self.git(self.source, "branch", "dev")
        self.git(self.source, "rm", self.map)
        self.git(self.source, "commit", "-qm", "No map on master")
        self.assertIn("branch dev", self.run_handoff().stdout)

    def test_missing_map_fails_without_running_doctor(self):
        self.git(self.source, "rm", self.map)
        self.git(self.source, "commit", "-qm", "Remove map")
        self.assertIn("no branch", self.run_handoff(success=False).stderr)
        self.assertFalse(self.adb_log.exists())

    def test_init_preserves_existing_configuration(self):
        env_file = self.home / ".config/phone-setup/env"
        env_file.parent.mkdir(parents=True)
        env_file.write_text("PHONE_SERIAL=friend-phone\nDETENT_PACKAGE=app.friend.launcher\n")
        for _ in range(2):
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/phone-setup"), "init"],
                env=self.env, text=True, capture_output=True, timeout=10,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(env_file.read_text(),
                         "PHONE_SERIAL=friend-phone\nDETENT_PACKAGE=app.friend.launcher\n")
        self.assertFalse(self.adb_log.exists())


if __name__ == "__main__":
    unittest.main(verbosity=2)
