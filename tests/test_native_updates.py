"""Exercise native setup admission without touching packages or systemd."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/setup-native-updates"


class NativeUpdateAdmissionTests(unittest.TestCase):
    def run_enable(self, first="not-found", second="not-found", status=0):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            calls = root / "calls"
            stubs = {
                "systemctl": '''#!/bin/sh
printf '%s\\n' "$*" >> "$CALLS"
[ "$1" = show ] || exit 97
[ "$2" = os-update.timer ] && state=$FIRST || state=$SECOND
printf '%s\\n' "$state"
exit "$QUERY_STATUS"
''',
                "df": "#!/bin/sh\nexit 97\n",
                "pacman": "#!/bin/sh\nexit 97\n",
                "install": "#!/bin/sh\nexit 97\n",
            }
            for name, content in stubs.items():
                path = root / name
                path.write_text(content)
                path.chmod(0o755)
            result = subprocess.run(
                ["bash", str(SCRIPT), "enable"], capture_output=True, text=True,
                env={**os.environ, "PATH": f"{root}:{os.environ['PATH']}",
                     "CALLS": str(calls), "FIRST": first, "SECOND": second,
                     "QUERY_STATUS": str(status)},
            )
            return result, calls.read_text().splitlines() if calls.exists() else []

    def test_installed_daily_timer_refuses_before_privilege_or_mutation(self):
        result, calls = self.run_enable(first="loaded")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Refusing: os-update.timer", result.stderr)
        self.assertEqual(calls, ["show os-update.timer -p LoadState --value"])

    def test_installed_maintenance_timer_also_refuses(self):
        result, calls = self.run_enable(second="loaded")
        self.assertEqual(result.returncode, 1)
        self.assertIn("Refusing: os-update-maintenance.timer", result.stderr)
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(call.startswith("show ") for call in calls))

    def test_unknown_masked_or_failed_queries_fail_closed(self):
        for state, status in [("", 0), ("masked", 0), ("error", 0), ("not-found", 1)]:
            with self.subTest(state=state, status=status):
                result, calls = self.run_enable(first=state, status=status)
                self.assertEqual(result.returncode, 1)
                self.assertIn("Refusing:", result.stderr)
                self.assertEqual(calls, ["show os-update.timer -p LoadState --value"])

    def test_absent_timers_reach_existing_privilege_or_disk_gate(self):
        result, calls = self.run_enable()
        self.assertEqual(calls, ["show os-update.timer -p LoadState --value",
                                 "show os-update-maintenance.timer -p LoadState --value"])
        self.assertEqual(result.returncode, 97 if os.geteuid() == 0 else 1)
        self.assertNotIn("Refusing:", result.stderr)


if __name__ == "__main__":
    unittest.main()
