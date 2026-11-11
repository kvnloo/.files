import importlib.machinery
import importlib.util
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
loader = importlib.machinery.SourceFileLoader("fleet_backfill", str(ROOT / "scripts/fleet-backfill"))
spec = importlib.util.spec_from_loader("fleet_backfill", loader)
bf = importlib.util.module_from_spec(spec)
loader.exec_module(bf)

CFG = json.loads((ROOT / "config/fleet/backfill.json").read_text())
PAID = dict(canStart=True, creditBalanceSeconds=1385373, wallet={"balanceDollars": 0},
            keepGoing={"enabled": False}, nextStartDollars=0, last24hUsageSeconds=4,
            planIncluded={"periodEnd": "2026-11-30T22:23:28.000Z"})
NOW = 1794380000  # 2026-11-11 ~01:00 CST, ~19.9 days before periodEnd
FREE = dict(mem_available=5 << 30, mbp_free=4, mbp_pending=0, boat_ok=True, active=[], recent=set())


def queue(nominal, used, pending=0):
    return {"spec": {"resourceGroups": [{"flavors": [{"resources": [
                {"name": "cpu", "nominalQuota": nominal}, {"name": "memory", "nominalQuota": "1Gi"}]}]}]},
            "status": {"pendingWorkloads": pending, "flavorsUsage": [{"resources": [
                {"name": "cpu", "total": used}, {"name": "memory", "total": "1Gi"}]}]}}


class CohortTests(unittest.TestCase):
    def test_free_cpu_is_cohort_quota_minus_both_queues_usage(self):
        self.assertEqual(bf.cohort_free([queue("6", "2"), queue("0", "1500m", 1)]), (2.5, 1))

    def test_own_preempted_bench_unit_is_not_agent_pending_work(self):
        lanes, bench = queue("6", "6"), queue("2", "0", 1)
        lanes["metadata"], bench["metadata"] = {"name": "lanes"}, {"name": "bench-lanes"}
        self.assertEqual(bf.cohort_free([lanes, bench]), (2.0, 0))
        lanes["status"]["pendingWorkloads"] = 1
        self.assertEqual(bf.cohort_free([lanes, bench])[1], 1)


class BoatPacingTests(unittest.TestCase):
    def test_paced_to_credit_over_days_left(self):
        self.assertTrue(bf.boat_allowed(PAID, NOW))
        per_day = PAID["creditBalanceSeconds"] / ((1796077408 - NOW) / 86400)
        self.assertFalse(bf.boat_allowed(dict(PAID, last24hUsageSeconds=per_day + 1), NOW))

    def test_billing_paths_and_unknown_period_never_start(self):
        for change in (dict(wallet={"balanceDollars": 1}), dict(keepGoing={"enabled": True}),
                       dict(nextStartDollars=0.03), dict(planIncluded=None), dict(canStart=False)):
            with self.subTest(change=change):
                self.assertFalse(bf.boat_allowed(dict(PAID, **change), NOW))


class PlanTests(unittest.TestCase):
    def test_idle_cohort_and_budget_launch_both(self):
        self.assertEqual(bf.plan(CFG, **FREE), ["mbp", "boat"])

    def test_groot_floor_blocks_everything(self):
        self.assertEqual(bf.plan(CFG, **dict(FREE, mem_available=(2 << 30) - 1)), [])

    def test_agent_work_pending_or_full_cohort_yields_mbp(self):
        self.assertEqual(bf.plan(CFG, **dict(FREE, mbp_pending=1)), ["boat"])
        self.assertEqual(bf.plan(CFG, **dict(FREE, mbp_free=CFG["mbp"]["cpus"] / 2)), ["boat"])
        self.assertEqual(bf.plan(CFG, **dict(FREE, recent={"mbp"})), ["boat"])
        full = [("s", f"u{i}", "mbp") for i in range(CFG["mbp"]["max"])] + [
            ("s", f"b{i}", "boat") for i in range(CFG["boat"]["max"])]
        self.assertEqual(bf.plan(CFG, **dict(FREE, active=full)), [])


class PickTests(unittest.TestCase):
    commits = {"hermes-agent": ["a" * 40, "b" * 40], "llama.cpp": ["c" * 40]}

    def test_newest_commit_first_and_units_run_once_on_any_node(self):
        suite, commit, piece = bf.pick(CFG, "boat", self.commits, set())
        self.assertEqual((suite["name"], commit, piece), ("hermes-agent", "a" * 40, 1))
        taken = {("hermes-agent", bf.unit_key("a" * 40, 1), "mbp")}
        self.assertEqual(bf.pick(CFG, "boat", self.commits, taken)[2], 2)

    def test_boat_never_gets_mbp_only_suites_and_mbp_spreads_suites(self):
        taken = {("hermes-agent", bf.unit_key(c, i), "mbp") for c in self.commits["hermes-agent"]
                 for i in range(1, 9)}
        self.assertIsNone(bf.pick(CFG, "boat", self.commits, taken))
        active = [("hermes-agent", "x", "mbp")]
        self.assertEqual(bf.pick(CFG, "mbp", self.commits, set(), active)[0]["name"], "llama.cpp")


class JobRunnerTests(unittest.TestCase):
    def test_pytest_slice_resumes_from_markers_and_reports(self):
        with tempfile.TemporaryDirectory() as tmp:
            stage = pathlib.Path(tmp)
            (stage / ".backfill").mkdir()
            (stage / ".backfill/sync.json").write_text('{"rc": 0}')
            (stage / ".backfill/slice-1.json").write_text('{"rc": 0, "counts": {"passed": 3}}')
            (stage / "suite.json").write_text(json.dumps(
                {"name": "x", "kind": "pytest-slices", "slices": 2, "only": [1], "head": "abc"}))
            out = subprocess.run([sys.executable, str(ROOT / "scripts/fleet_backfill_job.py"), "suite.json"],
                                 cwd=stage, capture_output=True, text=True, env={**os.environ, "HOME": tmp})
            self.assertEqual(out.returncode, 0, out.stderr)
            result = json.loads(out.stdout.splitlines()[-1].split(" ", 1)[1])
            self.assertEqual(result["stages"]["slice-1"]["counts"], {"passed": 3})
            self.assertEqual(result["head"], "abc")


class ShardDoneTests(unittest.TestCase):
    def test_exit_zero_without_embeddings_is_not_done(self):
        with tempfile.TemporaryDirectory() as d:
            receipt = pathlib.Path(d)
            self.assertFalse(bf.shard_done({"exit_code": 0, "attempts": 1}, receipt))
            (receipt / "embeddings.jsonl").write_text("{}\n")
            self.assertTrue(bf.shard_done({"exit_code": 0, "attempts": 1}, receipt))

    def test_out_of_retries_is_done(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertTrue(bf.shard_done({"exit_code": 143, "attempts": bf.MAX_ATTEMPTS}, pathlib.Path(d)))


if __name__ == "__main__":
    unittest.main()


class PhoneFeeder(unittest.TestCase):
    def test_shards_cover_corpus_once(self):
        shards = bf.phone_shards(1001, 400)
        self.assertEqual(shards, [(0, 0, 400), (1, 400, 800), (2, 800, 1001)])

    def test_pick_skips_done_and_held(self):
        shards = bf.phone_shards(1200, 400)
        self.assertEqual(bf.phone_pick(shards, {0}, {1})[0], 2)
        self.assertIsNone(bf.phone_pick(shards, {0, 1}, {2}))

    def test_feeder_masks_avoid_the_bench_cores(self):
        bench = {"omarchy-phone": 0xc0, "galaxy-s22plus": 0xf0, "lenovo-tab": 0xc0}  # turbo/mobile.py BENCH_PIN
        for slot, n in CFG["phones"]["nodes"].items():
            node = n.get("node", slot)
            mask = int(n["mask"], 16)
            if not n.get("idle"):  # only SCHED_IDLE slots may share the bench cores
                self.assertEqual(mask & bench[node], 0, slot)
            self.assertLessEqual(n["threads"], bin(mask).count("1"), slot)
        ports = [(n.get("node", s), n.get("port", 18431)) for s, n in CFG["phones"]["nodes"].items()]
        self.assertEqual(len(ports), len(set(ports)))

    def test_argv_uses_native_fleet_lane_with_taskset(self):
        argv = bf.phone_argv(CFG, "lenovo-tab", "/x/0000.jsonl")
        self.assertEqual(argv[1:4], ["run", "--node", "lenovo-tab"])
        self.assertIn("/x/0000.jsonl:shard.jsonl", argv)
        i = argv.index("--")
        self.assertEqual(argv[i + 1:i + 3], ["taskset", "3f"])

    def test_idle_slot_runs_sched_idle_on_its_device(self):
        argv = bf.phone_argv(CFG, "galaxy-s22plus-idle", "/x/0003.jsonl")
        self.assertEqual(argv[1:4], ["run", "--node", "galaxy-s22plus"])
        i = argv.index("--")
        self.assertEqual(argv[i + 1:i + 6], ["chrt", "-i", "0", "taskset", "f0"])
        self.assertIn("18432", argv)
