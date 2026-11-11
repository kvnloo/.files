"""hermes-skew-restart puts a backend that predates the checkout's HEAD back on the code on disk."""
import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/hermes-skew-restart"


class SkewRestart(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.repo = self.tmp / "checkout"
        self.bin = self.tmp / "bin"
        self.bin.mkdir()
        self.calls = self.tmp / "calls"
        self.journal_epoch = self.tmp / "journal_epoch"
        self.journal_epoch.write_text(str(int(time.time())))
        git = lambda *a: subprocess.run(["git", "-C", str(self.repo), *a], check=True, capture_output=True)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "old")
        self.old = subprocess.Popen(["sleep", "60"])  # a backend that boots on the old code
        time.sleep(1.2)
        git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "new")
        time.sleep(1.2)
        self.new = subprocess.Popen(["sleep", "60"])  # a backend that booted after the move
        self.stub("systemctl", f"""case "$*" in
  *"show hermes-gateway -p MainPID"*) echo {self.old.pid};;
  *"show hermes-web -p MainPID"*) echo {self.old.pid};;
  *"show fresh -p MainPID"*) echo {self.new.pid};;
  *) echo "$*" >> {self.calls};;
esac""")
        self.stub("journalctl", f'echo "$(cat {self.journal_epoch}).000000 host unit[1]: line"')

    def tearDown(self):
        self.old.kill(); self.new.kill()

    def stub(self, name, body):
        path = self.bin / name
        path.write_text("#!/bin/sh\n" + body + "\n")
        path.chmod(0o755)

    def run_script(self, units, **env):
        e = {**os.environ, "PATH": f"{self.bin}:{os.environ['PATH']}", "HERMES_CHECKOUT": str(self.repo),
             "HERMES_SKEW_UNITS": units, "XDG_STATE_HOME": str(self.tmp / "state"), **env}
        return subprocess.run(["bash", str(SCRIPT)], env=e, capture_output=True, text=True, check=True).stdout

    def acted(self):
        return self.calls.read_text().splitlines() if self.calls.exists() else []

    def test_stale_gateway_gets_one_graceful_reload(self):
        self.run_script("hermes-gateway")
        self.assertEqual(self.acted(), ["--user reload hermes-gateway"])
        self.assertIn("already asked", self.run_script("hermes-gateway"))
        self.assertEqual(len(self.acted()), 1)

    def test_busy_stale_web_waits_then_restarts_after_grace(self):
        self.assertIn("waiting for a quiet moment", self.run_script("hermes-web", HERMES_SKEW_GRACE_S="600"))
        self.assertEqual(self.acted(), [])
        self.run_script("hermes-web", HERMES_SKEW_GRACE_S="0")
        self.assertEqual(self.acted(), ["--user restart hermes-web"])

    def test_quiet_stale_web_restarts_at_once(self):
        self.journal_epoch.write_text(str(int(time.time()) - 300))
        self.run_script("hermes-web")
        self.assertEqual(self.acted(), ["--user restart hermes-web"])

    def test_backend_started_after_the_move_is_left_alone(self):
        self.assertIn("current", self.run_script("fresh", HERMES_SKEW_GRACE_S="0"))
        self.assertEqual(self.acted(), [])


class Upheld(unittest.TestCase):
    """A blanket `systemctl --user stop <every timer>` must not leave Hermes backends unwatched."""

    def test_both_backends_uphold_the_timer(self):
        root = Path(__file__).resolve().parents[1] / "config/systemd/user"
        for dropin in ("hermes-web.service.d/60-retire-on-code-skew.conf",
                       "hermes-gateway.service.d/60-skew-restart.conf"):
            lines = (root / dropin).read_text().splitlines()
            self.assertIn("Upholds=hermes-skew-restart.timer", lines, dropin)


if __name__ == "__main__":
    unittest.main()
