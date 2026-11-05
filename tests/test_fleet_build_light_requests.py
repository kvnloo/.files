"""Per-kind Kueue request defaults (MBP lanes: 4 CPU / ~10 GiB). Values come from measured pod
memory peaks (operations/fleet-stage-lifecycle-20261104/peak-rss): tests 1 CPU / 1.5 GiB so four
run at once, Node/JS builds 2 CPU / 3.5 GiB, other builds 2 CPU / 3 GiB. Explicit requests win.
fleet-build leaves --mem unset on the Kueue route so these defaults apply, and phone routes stay
resource-neutral (fleet-build supplies no phone default)."""
import importlib.machinery, importlib.util, os, subprocess, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("fleet_kueue_requests", str(ROOT / "scripts/fleet-kueue"))
kueue = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(kueue)


def wrapped(*argv):
    """The argv fleet-build hands fleet-kueue."""
    return ["env", "FLEET_BUILD_JDK=", "sh", "-c", "script mentions npm and gradle", "fleet-build", ".", *argv]


class KindRequests(unittest.TestCase):
    def test_light_jobs_ask_one_cpu_and_a_half_gib(self):
        self.assertEqual(kueue.default_requests(None, None, ["phone"]), ("1", "1.5G"))

    def test_test_class_asks_one_cpu_and_a_half_gib(self):
        self.assertEqual(kueue.default_requests(None, None, None, "test", wrapped("bash", "gate.sh")), ("1", "1.5G"))

    def test_pytest_and_unittest_are_tests_in_any_class(self):
        for argv in (("python3", "-m", "pytest", "-q"), ("/x/venv/bin/pytest",), ("python3", "-m", "unittest", "-v")):
            self.assertEqual(kueue.default_requests(None, None, None, "build", wrapped(*argv)), ("1", "1.5G"))

    def test_node_tools_get_measured_headroom_even_as_tests(self):
        for argv in (("npm", "run", "build"), ("npx", "vitest", "run"), ("bun", "test")):
            self.assertEqual(kueue.default_requests(None, None, None, "test", wrapped(*argv)), ("2", "3.5G"))

    def test_wrapper_script_text_does_not_set_the_kind(self):
        self.assertEqual(kueue.default_requests(None, None, None, None, wrapped("make", "all")), ("2", "3G"))

    def test_explicit_requests_win(self):
        self.assertEqual(kueue.default_requests("3", "5G", ["phone"], "test", wrapped("npm", "ci")), ("3", "5G"))
        self.assertEqual(kueue.default_requests(None, "8G", None, "test", wrapped("pytest")), ("1", "8G"))


class FleetBuildPassesNoKueueDefault(unittest.TestCase):
    """fleet-build must not pin --mem 3G on the Kueue route, or fleet-kueue's defaults never apply."""

    def submitted(self, *flags):
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "argv"
            fake = Path(d) / "fake-kueue"
            fake.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {log}\nexit 0\n"); fake.chmod(0o755)
            fleet = Path(d) / "fleet"; fleet.write_text(f"#!/bin/sh\nprintf '%s\\n' \"$@\" > {log}\n"); fleet.chmod(0o755)
            env = dict(os.environ, FLEET=str(fleet), PATH=f"{d}:{os.environ['PATH']}")
            body = (ROOT / "scripts/fleet-build").read_text().replace(
                'python3 "$(dirname "$FLEET")/fleet-kueue"', f'"{fake}"')
            script = Path(d) / "fleet-build"; script.write_text(body); script.chmod(0o755)
            subprocess.run([str(script), *flags, "--wait", "5", "--", "true"], cwd=d, env=env,
                           capture_output=True, text=True, timeout=60)
            return log.read_text().split("\n") if log.exists() else []

    def test_mbp_build_leaves_mem_to_fleet_kueue(self):
        argv = self.submitted("--node", "mbp", "--class", "test")
        self.assertIn("--class", argv)
        self.assertNotIn("--mem", argv[:argv.index("--")])

    def test_explicit_mem_is_passed(self):
        argv = self.submitted("--node", "mbp", "--mem", "5G")
        self.assertEqual(argv[argv.index("--mem") + 1], "5G")


if __name__ == "__main__":
    unittest.main()
