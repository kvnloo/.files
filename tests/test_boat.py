"""Local policy tests; the real VM/canary receipt is in docs/fleet/BOAT.md."""
from datetime import datetime, timedelta, timezone
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

loader = SourceFileLoader("boat_wrapper", str(Path(__file__).resolve().parents[1] / "scripts/boat"))
spec = spec_from_loader(loader.name, loader)
boat = module_from_spec(spec)
loader.exec_module(boat)


class BoatPolicyTest(unittest.TestCase):
    def limits(self, **overrides):
        data = dict(accessTier="trial", billingStatus="trialing", canStart=True,
                    activeSandboxes=0, maxActiveSandboxes=2, creditUsedSeconds=0,
                    liveUsageSeconds=0, last24hUsageSeconds=0, trialComputeCapSeconds=90000)
        data.update(overrides)
        return data

    def test_trial_capacity(self):
        with patch.object(boat, "limits", return_value=self.limits(activeSandboxes=1)):
            boat.check_capacity()
        with patch.object(boat, "limits", return_value=self.limits(activeSandboxes=2)):
            with self.assertRaisesRegex(boat.BoatError, "Concurrency cap"):
                boat.check_capacity()

    def test_trial_budget_reserves_live_leases(self):
        with patch.object(boat, "limits", return_value=self.limits(
                activeSandboxes=1, last24hUsageSeconds=9700)):
            with self.assertRaisesRegex(boat.BoatError, "budget"):
                boat.check_capacity()

    def test_total_trial_cap_is_independent_of_daily_budget(self):
        with patch.object(boat, "limits", return_value=self.limits(creditUsedSeconds=89900)):
            with self.assertRaisesRegex(boat.BoatError, "Total trial"):
                boat.check_capacity()

    def test_old_usage_does_not_consume_daily_budget(self):
        with patch.object(boat, "limits", return_value=self.limits(creditUsedSeconds=50000)):
            boat.check_capacity()

    def test_provider_controls_concurrency(self):
        with patch.object(boat, "limits", return_value=self.limits(
                activeSandboxes=3, maxActiveSandboxes=4)):
            boat.check_capacity()

    def test_paid_account_is_not_implicit_authorization(self):
        with patch.object(boat, "limits", return_value=self.limits(accessTier="standard")):
            with self.assertRaisesRegex(boat.BoatError, "Trial-only"):
                boat.check_capacity()

    def test_account_keys_cannot_be_requested(self):
        for name in ("BOAT_API_KEY", "BWS_ACCESS_TOKEN", "UNAPPROVED_KEY"):
            with self.subTest(name=name), patch.object(boat.subprocess, "run") as run:
                with self.assertRaisesRegex(boat.BoatError, "not allowlisted"):
                    boat.selected_secrets([name])
                run.assert_not_called()

    def test_dummy_needs_no_real_credential_lookup(self):
        with patch.object(boat.subprocess, "run") as run:
            selected = boat.selected_secrets([], dummy=True)
        self.assertEqual(list(selected), ["BOAT_SMOKE_DUMMY"])
        self.assertTrue(selected["BOAT_SMOKE_DUMMY"].startswith("omp-dummy-"))
        run.assert_not_called()

    def test_reaper_deletes_only_expired_omp_resources(self):
        now = datetime.now(timezone.utc)
        resources = [
            dict(id="old", name="omp-old", createdAt=(now-timedelta(seconds=601)).isoformat()),
            dict(id="fresh", name="omp-fresh", createdAt=now.isoformat()),
            dict(id="user", name="personal", createdAt=(now-timedelta(days=1)).isoformat()),
        ]
        with patch.object(boat, "inventory", return_value=iter(resources)), \
                patch.object(boat, "delete") as delete:
            boat.reap()
        delete.assert_called_once_with("old")

    def test_delete_refuses_other_resources(self):
        with patch.object(boat, "api", return_value={"sandbox": {"name": "personal"}}) as api:
            with self.assertRaisesRegex(boat.BoatError, "Refusing"):
                boat.delete("bx_23456789")
        self.assertEqual(api.call_count, 1)

    def test_failed_command_still_deletes_snapshotless_lease(self):
        calls = []
        def api(path, method="GET", body=None, headers=None):
            calls.append((path, method, body))
            if path == "/sandboxes":
                return {"sandbox": {"id": "bx_23456789"}}
            if path.endswith("/commands"):
                return {"exitCode": 17, "stdout": "", "stderr": ""}
            if path.endswith("/usage"):
                return {"seconds": 1, "dollars": .00001, "sandboxType": "small"}
            self.fail("Unexpected API route " + path)
        args = SimpleNamespace(name="failed-job", type="small", action="run", secret=[],
                               dummy_secret_test=False, command=["false"])
        with patch.object(boat, "api", side_effect=api), patch.object(boat, "reap"), \
                patch.object(boat, "check_capacity"), patch.object(boat, "wait_ready"), \
                patch.object(boat, "creation_lock", boat.contextlib.nullcontext), \
                patch.object(boat, "delete") as delete, patch.object(boat.signal, "signal"):
            self.assertEqual(boat.lease(args), 17)
        body = calls[0][2]
        self.assertTrue(body["noEnv"])
        self.assertFalse(body["snapshots"])
        self.assertFalse(body["monitoring"])
        self.assertLessEqual(body["ttlSeconds"], 600)
        self.assertTrue(body["name"].startswith("omp-"))
        delete.assert_called_once_with("bx_23456789")


if __name__ == "__main__":
    unittest.main()
