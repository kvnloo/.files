"""Isolated accounting fixtures only: no network, build, browser or real dispatch."""
import contextlib
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import importlib.machinery
import importlib.util
import io
import json
import multiprocessing
from pathlib import Path
import tempfile
import time
from types import SimpleNamespace
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / "scripts/fleet-avrea-budget"
loader = importlib.machinery.SourceFileLoader("fleet_avrea_budget_under_test", str(PATH))
spec = importlib.util.spec_from_loader(loader.name, loader)
budget = importlib.util.module_from_spec(spec)
loader.exec_module(budget)
NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
CAPTURED = NOW - timedelta(hours=1)
REPO = "kvnloo/fleet-runner"
LABEL = "avrea-ubuntu-latest-2-vcpu"


def stamp(value):
    return value.isoformat()


def snapshot(**changes):
    return {"version": 1, "month": "2026-10", "captured_at": stamp(CAPTURED),
            "owner": "kvnloo", "source": "isolated billing fixture",
            "allowance_confirmed": True, "scope": "all-account-metered-usage",
            "post_snapshot_scope": "factory-actions-only", "used_minutes": 100,
            "repositories": [{"repo": REPO}], "active_runs": [],
            "max_parallel": 2, **changes}


def run(run_id=1, **changes):
    return {"id": run_id, "run_attempt": 1, "status": "completed", "updated_at": stamp(NOW),
            "created_at": stamp(CAPTURED + timedelta(minutes=1)), **changes}


def job(job_id=1, **changes):
    return {"id": job_id, "labels": [LABEL], "status": "completed", "conclusion": "success",
            "started_at": stamp(CAPTURED + timedelta(minutes=5)),
            "completed_at": stamp(CAPTURED + timedelta(minutes=15)), **changes}


class API(budget.GitHub):
    def __init__(self, routes=None):
        self.calls = []
        self.routes = {f"/repos/{REPO}": {"full_name": REPO, "private": False},
            f"/repos/{REPO}/actions/runs?per_page=100&page=1": {"total_count": 0, "workflow_runs": []}}
        self.routes.update(routes or {})

    def get(self, endpoint):
        self.calls.append(endpoint)
        # Keep fixture keys readable while asserting a cutoff exists on run lists.
        if "?created=" in endpoint:
            if not endpoint.split("?created=", 1)[1].startswith("%3E%3D"):
                raise AssertionError("missing inclusive snapshot cutoff")
            endpoint = endpoint.split("?created=", 1)[0] + "?" + endpoint.split("&", 1)[1]
        if endpoint not in self.routes:
            raise AssertionError(f"unexpected network path: {endpoint}")
        return self.routes[endpoint]


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return NOW


def concurrent_check(args, event, queue):
    # forked fixture shares only real on-disk lock/ledger, not Python memory.
    class SlowAPI(API):
        def get(self, endpoint):
            time.sleep(0.02)
            return super().get(endpoint)
    with patch.object(budget, "GitHub", return_value=SlowAPI()):
        event.wait(5)
        try:
            queue.put(budget.check(args, NOW)[1])
        except Exception as error:
            queue.put(type(error).__name__)


class BudgetTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.snapshot = self.root / "snapshot.json"
        self.write_snapshot()
        self.args = SimpleNamespace(repo=REPO, runner=LABEL, jobs=1, timeout_minutes=10,
                                    parallel=1, snapshot=str(self.snapshot), state_dir=str(self.root / "state"),
                                    max_api_requests=200)

    def write_snapshot(self, **changes):
        self.snapshot.write_text(json.dumps(snapshot(**changes)))

    def check(self, api=None):
        with patch.object(budget, "GitHub", return_value=api or API()):
            return budget.check(self.args, NOW)

    def cli(self, *args):
        output = io.StringIO()
        with patch.object(budget, "datetime", Clock), contextlib.redirect_stdout(output):
            code = budget.main(list(args))
        return code, json.loads(output.getvalue())

    def state(self):
        return json.loads((Path(self.args.state_dir) / "budget.json").read_text())

    def api_with_runs(self, runs, jobs_by_attempt):
        routes = {f"/repos/{REPO}/actions/runs?per_page=100&page=1": {"total_count": len(runs), "workflow_runs": runs}}
        for (run_id, attempt), jobs in jobs_by_attempt.items():
            routes[f"/repos/{REPO}/actions/runs/{run_id}/attempts/{attempt}/jobs?per_page=100&page=1"] = {"total_count": len(jobs), "jobs": jobs}
        return API(routes)

    def test_rate_table_and_pinned_aliases(self):
        expected = {"avrea-ubuntu-latest": "1", "avrea-ubuntu-latest-1-vcpu": ".5",
                    "avrea-ubuntu-latest-4-vcpu-8gb": "1.5", "avrea-ubuntu-latest-4-vcpu": "2",
                    "avrea-ubuntu-22.04-8-vcpu-16gb": "3", "avrea-ubuntu-latest-8-vcpu": "4",
                    "avrea-ubuntu-latest-32-vcpu": "16", "avrea-ubuntu-24.04-arm-1-vcpu": "1.5",
                    "avrea-ubuntu-latest-arm-4-vcpu-8gb": "4.5", "avrea-ubuntu-latest-arm-8-vcpu-16gb": "9",
                    "avrea-ubuntu-latest-arm-16-vcpu": "24", "avrea-macos-26-8-vcpu": "20",
                    "avrea-macos-26-16-vcpu": "40", "avrea-windows-2025-2-vcpu": "2",
                    "avrea-windows-2025-16-vcpu": "16"}
        for label, ratio in expected.items():
            with self.subTest(label=label):
                self.assertEqual(budget.runner_multiplier(label), Decimal(ratio))
        code, data = self.cli("rates")
        self.assertEqual(code, 0)
        self.assertEqual(data["base_dollars_per_minute"], .004)
        self.assertEqual(data["runners"]["avrea-ubuntu-latest-4-vcpu-8gb"]["dollars_per_minute"], .006)
        for label in ("ubuntu-latest", "avrea-unknown", "avrea-ubuntu-22.04-arm-4-vcpu", "avrea-ubuntu-latest-2-vcpu-8gb", None):
            with self.subTest(label=label), self.assertRaises(budget.AccountingError):
                budget.runner_multiplier(label)

    def test_missing_snapshot_fails_before_any_scan_and_never_claims_zero(self):
        self.snapshot.unlink()
        with patch.object(budget, "GitHub", side_effect=AssertionError("scan before baseline")):
            code, data = self.cli("check", "--repo", REPO, "--runner", LABEL, "--jobs", "1", "--timeout-minutes", "5",
                                  "--snapshot", str(self.snapshot), "--state-dir", self.args.state_dir)
        self.assertEqual(code, 2)
        self.assertFalse(data["allowed"])
        self.assertIsNone(data["used_minutes"])
        self.assertFalse((Path(self.args.state_dir) / "budget.json").exists())

    def test_invalid_snapshot_fail_closed(self):
        cases = [{"captured_at": stamp(NOW - timedelta(days=1, seconds=1))},
                 {"captured_at": stamp(NOW + timedelta(seconds=1))}, {"month": "2026-09"},
                 {"scope": "one-repo"}, {"post_snapshot_scope": "unknown"}, {"allowance_confirmed": False},
                 {"allowance_confirmed": 1}, {"source": ""}, {"used_minutes": -1}, {"used_minutes": "NaN"},
                 {"allowance_minutes": 0}, {"max_parallel": None}, {"max_parallel": True},
                 {"captured_at": "2026-10-23T01:00:00"}]
        for changes in cases:
            with self.subTest(changes=changes):
                self.write_snapshot(**changes)
                with self.assertRaises(budget.AccountingError):
                    self.check()

    def test_24_hour_baseline_default_allowance_and_source(self):
        self.write_snapshot(captured_at=stamp(NOW - timedelta(days=1)))
        data, code = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(data["allowance_minutes"], 3000)
        self.assertEqual(data["source"]["snapshot"], "isolated billing fixture")
        self.assertEqual(data["source"]["public_repositories"], 1)
        self.assertEqual(data["max_parallel"], 2)
        self.assertEqual(data["reserved_minutes"], 10)
        self.assertTrue(data["reservation_id"])

    def test_alert_80_stop_95_include_requested_reservation(self):
        for index, (used, allowed, fragment) in enumerate(((2389, True, "allowed"), (2390, True, "80%"),
                                                         (2839, True, "80%"), (2840, False, "95%"))):
            with self.subTest(used=used):
                self.args.state_dir = str(self.root / f"state{index}")
                self.write_snapshot(used_minutes=used)
                data, code = self.check()
                self.assertEqual(code, 0 if allowed else 75)
                self.assertEqual(data["allowed"], allowed)
                self.assertIn(fragment, data["message"])
                self.assertEqual(len(self.state()["reservations"]), int(allowed))

    def test_nondefault_allowance_and_rate_weighted_request(self):
        self.write_snapshot(allowance_minutes=1000, used_minutes=100)
        self.args.runner = "avrea-ubuntu-latest-arm-4-vcpu-8gb"
        self.args.jobs = 2
        self.args.timeout_minutes = 20
        data, code = self.check()
        self.assertEqual(code, 0)
        self.assertEqual(data["requested_minutes"], 180)
        self.assertEqual(data["percent"], 28)

    def test_invalid_request_inputs_and_parallel_cap_do_not_reserve(self):
        for key, value in (("jobs", 0), ("timeout_minutes", 361), ("parallel", 0), ("repo", "other/private")):
            original = getattr(self.args, key)
            with self.subTest(key=key), self.assertRaises(budget.AccountingError):
                setattr(self.args, key, value)
                self.check()
            setattr(self.args, key, original)
        self.args.parallel = 3
        with patch.object(budget, "GitHub", side_effect=AssertionError("scan despite cap")):
            data, code = budget.check(self.args, NOW)
        self.assertEqual(code, 75)
        self.assertEqual(data["max_parallel"], 2)
        self.assertFalse((Path(self.args.state_dir) / "budget.json").exists())

    def test_completed_interval_clipped_to_snapshot_and_all_attempts_count(self):
        first = job(started_at=stamp(CAPTURED - timedelta(minutes=5)), completed_at=stamp(CAPTURED + timedelta(minutes=5)))
        second = job(2, labels=["avrea-ubuntu-latest-4-vcpu-8gb"])
        api = self.api_with_runs([run(run_attempt=2)], {(1, 1): [first], (1, 2): [second]})
        data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["used_minutes"], 100 + 6 + 11 * 1.5)
        self.assertTrue(any("attempts/1/" in path for path in api.calls))
        self.assertTrue(any("attempts/2/" in path for path in api.calls))

    def test_prebaseline_active_run_is_fetched_by_explicit_id(self):
        self.write_snapshot(active_runs=[{"repo": REPO, "run_id": 1}])
        api = API({f"/repos/{REPO}/actions/runs/1": run(created_at="2025-01-01T00:00:00Z"),
                   f"/repos/{REPO}/actions/runs/1/attempts/1/jobs?per_page=100&page=1": {"total_count": 1, "jobs": [job()]}})
        data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["used_minutes"], 111)

    def test_unknown_running_jobs_accrue_and_queued_local_budget_is_reserved(self):
        jobs = [job(status="in_progress", completed_at=None, started_at=stamp(NOW - timedelta(minutes=2))),
                job(2, status="queued", started_at=None, completed_at=None)]
        api = self.api_with_runs([run(status="in_progress")], {(1, 1): jobs})
        with patch.object(budget, "monotonic", return_value=100.0):
            data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["used_minutes"], 103)
        self.assertEqual(data["reserved_minutes"], 10)
        self.assertEqual(data["source"]["active_jobs"], 2)
        self.assertIn("unknown future runtime not reserved", data["message"])
        self.assertEqual(len(self.state()["reservations"]), 1)

    def test_every_explicit_factory_repository_is_counted(self):
        other = "kvnloo/another-public"
        self.write_snapshot(repositories=[{"repo": REPO}, {"repo": other}])
        api = API({f"/repos/{other}": {"full_name": other, "private": False},
            f"/repos/{other}/actions/runs?per_page=100&page=1": {"total_count": 1, "workflow_runs": [run()]},
            f"/repos/{other}/actions/runs/1/attempts/1/jobs?per_page=100&page=1": {"total_count": 1, "jobs": [job()]}})
        data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["used_minutes"], 111)
        self.assertEqual(data["source"]["public_repositories"], 2)

    def test_public_run_and_job_pagination_is_complete(self):
        endpoint = f"/repos/{REPO}/actions/runs"
        runs = [run(i) for i in range(1, 101)]
        api = API({endpoint + "?per_page=100&page=1": {"total_count": 101, "workflow_runs": runs},
                   endpoint + "?per_page=100&page=2": {"total_count": 101, "workflow_runs": [run(101)]},
                   f"{endpoint}/101/attempts/1/jobs?per_page=100&page=1": {"total_count": 101, "jobs": [job(i) for i in range(1, 101)]},
                   f"{endpoint}/101/attempts/1/jobs?per_page=100&page=2": {"total_count": 101, "jobs": [job(101)]}})
        api.routes.update({f"{endpoint}/{i}/attempts/1/jobs?per_page=100&page=1":
                           {"total_count": 0, "jobs": []} for i in range(1, 101)})
        data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["used_minutes"], 1211)
        self.assertEqual(sum("page=2" in path for path in api.calls), 2)

    def test_workflow_filter_does_not_enumerate_the_account(self):
        self.write_snapshot(repositories=[{"repo": REPO, "workflow": "verify.yml"}])
        api = API({f"/repos/{REPO}/actions/workflows/verify.yml/runs?per_page=100&page=1":
                   {"total_count": 0, "workflow_runs": []}})
        data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["source"]["public_repositories"], 1)
        self.assertEqual(len(api.calls), 2)
        self.assertTrue(any("/workflows/verify.yml/" in call for call in api.calls))
        self.assertFalse(any("/users/" in call for call in api.calls))

    def test_incomplete_or_unknown_job_evidence_fails_closed(self):
        cases = [job(labels=["avrea-future-size"]), job(labels=[]), job(labels=["self-hosted"]),
                 job(completed_at=None), job(started_at=stamp(NOW), completed_at=stamp(CAPTURED)),
                 job(status="unknown"), job(labels=[LABEL, "avrea-ubuntu-latest"])]
        for bad in cases:
            with self.subTest(job=bad), self.assertRaises(budget.AccountingError):
                self.check(self.api_with_runs([run()], {(1, 1): [bad]}))
        bad_api = API({f"/repos/{REPO}/actions/runs?per_page=100&page=1": {"total_count": 2, "workflow_runs": [run()]}})
        with self.assertRaises(budget.AccountingError):
            self.check(bad_api)
        bad_api = API({f"/repos/{REPO}": {"full_name": REPO, "private": True}})
        with self.assertRaises(budget.AccountingError):
            self.check(bad_api)

    def test_skipped_and_github_hosted_jobs_are_not_charged(self):
        api = self.api_with_runs([run()], {(1, 1): [job(labels=["ubuntu-latest"]),
            job(2, labels=[LABEL], conclusion="skipped", started_at=None, completed_at=None)]})
        data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["used_minutes"], 100)

    def test_request_limit_api_failure_and_malformed_json_fail_closed(self):
        api = budget.GitHub(1)
        with patch.object(budget.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout="[]")) as call:
            self.assertEqual(api.get("/fixture"), [])
            self.assertEqual(call.call_args.args[0], ["gh", "api", "--hostname", "github.com", "/fixture"])
            with self.assertRaises(budget.AccountingError):
                api.get("/too-many")
        for proc in (SimpleNamespace(returncode=403, stdout="secret not displayed"), SimpleNamespace(returncode=0, stdout="not JSON")):
            with patch.object(budget.subprocess, "run", return_value=proc), self.assertRaises(budget.AccountingError):
                budget.GitHub().get("/fixture")
        with patch.object(budget, "GitHub", return_value=budget.GitHub(1)), \
             patch.object(budget.subprocess, "run", return_value=SimpleNamespace(returncode=1, stdout="")):
            code, data = self.cli("check", "--repo", REPO, "--runner", LABEL, "--jobs", "1", "--timeout-minutes", "10",
                                  "--snapshot", str(self.snapshot), "--state-dir", self.args.state_dir)
        self.assertEqual(code, 2)
        self.assertIsNone(data["used_minutes"])
        self.assertFalse((Path(self.args.state_dir) / "budget.json").exists())

    def test_durable_reservations_never_silently_expire_and_corruption_is_error(self):
        first, _ = self.check()
        second, _ = self.check()
        self.assertEqual(second["reserved_minutes"], 20)
        self.assertNotEqual(first["reservation_id"], second["reservation_id"])
        data = self.state()
        data["reservations"][0]["minutes"] = "0"
        (Path(self.args.state_dir) / "budget.json").write_text(json.dumps(data))
        with self.assertRaises(budget.AccountingError):
            self.check()

    def test_concurrent_checks_cannot_both_spend_last_allowance(self):
        self.write_snapshot(used_minutes=2835)
        context = multiprocessing.get_context("fork")
        event, queue = context.Event(), context.Queue()
        children = [context.Process(target=concurrent_check, args=(self.args, event, queue)) for _ in range(2)]
        try:
            for child in children:
                child.start()
            event.set()
            codes = [queue.get(timeout=10) for _ in children]
            for child in children:
                child.join(timeout=10)
                self.assertEqual(child.exitcode, 0)
            self.assertEqual(sorted(codes), [0, 75])
            self.assertEqual(len(self.state()["reservations"]), 1)
        finally:
            for child in children:
                if child.is_alive():
                    child.terminate()
                    child.join()
            queue.close()

    def test_release_requires_explicit_undispatched_assertion(self):
        data, _ = self.check()
        identity = data["reservation_id"]
        code, _ = self.cli("release", "--reservation-id", identity, "--state-dir", self.args.state_dir)
        self.assertEqual(code, 2)
        self.assertEqual(len(self.state()["reservations"]), 1)
        code, _ = self.cli("release", "--reservation-id", identity, "--undispatched", "--state-dir", self.args.state_dir)
        self.assertEqual(code, 0)
        self.assertEqual(self.state()["reservations"], [])

    def test_settle_retains_charge_until_exact_terminal_evidence(self):
        data, _ = self.check()
        identity = data["reservation_id"]
        code, _ = self.cli("settle", "--reservation-id", identity, "--run-id", "1", "--state-dir", self.args.state_dir)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.state()["reservations"]), 1)
        code, _ = self.cli("release", "--reservation-id", identity, "--undispatched", "--state-dir", self.args.state_dir)
        self.assertEqual(code, 2)
        api = self.api_with_runs([run(status="in_progress", created_at=stamp(NOW))], {(1, 1): [job(status="queued")]})
        self.args.jobs = 10
        self.args.timeout_minutes = 360
        _, code = self.check(api)
        self.assertEqual(code, 75)
        self.assertEqual(len(self.state()["reservations"]), 1)
        self.args.jobs = 1
        self.args.timeout_minutes = 10
        api = self.api_with_runs([run(created_at=stamp(NOW))], {(1, 1): [job(started_at=stamp(NOW), completed_at=stamp(NOW))]})
        data, code = self.check(api)
        self.assertEqual(code, 0)
        self.assertEqual(data["reserved_minutes"], 10)
        self.assertNotIn(identity, [item["id"] for item in self.state()["reservations"]])

    def test_wrong_count_label_or_older_run_cannot_settle(self):
        data, _ = self.check()
        identity = data["reservation_id"]
        self.cli("settle", "--reservation-id", identity, "--run-id", "1", "--state-dir", self.args.state_dir)
        for candidate, jobs in ((run(), [job()]), (run(created_at=stamp(NOW)), [job(labels=["avrea-ubuntu-latest-1-vcpu"])]),
                                (run(created_at=stamp(NOW)), [job(), job(2)])):
            with self.subTest(run=candidate, jobs=jobs):
                _, code = self.check(self.api_with_runs([candidate], {(1, 1): jobs}))
                self.assertEqual(code, 0)
                self.assertIn(identity, [item["id"] for item in self.state()["reservations"]])

    def test_avrea_validate_preflight_is_charged_but_not_a_command_job(self):
        self.args.runner = "avrea-ubuntu-latest-4-vcpu"
        self.args.overhead_minutes = 2
        first, _ = self.check()
        identity = first["reservation_id"]
        self.assertEqual(first["requested_minutes"], 22)
        self.assertEqual(self.state()["reservations"][0]["overhead_minutes"], "2")
        self.cli("settle", "--reservation-id", identity, "--run-id", "1", "--state-dir", self.args.state_dir)
        jobs = [job(1, name="validate", started_at=stamp(NOW), completed_at=stamp(NOW)),
                job(2, name="verify (0)", labels=[self.args.runner], started_at=stamp(NOW), completed_at=stamp(NOW))]
        data, code = self.check(self.api_with_runs([run(created_at=stamp(NOW), conclusion="success")], {(1, 1): jobs}))
        self.assertEqual(code, 0)
        self.assertEqual(data["used_minutes"], 103)
        self.assertEqual(data["reserved_minutes"], 22)
        self.assertNotIn(identity, [item["id"] for item in self.state()["reservations"]])

    def test_incomplete_terminal_runs_settle_only_for_cancelled_or_failed_outcomes(self):
        cases = [
            ("cancelled", [], True),
            ("cancelled", [job(name="validate", labels=["ubuntu-latest"], conclusion="cancelled",
                               started_at=None, completed_at=stamp(NOW))], True),
            ("cancelled", [job(name="validate", conclusion="cancelled", started_at=None,
                               completed_at=stamp(NOW))], True),
            ("failure", [job(name="verify (0)", started_at=stamp(NOW), completed_at=stamp(NOW))], True),
            ("success", [job(name="verify (0)", started_at=stamp(NOW), completed_at=stamp(NOW))], False),
            ("failure", [job(name="verify (0)", labels=["avrea-ubuntu-latest-1-vcpu"],
                             started_at=stamp(NOW), completed_at=stamp(NOW))], False),
        ]
        self.args.jobs = 2
        for index, (conclusion, jobs, should_settle) in enumerate(cases):
            with self.subTest(conclusion=conclusion, jobs=jobs):
                self.args.state_dir = str(self.root / f"terminal{index}")
                first, _ = self.check()
                identity = first["reservation_id"]
                self.cli("settle", "--reservation-id", identity, "--run-id", "1", "--state-dir", self.args.state_dir)
                api = self.api_with_runs([run(created_at=stamp(NOW), conclusion=conclusion)], {(1, 1): jobs})
                data, code = self.check(api)
                self.assertEqual(code, 0)
                self.assertEqual(data["reserved_minutes"], 20 if should_settle else 40)
                self.assertEqual(identity not in [item["id"] for item in self.state()["reservations"]], should_settle)
                if conclusion == "cancelled":
                    self.assertEqual(data["used_minutes"], 100)

    def test_validate_preflight_must_be_terminal_before_settlement(self):
        for index, labels in enumerate(([LABEL], ["ubuntu-latest"])):
            with self.subTest(labels=labels):
                self.args.state_dir = str(self.root / f"pending-preflight{index}")
                first, _ = self.check()
                identity = first["reservation_id"]
                self.cli("settle", "--reservation-id", identity, "--run-id", "1", "--state-dir", self.args.state_dir)
                jobs = [job(1, name="validate", labels=labels, status="queued", conclusion=None,
                            started_at=None, completed_at=None),
                        job(2, name="verify (0)", started_at=stamp(NOW), completed_at=stamp(NOW))]
                api = self.api_with_runs([run(created_at=stamp(NOW), conclusion="success")], {(1, 1): jobs})
                _, code = self.check(api)
                self.assertEqual(code, 0)
                self.assertIn(identity, [item["id"] for item in self.state()["reservations"]])

    def test_job_timestamps_use_observation_time_after_slow_api_calls(self):
        for index, (status, start_seconds, end_seconds, expected_used) in enumerate((
                ("completed", 2, 15, 101 + 13 / 60),
                ("in_progress", 12, None, 101 + 6 / 60),
                ("completed", 2, 19, 101 + 17 / 60))):
            with self.subTest(status=status, end_seconds=end_seconds):
                self.args.state_dir = str(self.root / f"slow-api{index}")
                clock = [100.0]
                candidate = job(status=status, started_at=stamp(NOW + timedelta(seconds=start_seconds)),
                                completed_at=stamp(NOW + timedelta(seconds=end_seconds)) if end_seconds is not None else None)
                api = self.api_with_runs([run()], {(1, 1): [candidate]})
                get = api.get

                def delayed_get(endpoint):
                    evidence = get(endpoint)
                    if "/jobs?" in endpoint:
                        clock[0] = 118.0
                    return evidence

                with patch.object(api, "get", side_effect=delayed_get), \
                     patch.object(budget, "monotonic", side_effect=lambda: clock[0]):
                    data, code = self.check(api)
                self.assertEqual(code, 0)
                self.assertAlmostEqual(data["used_minutes"], expected_used)

    def test_slow_scan_still_rejects_genuinely_future_or_reversed_intervals(self):
        for candidate in (
                job(started_at=stamp(NOW + timedelta(seconds=2)), completed_at=stamp(NOW + timedelta(seconds=20))),
                job(status="in_progress", started_at=stamp(NOW + timedelta(seconds=20)), completed_at=None),
                job(started_at=stamp(NOW + timedelta(seconds=15)), completed_at=stamp(NOW + timedelta(seconds=2)))):
            with self.subTest(candidate=candidate):
                clock = [100.0]
                api = self.api_with_runs([run()], {(1, 1): [candidate]})
                get = api.get

                def delayed_get(endpoint):
                    evidence = get(endpoint)
                    if "/jobs?" in endpoint:
                        clock[0] = 118.0
                    return evidence

                with patch.object(api, "get", side_effect=delayed_get), \
                     patch.object(budget, "monotonic", side_effect=lambda: clock[0]), \
                     self.assertRaises(budget.AccountingError):
                    self.check(api)

    def test_month_rollover_drops_old_ledger_but_requires_current_snapshot(self):
        self.check()
        path = Path(self.args.state_dir) / "budget.json"
        state = budget.load_state(path, "2026-11")
        self.assertEqual(state["reservations"], [])
        with self.assertRaises(budget.AccountingError):
            budget.snapshot_at(self.snapshot, datetime(2026, 11, 1, tzinfo=timezone.utc))
        with self.assertRaises(budget.AccountingError):
            budget.load_state(path, "2026-09")

    def test_cli_invalid_arguments_are_json_exit_two(self):
        code, data = self.cli("check", "--jobs", "not-an-int")
        self.assertEqual(code, 2)
        self.assertFalse(data["allowed"])
        self.assertIsNone(data["percent"])


if __name__ == "__main__":
    unittest.main()
