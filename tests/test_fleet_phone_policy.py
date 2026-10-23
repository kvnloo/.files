"""Controller policy tests. FLEET_SCRIPT permits validation of an unpublished copy."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import unittest
from unittest.mock import patch
from types import SimpleNamespace


PATH = Path(os.environ.get("FLEET_SCRIPT", Path(__file__).resolve().parents[1] / "scripts/fleet"))
loader = importlib.machinery.SourceFileLoader("fleet_policy_under_test", str(PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
fleet = importlib.util.module_from_spec(spec)
loader.exec_module(fleet)


class PhonePolicyTests(unittest.TestCase):
    def failures(self, name, *, pct=32, mode="worker", thermal=3, available=3000):
        node = fleet.registry()[1][name]
        profile = {**node.get("phone_modes", {}).get(mode, {}), "mode": mode}
        probe = {"mem_available_mb": available, "phone_profile": profile,
                 "max_temp_c": 150 if mode == "worker" and name != "mbp" else None,
                 "power": {"source": "adb", "on_ac": False, "battery_temp_c": 50,
                           "android_thermal_status": thermal,
                           "batteries": [{"pct": pct, "status": "Discharging"}]}}
        return fleet.judge(node, probe, {}, {}, {})[0]

    def test_s25_worker_ignores_thermal_and_charging_but_requires_two_percent(self):
        self.assertEqual(self.failures("omarchy-phone", pct=2), [])
        self.assertTrue(any("battery 1% < 2%" in reason for reason in self.failures("omarchy-phone", pct=1)))

    def test_s22_worker_has_no_battery_or_thermal_gate(self):
        self.assertEqual(self.failures("galaxy-s22plus", pct=0, thermal=6), [])

    def test_light_retains_battery_and_thermal_gates(self):
        reasons = self.failures("omarchy-phone", mode="light", pct=49)
        self.assertTrue(any("battery 49% < 50%" in reason for reason in reasons))
        self.assertTrue(any("thermal" in reason for reason in reasons))
        self.assertTrue(any("battery 50C" in reason for reason in reasons))

    def test_worker_memory_floor_still_holds(self):
        self.assertTrue(any("memory" in reason for reason in self.failures("omarchy-phone", available=100)))

    def test_non_phone_battery_gate_is_unchanged(self):
        self.assertTrue(any("battery 39% < 40%" in reason for reason in self.failures("mbp", pct=39)))

    def test_phone_provisioning_uses_normal_admitted_host_lane(self):
        with patch.object(fleet.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(fleet.cmd_toolchain(SimpleNamespace(node="omarchy-phone", check=False)), 0)
        argv = run.call_args.args[0]
        self.assertIn("run", argv)
        self.assertIn("--no-src", argv)
        self.assertIn("pacman", argv)
        self.assertEqual(argv[-3:], ["go", "rust", "gcc"])

    def test_phone_provisioning_check_does_not_install(self):
        with patch.object(fleet.subprocess, "run") as run:
            run.return_value.returncode = 0
            self.assertEqual(fleet.cmd_toolchain(SimpleNamespace(node="galaxy-s22plus", check=True)), 0)
        self.assertIn("pacman -Q nodejs bun go rust gcc", run.call_args.args[0][-1])


if __name__ == "__main__":
    unittest.main()
