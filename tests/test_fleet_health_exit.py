"""fleet-health.service sat 'failed' 848x in 30 h (11-05) because `fleet health` exits 1 whenever
any node is BAD (phones' guest down, groot disk). A completed probe that found unhealthy nodes is
the guard working, so it exits UNHEALTHY (3), which the unit counts as success; a crash still
exits 1 and fails the unit, so a dead guard stays visible."""
import importlib.machinery, importlib.util, os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
PATH = Path(os.environ.get("FLEET_SCRIPT", ROOT / "scripts/fleet"))
loader = importlib.machinery.SourceFileLoader("fleet_exit_under_test", str(PATH))
fleet = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(fleet)


class HealthExit(unittest.TestCase):
    def run_health(self, bad):
        view = {"mbp": {"conditions": {"Ready": "True"}, "unschedulable": False, "cordoned_by": None, "taints": []}}
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(fleet, "STATE", Path(tmp)), \
             patch.object(fleet, "kc", lambda *a, check=True: SimpleNamespace(stdout="{}", returncode=0)), \
             patch.object(fleet, "probe", return_value={"max_temp_c": 50}), \
             patch.object(fleet, "judge", return_value=(list(bad), [])), \
             patch.object(fleet, "k8s_nodes", return_value=view), \
             patch.object(fleet, "tailnet_online", return_value={}), \
             patch.object(fleet, "reconcile_queue_health", return_value={}), \
             patch.object(fleet, "recovery_ready", return_value=True):
            return fleet.cmd_health(SimpleNamespace(node="mbp", set=[], strikes=None))

    def test_all_healthy_is_zero(self):
        self.assertEqual(self.run_health([]), 0)

    def test_unhealthy_node_is_distinct_code(self):
        self.assertEqual(self.run_health(["disk_root 14.7GiB free < 15GiB"]), fleet.UNHEALTHY)
        self.assertNotEqual(fleet.UNHEALTHY, 1)

    def test_unit_treats_only_unhealthy_as_success(self):
        unit = (ROOT / "config/systemd/user/fleet-health.service").read_text()
        self.assertIn(f"SuccessExitStatus={fleet.UNHEALTHY}", unit)
        self.assertNotIn("SuccessExitStatus=1", unit)


if __name__ == "__main__":
    unittest.main()
