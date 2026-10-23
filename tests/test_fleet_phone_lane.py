"""Phone lane regression tests. All Android telemetry is an isolated fixture."""
import json
import os
from pathlib import Path
import subprocess
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
            "uname": "#!/bin/sh\necho fixture-android\n",
            "adb": "#!/bin/sh\ncase \"$*\" in\n"
                   "  devices) printf 'List of devices attached\\nfixture\\tdevice\\n' ;;\n"
                   "  *battery) printf '  level: %s\\n  status: 3\\n  temperature: %s\\n  USB powered: %s\\n' \"${TEST_BATTERY:-80}\" \"${TEST_TEMP:-300}\" \"$TEST_CHARGING\" ;;\n"
                   "  *thermalservice) printf 'Thermal Status: %s\\n' \"${TEST_THERMAL:-0}\" ;;\nesac\n",
            "taskset": "#!/bin/sh\nprintf '%s\\n' \"$2\" > \"$HOME/affinity\"\nshift 2\nexec \"$@\"\n",
        }
        for name, content in fixtures.items():
            path = binary / name
            path.write_text(content)
            path.chmod(0o700)
        self.env = {**os.environ, "HOME": str(self.home),
                    "PATH": f"{binary}:/usr/bin:/bin", "TEST_CHARGING": "true"}

    def command(self, *payload):
        return [str(RUNNER), "--mem-mb", "64", "--floor-mb", "0", "--cpus", "0-7", "--", *payload]

    def profile(self, **values):
        path = self.home / ".config/fleet/phone-mode.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"mode": "worker", "cpus": "0-5", "slots": 6,
                                    "memory_pct": 75, "min_battery_pct": 2, **values}))

    def test_worker_override_keeps_thermal_in_receipt_without_holding(self):
        self.profile()
        result = subprocess.run([str(RUNNER), "--floor-mb", "0", "--gate-only"],
                                env={**self.env, "TEST_BATTERY": "2", "TEST_CHARGING": "false",
                                     "TEST_TEMP": "500", "TEST_THERMAL": "3"},
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("thermal 3", result.stderr)
        self.assertIn("mode=worker", result.stderr)

    def test_worker_s25_floor_is_two_percent(self):
        self.profile()
        result = subprocess.run([str(RUNNER), "--floor-mb", "0", "--gate-only"],
                                env={**self.env, "TEST_BATTERY": "1"},
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("battery 1% < 2%", result.stderr)

    def test_light_retains_thermal_and_off_charger_battery_gates(self):
        for extra in ({"TEST_THERMAL": "3"}, {"TEST_BATTERY": "49", "TEST_CHARGING": "false"}):
            result = subprocess.run([str(RUNNER), "--floor-mb", "0", "--gate-only"],
                                    env={**self.env, **extra}, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 1, result.stderr)

    def test_worker_profile_allows_multiple_slots_but_never_exceeds_cap(self):
        self.profile(slots=2)
        procs = []
        try:
            for number in (1, 2):
                proc = subprocess.Popen(self.command("sh", "-c", f'touch "$HOME/started{number}"; while [ ! -e "$HOME/release" ]; do sleep 0.1; done'),
                                        env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                procs.append(proc)
                deadline = time.monotonic() + 10
                while not (self.home / f"started{number}").exists() and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue((self.home / f"started{number}").exists())
            result = subprocess.run(self.command("true"), env=self.env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertIn("all 2 phone slots are occupied", result.stderr)
            self.assertEqual((self.home / "affinity").read_text(), "0-5\n")
            (self.home / "release").touch()
            for proc in procs:
                self.assertEqual(proc.wait(timeout=20), 0)
        finally:
            (self.home / "release").touch()
            for proc in procs:
                if proc.poll() is None:
                    proc.terminate()
                    proc.wait(timeout=20)

    def test_aggregate_memory_budget_refuses_oversized_reservation(self):
        self.profile()
        result = subprocess.run([str(RUNNER), "--mem-mb", "999999999", "--floor-mb", "0", "--", "true"],
                                env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 75, result.stderr)
        self.assertIn("memory reservation held", result.stderr)

    def test_charging_cannot_exceed_two_small_cores(self):
        result = subprocess.run(self.command("true"), env=self.env, capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / "affinity").read_text(), "0-1\n")

    def test_battery_uses_one_small_core(self):
        result = subprocess.run(self.command("true"), env={**self.env, "TEST_CHARGING": "false"},
                                capture_output=True, text=True, timeout=20)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual((self.home / "affinity").read_text(), "0\n")

    def test_direct_and_worker_jobs_share_one_slot(self):
        proc = subprocess.Popen(self.command("sh", "-c", 'touch "$HOME/started"; while [ ! -e "$HOME/release" ]; do sleep 0.1; done'),
                                env=self.env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            deadline = time.monotonic() + 10
            while not (self.home / "started").exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue((self.home / "started").exists())
            result = subprocess.run(self.command("true"), env=self.env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 75, result.stderr)
            self.assertIn("all 1 phone slots are occupied", result.stderr)
            (self.home / "release").touch()
            self.assertEqual(proc.wait(timeout=20), 0)
        finally:
            (self.home / "release").touch()
            if proc.poll() is None:
                proc.terminate()
                proc.wait(timeout=20)


if __name__ == "__main__":
    unittest.main()
