import json
import pathlib
import sys
import unittest

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).parents[1] / "scripts"))
import fleet_boat_pool as pool  # noqa: E402

PAID = dict(canStart=True, creditBalanceSeconds=1385377, wallet={"balanceDollars": 0},
            keepGoing={"enabled": False}, nextStartDollars=0)


class SlotBudgetTests(unittest.TestCase):
    def test_included_time_buys_slots_up_to_the_cap(self):
        self.assertEqual(pool.slots(PAID), pool.MAX_SLOTS)
        self.assertEqual(pool.slots(dict(PAID, creditBalanceSeconds=2 * pool.SLOT_SECONDS + 5)), 2)
        self.assertEqual(pool.slots(dict(PAID, creditBalanceSeconds=pool.SLOT_SECONDS - 1)), 0)

    def test_any_billing_path_or_unknown_state_scales_to_zero(self):
        for change in (dict(canStart=False), dict(wallet={"balanceDollars": 5}), dict(wallet=None),
                       dict(keepGoing={"enabled": True}), dict(keepGoing=None),
                       dict(nextStartDollars=0.03), dict(creditBalanceSeconds=None),
                       dict(creditBalanceSeconds=True), {}):
            with self.subTest(change=change):
                limits = dict(PAID, **change) if change else {}
                self.assertEqual(pool.slots(limits), 0)


class SyncTests(unittest.TestCase):
    def run_sync(self, limits, capacity):
        calls = []

        def run(*args, stdin=None):
            calls.append(args)
            return json.dumps(capacity) if args[:3] == ("get", "node", pool.NODE) else ""
        return pool.sync(limits, run), calls

    def test_sync_sets_queue_quota_and_advertises_relay_capacity(self):
        quota, calls = self.run_sync(PAID, {"cpu": "20"})
        self.assertEqual(quota, pool.MAX_SLOTS)
        node = json.loads(calls[1][-1])[0]
        self.assertEqual((node["op"], node["path"]), ("add", "/status/capacity/z0.dev~1boat"))
        queue = json.loads(calls[2][-1])[0]
        self.assertEqual(queue["value"], str(pool.MAX_SLOTS))

    def test_budget_gone_drops_quota_to_zero_without_touching_capacity(self):
        quota, calls = self.run_sync(dict(PAID, creditBalanceSeconds=0), {pool.RESOURCE: str(pool.MAX_SLOTS)})
        self.assertEqual(quota, 0)
        self.assertEqual(len(calls), 2)
        self.assertEqual(json.loads(calls[1][-1])[0]["value"], "0")

    def test_quota_patch_targets_the_boat_resource(self):
        manifest = pathlib.Path(__file__).parents[1] / "config/k3s/kueue/boat.yaml"
        docs = {d["kind"]: d for d in yaml.safe_load_all(manifest.read_text()) if d}
        first = docs["ClusterQueue"]["spec"]["resourceGroups"][0]["flavors"][0]["resources"][0]
        self.assertEqual(first, {"name": pool.RESOURCE, "nominalQuota": "0"})


class JobTests(unittest.TestCase):
    def test_job_is_a_queued_relay_of_bare_boat_run(self):
        name, job = pool.job(["pytest", "-q"], src="/tmp/repo", timeout=600)
        self.assertTrue(job["spec"]["suspend"])
        self.assertEqual(job["metadata"]["labels"]["kueue.x-k8s.io/queue-name"], pool.QUEUE)
        container = job["spec"]["template"]["spec"]["containers"][0]
        self.assertEqual(container["command"][:4], [pool.BOAT, "--no-update", "run", "--type"])
        self.assertIn("--push", container["command"])
        self.assertEqual(container["command"][-3:], ["bash", "-lc", "pytest -q"])
        self.assertEqual(container["resources"]["requests"][pool.RESOURCE], "1")
        self.assertNotIn("--keep", container["command"])  # sandbox is always deleted


if __name__ == "__main__":
    unittest.main()
