"""Exercise the admission CLI against paginated GitHub accounting responses."""
import contextlib
from datetime import datetime, timedelta, timezone
import importlib.machinery
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("avrea_budget", str(ROOT / "scripts/fleet-avrea-budget"))
spec = importlib.util.spec_from_loader(loader.name, loader)
budget = importlib.util.module_from_spec(spec)
loader.exec_module(budget)


class BudgetScanTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.now = datetime.now(timezone.utc)
        self.captured = self.now - timedelta(minutes=30)
        self.snapshot = self.root / "snapshot.json"
        self.data = dict(version=1, month=self.now.strftime("%Y-%m"),
                         captured_at=self.captured.isoformat(), owner="kvnloo",
                         source="operator receipt: remaining credit", allowance_confirmed=True,
                         scope="all-account-metered-usage", post_snapshot_scope="factory-actions-only",
                         used_minutes=0, allowance_minutes=1722, max_parallel=4,
                         repositories=[{"repo": "kvnloo/fleet-runner"}], active_runs=[])
        self.snapshot.write_text(json.dumps(self.data))
        self.private = False
        self.malformed = False
        self.attempts = 1
        self.calls = []

    def response(self, argv, **kwargs):
        endpoint = urlsplit(argv[-1])
        self.calls.append(argv[-1])
        page = int(parse_qs(endpoint.query).get("page", ["1"])[0])
        if endpoint.path == "/repos/kvnloo/fleet-runner":
            value = dict(private=self.private, full_name="kvnloo/fleet-runner")
        elif endpoint.path.endswith("/runs"):
            rows = [dict(id=i, run_attempt=self.attempts, status="completed", conclusion="success",
                         created_at=(self.captured + timedelta(seconds=1)).isoformat())
                    for i in range(1, 202)]
            value = dict(total_count=202 if self.malformed else len(rows),
                         workflow_runs=rows[(page - 1) * 100:page * 100])
        elif endpoint.path.endswith("/jobs"):
            parts = endpoint.path.split("/")
            run_id, attempt = int(parts[-4]), int(parts[-2])
            start = self.captured + timedelta(minutes=1)
            value = dict(total_count=1, jobs=[dict(id=run_id * 100 + attempt,
                         labels=["avrea-ubuntu-latest"], name="verify-0", status="completed",
                         conclusion="success", started_at=start.isoformat(),
                         completed_at=(start + timedelta(seconds=1)).isoformat())])
        else:
            raise AssertionError(endpoint.path)
        return SimpleNamespace(returncode=0, stdout=json.dumps(value))

    def invoke(self, *extra):
        output = io.StringIO()
        with patch.object(budget.subprocess, "run", side_effect=self.response), contextlib.redirect_stdout(output):
            code = budget.main(["check", "--repo", "kvnloo/fleet-runner", "--runner",
                                "avrea-ubuntu-latest", "--jobs", "1", "--timeout-minutes", "1",
                                "--snapshot", str(self.snapshot), "--state-dir", str(self.root), *extra])
        return code, json.loads(output.getvalue())

    def test_default_completes_more_than_200_requests_and_reserves(self):
        code, result = self.invoke()
        self.assertEqual(code, 0)
        self.assertTrue(result["allowed"])
        self.assertEqual(result["api_requests"], 205)
        self.assertEqual(result["max_api_requests"], 2000)
        self.assertAlmostEqual(result["used_minutes"], 201 * (1 + 1 / 60))
        ledger = json.loads((self.root / "budget.json").read_text())
        self.assertEqual(ledger["reservations"][0]["id"], result["reservation_id"])

    def test_explicit_200_ceiling_refuses_without_ledger(self):
        code, result = self.invoke("--max-api-requests", "200")
        self.assertEqual(code, 2)
        self.assertFalse(result["allowed"])
        self.assertIn("after 200 requests", result["message"])
        self.assertEqual(len(self.calls), 200)
        self.assertFalse((self.root / "budget.json").exists())

    def test_every_run_attempt_is_accounted(self):
        self.attempts = 2
        code, result = self.invoke()
        self.assertEqual(code, 0)
        self.assertEqual(result["api_requests"], 406)
        self.assertAlmostEqual(result["used_minutes"], 402 * (1 + 1 / 60))

    def test_incomplete_pagination_refuses_without_ledger(self):
        self.malformed = True
        code, result = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(result["allowed"])
        self.assertFalse((self.root / "budget.json").exists())

    def test_private_scope_refuses(self):
        self.private = True
        code, result = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(result["allowed"])
        self.assertIn("not confirmed public", result["message"])
        self.assertEqual(len(self.calls), 1)

    def test_nonpositive_ceiling_refuses_before_api(self):
        code, result = self.invoke("--max-api-requests", "0")
        self.assertEqual(code, 2)
        self.assertFalse(result["allowed"])
        self.assertEqual(self.calls, [])

    def test_stale_snapshot_refuses_before_api(self):
        self.data["captured_at"] = (self.now - timedelta(hours=25)).isoformat()
        self.snapshot.write_text(json.dumps(self.data))
        code, result = self.invoke()
        self.assertEqual(code, 2)
        self.assertFalse(result["allowed"])
        self.assertEqual(self.calls, [])

    def test_build_blocks_private_local_data_before_dispatch(self):
        proc = subprocess.run([str(ROOT / "scripts/fleet-build"), "--node", "avrea", "--local-data",
                               "--", "true"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("--local-data cannot use Avrea", proc.stderr)


if __name__ == "__main__":
    unittest.main()
