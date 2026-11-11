import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fable-arm"


class FableArmTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.ops = self.root / "ops"
        self.ops.mkdir()
        self.home = self.root / "z0int"
        self.env = dict(os.environ, FIX_OPS=str(self.ops), Z0INT_HOME=str(self.home),
                        PYTHONDONTWRITEBYTECODE="1")
        self.arms = {
            "A": {"mode": "implement", "effort": "medium", "scouts": True},
            "B": {"mode": "implement", "effort": "high", "scouts": True},
        }
        self.write("hill-state.json", {"incumbent": self.arms["A"],
                                      "challenger": self.arms["B"]})
        self.write("fix-state.json", {})
        self.write("fix-tapes.json", {"tapes": []})
        self.runs = []
        self.start = datetime(2026, 11, 10, 12)

    def write(self, name, value):
        (self.ops / name).write_text(json.dumps(value))

    def cli(self, command):
        result = subprocess.run([sys.executable, str(SCRIPT), command], env=self.env,
                                capture_output=True, text=True, timeout=30)
        self.assertEqual(result.returncode, 0, result.stderr)
        return result.stdout

    def rows(self, table):
        with sqlite3.connect(self.home / "autoresearch/queue.sqlite3") as db:
            db.row_factory = sqlite3.Row
            return [dict(row) for row in db.execute(f"SELECT * FROM {table}")]

    def add_run(self, arm="B", **overrides):
        run = {"job": f"F{len(self.runs) + 1}",
               "ts": (self.start + timedelta(minutes=10 * len(self.runs))).isoformat(),
               "class": "memory", "minutes": 5,
               "arm": {**self.arms[arm], "slot": "incumbent" if arm == "A" else "challenger"},
               "meter_delta": {"fable": 1}}
        run.update(overrides)
        self.runs.append(run)
        (self.ops / "hill.jsonl").write_text("".join(json.dumps(r) + "\n" for r in self.runs))
        return run

    def tape(self, fails=1, **overrides):
        state = {"ok": True, "fails": fails, "cls": "memory",
                 "since": (self.start + timedelta(hours=2)).timestamp()}
        state.update(overrides)
        self.write("fix-state.json", {"tape-1": state})

    def definitions(self):
        return json.loads((self.home / "autoresearch/champions/fable.json").read_text())

    def test_first_pass_has_no_job(self):
        self.add_run()
        self.tape(fails=0)
        self.cli("sync")
        self.assertEqual(self.rows("jobs"), [])
        arm, = self.rows("arms")
        self.assertEqual(arm["status"], "done")
        self.assertEqual(json.loads(arm["result_json"]), {"cost": 1, "minutes": 5})

    def test_flip_is_credited_once_after_two_syncs(self):
        run = self.add_run()
        self.tape()
        self.cli("sync")
        self.cli("sync")
        job, = self.rows("jobs")
        self.assertEqual(job["status"], "credited")
        self.assertEqual(job["trace_id"], f"flip:{run['job']}@{run['ts']}")
        payload = json.loads(job["payload"])
        self.assertEqual(payload["verifier_id"], "tape-1")
        expected_hash = hashlib.sha256(json.dumps(self.arms["B"], sort_keys=True).encode()).hexdigest()[:16]
        self.assertEqual(payload["payload"], {"kind": "fix_flip", "treatment_hash": expected_hash})
        self.assertEqual(len(self.rows("arms")), 1)

    def test_next_alternates_as_runs_arrive(self):
        for arm, slot in [("B", "challenger"), ("A", "incumbent")] * 2:
            self.assertEqual(json.loads(self.cli("next")), {**self.arms[arm], "slot": slot})
            self.add_run(arm)
        self.assertEqual(self.definitions(), self.arms)
        self.write("hill-state.json", {})
        self.assertEqual(json.loads(self.cli("next"))["slot"], "challenger")

    def test_promote_needs_three_runs_each(self):
        for arm in ["A", "A", "B", "B", "B"]:
            self.add_run(arm)
        self.tape()
        self.assertIn("need 3 runs each", self.cli("promote"))
        self.assertEqual(self.definitions(), self.arms)

    def test_latest_eligible_run_and_source_match(self):
        self.add_run()
        chosen = self.add_run("A", **{"class": "other"})
        self.add_run(ts=(self.start + timedelta(hours=3)).isoformat())
        self.write("fix-tapes.json", {"tapes": [{"id": "tape-1", "src": f"fable {chosen['job']}"}]})
        self.tape()
        self.cli("sync")
        job, = self.rows("jobs")
        self.assertEqual(job["trace_id"], f"flip:{chosen['job']}@{chosen['ts']}")

    def test_start_time_not_finish_time(self):
        self.add_run(minutes=10)
        self.tape(since=(self.start - timedelta(minutes=5)).timestamp())
        self.cli("sync")
        self.assertEqual(len(self.rows("jobs")), 1)

    def test_ineligible_tapes_and_grader_changes_get_no_credit(self):
        run = self.add_run()
        for state in [{"ok": False}, {"cls": "unrelated"},
                      {"since": (self.start - timedelta(hours=1)).timestamp()}]:
            with self.subTest(state=state):
                self.tape(**state)
                self.cli("sync")
                self.assertEqual(self.rows("jobs"), [])
        run["arm"]["grader_touched"] = True
        (self.ops / "hill.jsonl").write_text(json.dumps(run) + "\n")
        self.tape()
        self.cli("sync")
        self.assertEqual(self.rows("jobs"), [])

    def test_sync_recovers_enqueued_but_uncredited_flip(self):
        self.add_run()
        self.tape()
        self.cli("sync")
        with sqlite3.connect(self.home / "autoresearch/queue.sqlite3") as db:
            db.execute("UPDATE jobs SET status='queued'")
        self.cli("sync")
        job, = self.rows("jobs")
        self.assertEqual(job["status"], "credited")

    def test_promote_winner_and_mutate_one_knob(self):
        for arm in ["A"] * 3 + ["B"] * 3:
            self.add_run(arm)
        self.tape()
        self.cli("promote")
        definitions = self.definitions()
        self.assertEqual(definitions["A"], self.arms["B"])
        changed = [key for key in definitions["A"] if definitions["A"][key] != definitions["B"][key]]
        self.assertEqual(len(changed), 1)
        self.assertIn(changed[0], ["effort", "scouts"])
        self.assertIn("need 3 runs each", self.cli("promote"))

    def test_score_uses_summed_cost_floor(self):
        self.add_run(meter_delta={"fable": 0})
        self.tape()
        output = self.cli("score")
        self.assertIn("| B | 1 | 0.50 | 1 | 2.00 |", output)


if __name__ == "__main__":
    unittest.main()
