"""Controller policy tests. FLEET_SCRIPT permits validation of an unpublished copy."""
import importlib.machinery
import importlib.util
import os
from pathlib import Path
import tempfile
import time
import json
import unittest
from unittest.mock import patch
from types import SimpleNamespace


PATH = Path(os.environ.get("FLEET_SCRIPT", Path(__file__).resolve().parents[1] / "scripts/fleet"))
loader = importlib.machinery.SourceFileLoader("fleet_policy_under_test", str(PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
fleet = importlib.util.module_from_spec(spec)
loader.exec_module(fleet)


class PhonePolicyTests(unittest.TestCase):
    def probe(self, **changes):
        return {"ts": time.time(), "host_lane_supported": True,
                "mem_available_mb": 0, "load1": 1000, "ncpu": 8,
                "max_temp_c": 150, "services": {"sshd": "active", "fleet-worker": "active"},
                "power": {"source": "adb", "on_ac": False, "battery_temp_c": 80,
                          "android_thermal_status": 6,
                          "batteries": [{"pct": 0, "status": "Discharging"}]}, **changes}

    def args(self, name):
        return SimpleNamespace(node=name, cls=None, arch=None, tolerate=[], cmd=["true"],
                               no_src=True, src=None, mem=None, cpus="128", timeout=30,
                               idempotent=False, fetch=[], input=[])

    def launch(self, name, probe):
        with tempfile.TemporaryDirectory(prefix="fleet-placement-") as tmp:
            state = Path(tmp)
            (state / "health").mkdir()
            (state / "health/state.json").write_text(json.dumps({name: {"paused": True}}))
            with patch.object(fleet, "STATE", state), \
                 patch.object(fleet, "probe", return_value=probe), \
                 patch.object(fleet, "k8s_nodes", return_value={}), \
                 patch.object(fleet.subprocess, "run") as transport, \
                 patch.object(fleet.phone_controller, "run", return_value=0) as execute:
                try:
                    rc = fleet.cmd_run(self.args(name))
                except SystemExit as error:
                    return error.code, execute.call_args, transport.call_count
                return rc, execute.call_args, transport.call_count

    def test_phone_placement_ignores_resources_and_historical_health_pause(self):
        for name in ("omarchy-phone", "galaxy-s22plus"):
            for changes in ({}, {"power": {}, "mem_available_mb": None, "max_temp_c": None}):
                with self.subTest(node=name, changes=changes):
                    rc, call, _ = self.launch(name, self.probe(**changes))
                    self.assertEqual(rc, 0)
                    self.assertIsNotNone(call)
                    spec = call.args[3]
                    self.assertEqual(spec["argv"], ["true"])
                    self.assertNotIn("mem_mb", spec)
                    self.assertNotIn("floor_mb", spec)
                    self.assertNotIn("cpus", spec)

    def test_phone_placement_respects_owner_reachability_and_services(self):
        cases = ({"paused": True}, {"maintenance": True}, {"error": "ssh unavailable"},
                 {"services": {"sshd": "down"}}, {"services": {"fleet-worker": "down"}},
                 {"host_lane_supported": False},
                 {"android": {"omalauncher_fgs": False}}, {"tern_doctor": "failed"})
        for changes in cases:
            with self.subTest(changes=changes):
                rc, call, transports = self.launch("omarchy-phone", self.probe(**changes))
                self.assertEqual(rc, 75)
                self.assertIsNone(call)
                self.assertEqual(transports, 0)

    def test_non_phone_battery_gate_is_unchanged(self):
        node = fleet.registry()[1]["mbp"]
        reasons, _ = fleet.judge(node, self.probe(
            mem_available_mb=999999, max_temp_c=30,
            power={"on_ac": False, "batteries": [{"pct": 39, "status": "Discharging"}]}), {}, {}, {})
        self.assertTrue(any("battery" in reason for reason in reasons), reasons)

    def test_retired_phone_mode_command_is_not_a_public_interface(self):
        import subprocess
        import sys
        result = subprocess.run([sys.executable, str(PATH), "phone-mode", "--help"],
                                capture_output=True, text=True, timeout=10)
        self.assertEqual(result.returncode, 2)
        self.assertIn("invalid choice", result.stderr)

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
