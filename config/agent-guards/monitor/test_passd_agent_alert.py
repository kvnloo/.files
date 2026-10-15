import contextlib
import copy
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch


SCRIPT = Path(__file__).with_name("passd-agent-alert.py")
FIXTURES = SCRIPT.parent / "fixtures"
spec = importlib.util.spec_from_file_location("passd_agent_alert", SCRIPT)
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.event = monitor.records(json.loads((FIXTURES / "approved.json").read_text()))[0]
        self.leases = monitor.load_leases(FIXTURES / "approvals.jsonl")

    def flags(self, **changes):
        event = copy.deepcopy(self.event)
        event.update(changes)
        return monitor.summarize([event], self.leases, {"broker"})["event_flag_counts"][0]

    def test_approved(self):
        self.assertEqual(self.flags(), {})

    def test_unapproved(self):
        self.assertEqual(self.flags(Reason="passd capability=cap-1 lease=missing"), {"no_approved_lease": 1})

    def test_missing_and_unstructured_reason(self):
        for reason in (None, "", "plain reason", {"secret": "CANARY"}, "passd lease=lease-1"):
            with self.subTest(reason=reason):
                self.assertEqual(self.flags(Reason=reason), {"unstructured_reason": 1})

    def test_time_window(self):
        for when in ("2026-10-15T11:59:59Z", "2026-10-15T12:01:00Z", "2026-10-15T12:01:01Z"):
            self.assertEqual(self.flags(create_time=when), {"outside_lease_validity": 1})
        self.assertEqual(self.flags(create_time="2026-10-15T12:00:00Z"), {})

    def test_invalid_time(self):
        for value in (None, "bad", "2026-10-15T12:00:30", float("nan"), True):
            self.assertEqual(self.flags(create_time=value), {"invalid_time": 1})

    def test_unknown_agent(self):
        self.assertEqual(self.flags(agent={"id": "unknown"}), {"unknown_agent": 1, "lease_agent_mismatch": 1})

    def test_missing_agent_item(self):
        self.assertIn("unknown_agent", self.flags(agent=None))
        self.assertIn("missing_item", self.flags(item=None))

    def test_capability_and_item_mismatch(self):
        self.assertEqual(self.flags(Reason="passd capability=cap-2 lease=lease-1"), {"capability_mismatch": 1})
        self.assertEqual(self.flags(item="item-2"), {"item_mismatch": 1})

    def test_revoked(self):
        self.assertEqual(self.flags(Reason="passd capability=cap-1 lease=lease-revoked"), {"outside_lease_validity": 1})

    def test_native_passd_audit(self):
        leases = monitor.load_leases(FIXTURES / "native-audit.jsonl")
        self.assertEqual(leases["native-1"]["end"] - leases["native-1"]["start"], 20)
        self.assertIsNone(leases["native-1"]["agent"])

    def test_approximate_audit_times_rejected(self):
        with self.assertRaises(ValueError):
            monitor.load_leases(FIXTURES / "unenriched-audit.jsonl")

    def test_schema_aliases_and_counts_only(self):
        events = [
            {"reason": "passd capability=cap-1 lease=lease-1", "timestamp": 1792065630000,
             "item_id": "item-1", "agent_id": "broker", "type": "view"},
            {"reason": None, "time": "bad", "item": "CANARY_SECRET_ITEM", "agent": "CANARY_SECRET_AGENT", "action": "CANARY_SECRET_ACTION"},
        ]
        summary = monitor.summarize(events, self.leases, {"broker"})
        self.assertEqual(summary["counts"]["events"], 2)
        self.assertEqual(summary["counts"]["flagged_events"], 1)
        self.assertEqual(len(summary["event_flag_counts"]), 2)
        self.assertNotIn("CANARY", json.dumps(summary))
        self.assertNotIn("item-1", json.dumps(summary))

    def run_cli(self, fixture="approved", *extra):
        return subprocess.run([sys.executable, str(SCRIPT), "--agent", "broker", "--known-agent", "broker",
            "--pass-cli", str(FIXTURES / "fake-pass-cli.py"), "--session-dir", "fixture-session",
            "--audit-jsonl", str(FIXTURES / "approvals.jsonl"), *extra],
            env=dict(os.environ, GUARD_MONITOR_FIXTURE=fixture), text=True, capture_output=True, check=False)

    def test_fake_binary_cli(self):
        result = self.run_cli()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["counts"]["flagged_events"], 0)
        self.assertNotIn("CANARY", result.stdout + result.stderr)

    def test_empty(self):
        self.assertEqual(self.run_cli("empty").returncode, 0)

    def test_flagged_cli_counts_each_event(self):
        result = self.run_cli("flagged")
        self.assertEqual(result.returncode, 1)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["counts"]["flagged_events"], 2)
        self.assertEqual(summary["event_flag_counts"], [
            {"unknown_agent": 1, "unstructured_reason": 1}, {"outside_lease_validity": 1}])
        self.assertNotIn("CANARY", result.stdout + result.stderr)

    def test_subprocess_and_schema_errors(self):
        for fixture in ("failure", "malformed", "unknown-schema"):
            result = self.run_cli(fixture)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(json.loads(result.stdout), {"counts": {"collection_errors": 1}})
            self.assertNotIn("CANARY", result.stdout + result.stderr)

    def test_bad_audit_and_missing_binary(self):
        for extra in (("--audit-jsonl", str(FIXTURES / "bad-audit.jsonl")), ("--pass-cli", "/nonexistent-fixture")):
            result = self.run_cli("approved", *extra)
            self.assertEqual(result.returncode, 1)
            self.assertNotIn("CANARY", result.stdout + result.stderr)

    def test_truncation_alert(self):
        result = self.run_cli("approved", "--limit", "1")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(json.loads(result.stdout)["counts"]["possibly_truncated_window"], 1)
        self.assertTrue(result.stderr)

    def test_notification_is_static_argv(self):
        calls = []
        def fake_run(argv, **kwargs):
            calls.append(argv)
            if len(calls) == 1:
                return subprocess.CompletedProcess(argv, 0, "not JSON", "CANARY_SECRET")
            return subprocess.CompletedProcess(argv, 0)
        with patch.object(monitor.subprocess, "run", side_effect=fake_run), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            code = monitor.main(["--agent", "broker", "--known-agent", "broker", "--session-dir", "fixture-session",
                "--audit-jsonl", str(FIXTURES / "approvals.jsonl"), "--notify", "--alert-command", 'fixture-alert "two words"'])
        self.assertEqual(code, 1)
        self.assertEqual(calls[1], ["notify-send", "passd agent alert", monitor.ALERT])
        self.assertEqual(calls[2], ["fixture-alert", "two words", monitor.ALERT])


if __name__ == "__main__":
    unittest.main()
