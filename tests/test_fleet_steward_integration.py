"""Small regressions for the existing health path and source-index opt-in."""
import argparse
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("fleet_steward_integration", str(ROOT / "scripts/fleet"))
spec = importlib.util.spec_from_loader(loader.name, loader)
fleet = importlib.util.module_from_spec(spec)
loader.exec_module(fleet)


class FleetStewardIntegrationTests(unittest.TestCase):
    def test_repository_identity_is_canonical_and_does_not_export_url_credentials(self):
        args = argparse.Namespace(src="/tmp/source", no_src=False)
        for remote in ("git@github.com:kvnloo/noop-oura.git",
                       "https://private-token@github.com/kvnloo/noop-oura.git"):
            with patch.object(fleet.subprocess, "run",
                              return_value=subprocess.CompletedProcess([], 0, stdout=remote)):
                self.assertEqual(fleet.job_repo(args), "kvnloo/noop-oura")
        args.no_src = True
        self.assertIsNone(fleet.job_repo(args))

    def test_health_dry_run_retains_state_and_never_mutates_cluster(self):
        with tempfile.TemporaryDirectory() as directory:
            state = Path(directory)
            (state / "health").mkdir()
            prior = '{"mbp":{"bad":1,"good":0,"paused":false}}\n'
            (state / "health/state.json").write_text(prior)
            node = {"name": "mbp", "role": "worker", "kind": "linux", "k8s": True,
                    "tailnet_ip": "test", "health": {"strikes": 1, "on_unhealthy": "cordon"}}
            args = argparse.Namespace(node="mbp", set=[], strikes=None, dry_run=True, steward=True)
            with patch.object(fleet, "STATE", state), \
                 patch.object(fleet, "registry", return_value=({"nodes": {}}, {"mbp": node})), \
                 patch.object(fleet, "k8s_nodes", return_value={"mbp": {"unschedulable": False}}), \
                 patch.object(fleet, "tailnet_online", return_value={}), \
                 patch.object(fleet, "probe", return_value={"max_temp_c": 90}), \
                 patch.object(fleet, "node_events", return_value=[]), \
                 patch.object(fleet, "judge", return_value=(["k8s DiskPressure"], [])), \
                 patch.object(fleet, "kc") as kubectl, \
                 patch.object(fleet.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)) as run:
                self.assertEqual(fleet.cmd_health(args), 1)
            kubectl.assert_not_called()
            self.assertEqual((state / "health/state.json").read_text(), prior)
            receipt = json.loads((state / "health/mbp.json").read_text())
            self.assertTrue(receipt["dry_run"])
            self.assertEqual(receipt["probe"]["max_temp_c"], 90)
            self.assertEqual(receipt["action"], "none")
            self.assertIn("--dry-run", run.call_args.args[0])
            self.assertIn(str(state / "registry.json"), run.call_args.args[0])

    def test_controller_hold_has_one_ledger_log_and_no_remote_job(self):
        with tempfile.TemporaryDirectory() as directory:
            args = argparse.Namespace(src=None, mem="3G", cmd=["pnpm", "test"])
            with patch.object(fleet, "STATE", Path(directory)), \
                 patch.dict(fleet.os.environ, {"FLEET_QUEUED_TS": "1", "FLEET_ATTEMPT_ID": "attempt-a"}), \
                 self.assertRaises(SystemExit) as stop:
                fleet.admission_hold(args, "mbp: paused by fleet health", "mbp")
            self.assertEqual(stop.exception.code, 75)
            logs = list((Path(directory) / "runs").glob("*.log"))
            self.assertEqual(len(logs), 1)
            text = logs[0].read_text()
            metadata = json.loads(next(line[10:] for line in text.splitlines() if line.startswith("# steward ")))
            self.assertTrue(metadata["admission_only"])
            self.assertIsNone(metadata["started_ts"])
            self.assertEqual(metadata["attempt_id"], "attempt-a")
            self.assertEqual(metadata["memory_limit_mb"], 3072)
            self.assertIn("# exit 75", text)

    def test_git_index_uses_literal_nul_paths_and_no_controller_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            src = Path(directory)
            for name in ("tracked [1].txt", "two\nlines.txt", "untracked.txt"):
                (src / name).write_text("content")
            listed = b"tracked [1].txt\0two\nlines.txt\0deleted.txt\0"
            result = subprocess.CompletedProcess([], 0, stdout=listed)
            with patch.object(fleet.subprocess, "run", side_effect=[result, subprocess.CompletedProcess([], 0)]) as run:
                fleet.transfer_git_index(src, ["ssh", "test-worker"], "~/jobs/test")
            command = run.call_args.args[0][-1]
            self.assertIn("init.templateDir=", command)
            self.assertIn("--literal-pathspecs", command)
            self.assertIn("--pathspec-file-nul", command)
            self.assertEqual(run.call_args.kwargs["input"], b"tracked [1].txt\0two\nlines.txt\0")
            self.assertNotIn("bundle", command)
            self.assertNotIn(".git/config", command)


if __name__ == "__main__":
    unittest.main()
