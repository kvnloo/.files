"""fleet health uncordons a node it cordoned itself once healthy for 2 probes, even when its
local state forgot the cordon (2026-11-05: mbp stayed cordoned after DiskPressure cleared)."""
import importlib.machinery, importlib.util, json, os, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

PATH = Path(os.environ.get("FLEET_SCRIPT", Path(__file__).resolve().parents[1] / "scripts/fleet"))
loader = importlib.machinery.SourceFileLoader("fleet_uncordon_under_test", str(PATH))
fleet = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(fleet)


def node(cordoned_by="fleet-health"):
    ann = {fleet.ANNOT: cordoned_by} if cordoned_by else {}
    return {"mbp": {"conditions": {"Ready": "True", "DiskPressure": "False"}, "unschedulable": True,
                    "cordoned_by": ann.get(fleet.ANNOT), "taints": []}}


class OwnedUncordon(unittest.TestCase):
    def run_probes(self, views, state=None):
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            st = Path(tmp)
            if state is not None:
                (st / "health").mkdir(parents=True)
                (st / "health" / "state.json").write_text(json.dumps(state))
            def kc(*args, check=True):
                calls.append(args)
                return SimpleNamespace(stdout="{}", returncode=0)
            for view in views:
                with patch.object(fleet, "STATE", st), patch.object(fleet, "kc", kc), \
                     patch.object(fleet, "probe", return_value={"max_temp_c": 50}), \
                     patch.object(fleet, "judge", return_value=([], [])), \
                     patch.object(fleet, "k8s_nodes", return_value=view), \
                     patch.object(fleet, "tailnet_online", return_value={}), \
                     patch.object(fleet, "reconcile_queue_health", return_value={}), \
                     patch.object(fleet, "recovery_ready", return_value=True):
                    fleet.cmd_health(SimpleNamespace(node="mbp", set=[], strikes=None))
        return [c for c in calls if c[0] == "uncordon"], calls

    def test_owned_cordon_is_lifted_after_two_good_probes_without_local_state(self):
        up, _ = self.run_probes([node()])
        self.assertEqual(up, [], "one good probe is not enough")
        up, _ = self.run_probes([node(), node()])
        self.assertEqual(up, [("uncordon", "mbp")])

    def test_a_missed_k8s_read_does_not_forget_ownership(self):
        """paused was cleared on the probe where the node view was missing; the cordon then stuck."""
        up, _ = self.run_probes([node(), {}, node()], state={"mbp": {"bad": 5, "good": 0, "paused": True}})
        self.assertEqual(up, [("uncordon", "mbp")])

    def test_someone_elses_cordon_is_left_alone(self):
        up, _ = self.run_probes([node(None)] * 3)
        self.assertEqual(up, [])


if __name__ == "__main__":
    unittest.main()
