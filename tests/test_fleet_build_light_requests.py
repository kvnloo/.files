"""Kueue requests for fleet-build --light jobs (lint, pure-Python tests) default to 1 CPU /
2 GiB so the 4-CPU MBP lanes quota admits 4 instead of 2; explicit requests still win and
phone routes stay resource-neutral (fleet-build itself supplies no default)."""
import importlib.machinery, importlib.util, unittest
from pathlib import Path

loader = importlib.machinery.SourceFileLoader(
    "fleet_kueue_requests", str(Path(__file__).resolve().parents[1] / "scripts/fleet-kueue"))
kueue = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(kueue)


class LightRequests(unittest.TestCase):
    def test_light_defaults_to_one_cpu_two_gib(self):
        self.assertEqual(kueue.default_requests(None, None, ["phone"]), ("1", "2G"))

    def test_explicit_requests_win(self):
        self.assertEqual(kueue.default_requests("3", "5G", ["phone"]), ("3", "5G"))

    def test_other_jobs_unchanged(self):
        self.assertEqual(kueue.default_requests(None, None, None), ("2", "3G"))


if __name__ == "__main__":
    unittest.main()
