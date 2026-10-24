"""Exercise the phone wrapper with isolated Android and resource fixtures."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest


RUNNER = Path(__file__).resolve().parents[1] / "scripts/fleet-polite-run"


class PhoneLaneTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="fleet-phone-lane-")
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        binary = self.home / "bin"
        binary.mkdir()
        fixtures = {
            "uname": "printf 'fixture-android\\n'\n",
            "free": "printf 'Mem: 1024 1023 1 0 0 1\\n'\n",
            "adb": "exit 1\n",
            "sensors": "exit 1\n",
            "taskset": 'echo taskset >> "$HOME/resource-calls"; exit 99\n',
            "nice": 'echo nice >> "$HOME/resource-calls"; exit 99\n',
        }
        for name, body in fixtures.items():
            path = binary / name
            path.write_text("#!/bin/sh\n" + body)
            path.chmod(0o700)
        self.env = {**os.environ, "HOME": str(self.home), "PATH": f"{binary}:/usr/bin:/bin"}

    def command(self, *payload, timeout=20):
        return [str(RUNNER), "--timeout", str(timeout), "--", *payload]

    def run_payload(self, *payload, timeout=20):
        return subprocess.run(self.command(*payload, timeout=timeout), env=self.env,
                              capture_output=True, text=True, timeout=30)

    def flag(self, name):
        path = self.home / ".config/fleet" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()

    def test_unreadable_telemetry_and_low_memory_do_not_hold_payload(self):
        result = self.run_payload(sys.executable, "-c", "print('PAYLOAD_OK')")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("PAYLOAD_OK", result.stdout)

    def test_inherits_all_existing_cpu_affinity_and_priority(self):
        code = "import json,os; print(json.dumps([sorted(os.sched_getaffinity(0)), os.getpriority(os.PRIO_PROCESS,0)]))"
        result = self.run_payload(sys.executable, "-c", code)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout),
                         [sorted(os.sched_getaffinity(0)), os.getpriority(os.PRIO_PROCESS, 0)])
        self.assertFalse((self.home / "resource-calls").exists())

    def test_multiple_jobs_start_without_slot_or_memory_reservations(self):
        first = self.start_waiter()
        try:
            result = self.run_payload(sys.executable, "-c", "print('SECOND_OK')")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("SECOND_OK", result.stdout)
        finally:
            first.terminate()
            first.communicate(timeout=15)

    def test_owner_pause_and_call_block_gate_and_payload(self):
        for name in ("pause", "owner-call"):
            with self.subTest(flag=name):
                self.flag(name)
                gate = subprocess.run([str(RUNNER), "--gate-only"], env=self.env,
                                      capture_output=True, text=True, timeout=10)
                self.assertEqual(gate.returncode, 1, gate.stderr)
                result = self.run_payload(sys.executable, "-c", "print('SHOULD_NOT_RUN')")
                self.assertEqual(result.returncode, 75, result.stderr)
                self.assertNotIn("SHOULD_NOT_RUN", result.stdout)
                (self.home / ".config/fleet" / name).unlink()

    def start_waiter(self, timeout=20, descendants=False):
        code = ("import os,time,subprocess,sys; "
                + ("p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                   "open(os.environ['HOME']+'/descendant','w').write(str(p.pid)); " if descendants else "")
                + "open(os.environ['HOME']+'/started','w').write(str(os.getpid())); time.sleep(60)")
        proc = subprocess.Popen(self.command(sys.executable, "-c", code, timeout=timeout),
                                env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(self.stop, proc)
        deadline = time.monotonic() + 10
        while not (self.home / "started").exists() and proc.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertTrue((self.home / "started").exists(), "payload did not start")
        return proc

    @staticmethod
    def stop(proc):
        if proc.poll() is None:
            proc.terminate()
        proc.communicate(timeout=15)

    def assert_not_running(self, pid):
        stat = Path(f"/proc/{pid}/stat")
        self.assertTrue(not stat.exists() or stat.read_text().split(") ", 1)[1].startswith("Z"),
                        f"owned process {pid} still running")

    def test_timeout_cleans_payload_and_descendants(self):
        proc = self.start_waiter(timeout=1, descendants=True)
        _, stderr = proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 124, stderr)
        self.assertIn("timeout", stderr)
        for name in ("started", "descendant"):
            self.assert_not_running(int((self.home / name).read_text()))

    def test_owner_pause_and_call_interrupt_running_payload(self):
        for name in ("pause", "owner-call"):
            with self.subTest(flag=name):
                proc = self.start_waiter()
                pid = int((self.home / "started").read_text())
                self.flag(name)
                _, stderr = proc.communicate(timeout=15)
                self.assertEqual(proc.returncode, 75, stderr)
                self.assert_not_running(pid)
                (self.home / ".config/fleet" / name).unlink()
                (self.home / "started").unlink()

    def test_signal_cleans_owned_group(self):
        proc = self.start_waiter(descendants=True)
        proc.terminate()
        proc.communicate(timeout=15)
        self.assertEqual(proc.returncode, 75)
        for name in ("started", "descendant"):
            self.assert_not_running(int((self.home / name).read_text()))

    def test_normal_exit_preserves_status_and_reaps_orphan_descendants(self):
        code = ("import os,subprocess,sys; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
                "open(os.environ['HOME']+'/descendant','w').write(str(p.pid)); sys.exit(7)")
        result = self.run_payload(sys.executable, "-c", code)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assert_not_running(int((self.home / "descendant").read_text()))


if __name__ == "__main__":
    unittest.main()
