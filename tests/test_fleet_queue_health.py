#!/usr/bin/env python3
"""Executable, API-transport-doubled queue health contracts; no cluster access."""
import copy
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from fleet_queue_health import OWNER, OWNED, QUEUES, reconcile, recovery_ready


class API:
    def __init__(self):
        self.node = {"spec": {}, "status": {"conditions": [
            {"type": name, "status": "True" if name == "Ready" else "False"}
            for name in ("Ready", "DiskPressure", "MemoryPressure", "PIDPressure")]}}
        self.queues = {name: {"metadata": {"resourceVersion": "1"}, "spec": {"stopPolicy": "None"}} for name in QUEUES}
        self.writes = []
        self.fail = None

    def __call__(self, *args):
        if self.fail == args[:3]:
            raise subprocess.CalledProcessError(1, args, stderr="API unavailable")
        if args[:2] == ("get", "node"):
            return SimpleNamespace(stdout=json.dumps(self.node))
        name = args[2]
        if args[0] == "get":
            return SimpleNamespace(stdout=json.dumps(self.queues[name]))
        assert args[:2] == ("patch", "clusterqueue")
        patch = json.loads(args[-1])
        queue = copy.deepcopy(self.queues[name])
        for op in patch:
            parts = [p.replace("~1", "/").replace("~0", "~") for p in op["path"].split("/")[1:]]
            target = queue
            for part in parts[:-1]:
                target = target[part]
            if op["op"] == "test":
                assert target[parts[-1]] == op["value"]
            elif op["op"] == "remove":
                del target[parts[-1]]
            else:
                target[parts[-1]] = op["value"]
        self.queues[name] = queue
        self.writes.append((name, patch))
        return SimpleNamespace(stdout=json.dumps(queue))


class QueueHealthTests(unittest.TestCase):
    def assertPolicies(self, api, value):
        self.assertEqual({n: q["spec"]["stopPolicy"] for n, q in api.queues.items()}, {n: value for n in QUEUES})

    def test_cordon_holds_both_and_ready_restores_owned(self):
        api = API()
        api.node["spec"]["unschedulable"] = True
        reconcile(api)
        self.assertPolicies(api, "Hold")
        for queue in api.queues.values():
            self.assertEqual(queue["metadata"]["annotations"][OWNER], OWNED)
        api.node["spec"]["unschedulable"] = False
        reconcile(api)
        self.assertPolicies(api, "None")
        for queue in api.queues.values():
            self.assertNotIn(OWNER, queue["metadata"]["annotations"])

    def test_pressure_not_ready_and_blocking_taints_hold(self):
        for kind in ("DiskPressure", "MemoryPressure", "PIDPressure", "Ready", "NoSchedule", "NoExecute", "unknown"):
            with self.subTest(kind=kind):
                api = API()
                if kind in ("NoSchedule", "NoExecute"):
                    api.node["spec"]["taints"] = [{"key": "operator", "effect": kind}]
                elif kind == "unknown":
                    api.node["status"]["conditions"] = []
                else:
                    for condition in api.node["status"]["conditions"]:
                        if condition["type"] == kind:
                            condition["status"] = "False" if kind == "Ready" else "True"
                reconcile(api)
                self.assertPolicies(api, "Hold")

    def test_unowned_policies_never_changed(self):
        for policy in ("Hold", "HoldAndDrain"):
            for blocked in (False, True):
                api = API()
                for queue in api.queues.values():
                    queue["spec"]["stopPolicy"] = policy
                reconcile(api, unhealthy=blocked)
                self.assertPolicies(api, policy)
                self.assertEqual(api.writes, [])

    def test_operator_drain_revokes_ownership_without_override(self):
        api = API()
        reconcile(api, unhealthy=True)
        for queue in api.queues.values():
            queue["spec"]["stopPolicy"] = "HoldAndDrain"
        for blocked in (True, False):
            reconcile(api, unhealthy=blocked)
            self.assertPolicies(api, "HoldAndDrain")
        for queue in api.queues.values():
            self.assertNotIn(OWNER, queue["metadata"]["annotations"])

    def test_failed_queue_write_raises_and_still_holds_other_queue(self):
        api = API()
        api.fail = ("patch", "clusterqueue", "lanes")
        with self.assertRaisesRegex(RuntimeError, "lanes"):
            reconcile(api, unhealthy=True)
        self.assertEqual(api.queues["bench-lanes"]["spec"]["stopPolicy"], "Hold")
        self.assertEqual(api.queues["lanes"]["spec"]["stopPolicy"], "None")

    def test_node_api_failure_never_releases_owned_hold(self):
        api = API()
        reconcile(api, unhealthy=True)
        api.fail = ("get", "node", "mbp")
        with self.assertRaisesRegex(RuntimeError, "node health unavailable"):
            reconcile(api)
        self.assertPolicies(api, "Hold")

    def test_node_read_failure_closes_admission_where_api_allows(self):
        api = API()
        api.fail = ("get", "node", "mbp")
        with self.assertRaisesRegex(RuntimeError, "node health unavailable"):
            reconcile(api)
        self.assertPolicies(api, "Hold")

    def test_operator_takes_over_existing_guard_hold(self):
        api = API()
        reconcile(api, unhealthy=True)
        for queue in api.queues.values():
            del queue["metadata"]["annotations"][OWNER]
        reconcile(api)
        self.assertPolicies(api, "Hold")

    def test_owned_uncordon_requires_fresh_ready_no_pressure_or_other_taints(self):
        api = API()
        api.node["metadata"] = {"annotations": {"z0.dev/cordoned-by": "fleet-health"}}
        api.node["spec"] = {"unschedulable": True, "taints": [
            {"key": "node.kubernetes.io/unschedulable", "effect": "NoSchedule"}]}
        self.assertTrue(recovery_ready(api))
        baseline = copy.deepcopy(api.node)
        for kind in ("DiskPressure", "MemoryPressure", "PIDPressure", "Ready", "taint", "owner"):
            with self.subTest(kind=kind):
                api.node = copy.deepcopy(baseline)
                if kind == "taint":
                    api.node["spec"]["taints"].append({"key": "disk-pressure", "effect": "NoSchedule"})
                elif kind == "owner":
                    api.node["metadata"]["annotations"] = {}
                else:
                    for condition in api.node["status"]["conditions"]:
                        if condition["type"] == kind:
                            condition["status"] = "False" if kind == "Ready" else "True"
                self.assertFalse(recovery_ready(api))

    def test_unrelated_annotations_survive_and_writes_are_conditional(self):
        api = API()
        for queue in api.queues.values():
            queue["metadata"]["annotations"] = {"operator": "keep"}
        reconcile(api, unhealthy=True)
        reconcile(api, unhealthy=True)
        self.assertEqual(len(api.writes), 2)
        for _, patch in api.writes:
            self.assertEqual(patch[0], {"op": "test", "path": "/metadata/resourceVersion", "value": "1"})
        reconcile(api)
        for queue in api.queues.values():
            self.assertEqual(queue["metadata"]["annotations"], {"operator": "keep"})


if __name__ == "__main__":
    unittest.main()
