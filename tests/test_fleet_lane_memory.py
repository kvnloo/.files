#!/usr/bin/env python3
"""Lane memory quota follows memory the MBP host is already using outside Kueue."""
import copy
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fleet_queue_health import IDLE_BASELINE, STATIC_MEMORY, reconcile_lane_memory

GiB = 1024 ** 3


class API:
    def __init__(self, node_ws, pods, quota=STATIC_MEMORY, summary_error=False):
        self.summary = {"node": {"memory": {"workingSetBytes": node_ws}},
                        "pods": [{"podRef": {"namespace": ns}, "memory": {"workingSetBytes": ws}} for ns, ws in pods]}
        self.summary_error = summary_error
        self.queue = {"metadata": {"resourceVersion": "7"}, "spec": {"resourceGroups": [{
            "coveredResources": ["cpu", "memory"], "flavors": [{"name": "node-mbp", "resources": [
                {"name": "cpu", "nominalQuota": "4"}, {"name": "memory", "nominalQuota": str(quota)}]}]}]}}
        self.patches = []

    def __call__(self, *args):
        if args[:2] == ("get", "--raw"):
            if self.summary_error:
                raise RuntimeError("502 Bad Gateway")
            return SimpleNamespace(stdout=json.dumps(self.summary))
        if args[:3] == ("get", "clusterqueue", "lanes"):
            return SimpleNamespace(stdout=json.dumps(self.queue))
        assert args[:3] == ("patch", "clusterqueue", "lanes"), args
        patch = json.loads(args[-1])
        assert patch[0] == {"op": "test", "path": "/metadata/resourceVersion", "value": "7"}
        self.patches.append(patch)
        self.queue["spec"]["resourceGroups"][0]["flavors"][0]["resources"][1]["nominalQuota"] = patch[1]["value"]
        return SimpleNamespace(stdout="")

    @property
    def quota(self):
        return int(self.queue["spec"]["resourceGroups"][0]["flavors"][0]["resources"][1]["nominalQuota"])


class LaneMemoryTests(unittest.TestCase):
    def test_non_kueue_resident_memory_shrinks_the_quota(self):
        # Army + kind use 5 GiB above the idle baseline, a Kueue pod uses 2 GiB.
        api = API(IDLE_BASELINE + 5 * GiB + 2 * GiB, [("fleet-mbp", 2 * GiB), ("kube-system", GiB // 4)])
        result = reconcile_lane_memory(api)
        self.assertEqual(api.quota, STATIC_MEMORY - 5 * GiB)
        self.assertEqual(result["memory_quota"], STATIC_MEMORY - 5 * GiB)

    def test_kueue_pods_do_not_shrink_their_own_quota(self):
        api = API(IDLE_BASELINE + 6 * GiB, [("fleet-mbp", 6 * GiB)])
        reconcile_lane_memory(api)
        self.assertEqual(api.patches, [], "quota already at the static budget")
        self.assertEqual(api.quota, STATIC_MEMORY)

    def test_quota_returns_to_static_when_the_host_frees_memory(self):
        api = API(IDLE_BASELINE, [], quota=STATIC_MEMORY - 6 * GiB)
        reconcile_lane_memory(api)
        self.assertEqual(api.quota, STATIC_MEMORY)

    def test_quota_never_goes_negative(self):
        api = API(IDLE_BASELINE + 40 * GiB, [])
        reconcile_lane_memory(api)
        self.assertEqual(api.quota, 0)

    def test_small_drift_does_not_rewrite_the_queue(self):
        api = API(IDLE_BASELINE + 100 * 1024 ** 2, [], quota=STATIC_MEMORY)
        reconcile_lane_memory(api)
        self.assertEqual(api.patches, [])

    def test_unreadable_stats_leave_the_quota_alone(self):
        api = API(0, [], quota=STATIC_MEMORY - 3 * GiB, summary_error=True)
        with self.assertRaises(RuntimeError):
            reconcile_lane_memory(api)
        self.assertEqual(api.quota, STATIC_MEMORY - 3 * GiB)

    def test_static_ceiling_matches_the_iac_lanes_quota(self):
        text = (Path(__file__).resolve().parents[1] / "config/k3s/kueue/queues.yaml").read_text()
        lanes = text.split("name: lanes\n", 1)[1].split("\n---", 1)[0]
        self.assertIn('{name: memory, nominalQuota: "%d"}' % STATIC_MEMORY, lanes)


if __name__ == "__main__":
    unittest.main()
