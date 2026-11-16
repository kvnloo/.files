import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fix-replay"


def load(ops):
    os.environ["FIX_OPS"] = str(ops)
    loader = importlib.machinery.SourceFileLoader("fix_replay_under_test", str(SCRIPT))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FixReplayCost(unittest.TestCase):
    def test_every_log_row_records_wall_time_so_heavy_tapes_are_findable(self):
        with tempfile.TemporaryDirectory() as tmp:
            ops = Path(tmp) / "ops"
            ops.mkdir()
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [
                {"id": "quick", "tape": "true"},
                {"id": "slow-fail", "tape": "timeout 0.3 tail -f /dev/null; false"},
            ]}))
            load(ops).run()
            rows = {r["id"]: r for r in map(json.loads, (ops / "fix-replay.jsonl").read_text().splitlines())}
            self.assertIsInstance(rows["quick"]["ms"], int)
            self.assertGreaterEqual(rows["slow-fail"]["ms"], 250)
            self.assertFalse(rows["slow-fail"]["ok"])

    def test_a_malformed_row_fails_alone_and_the_rest_still_replay(self):
        # 2026-11-16 13:03: one row carried "env" as prose instead of an object; the TypeError aborted the
        # whole replay, so no tape was checked, the board went stale and nobody was paged.
        with tempfile.TemporaryDirectory() as tmp:
            ops = Path(tmp) / "ops"
            ops.mkdir()
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [
                {"id": "prose-env", "tape": "true", "env": "needs XDG_RUNTIME_DIR"},
                {"id": "no-tape"},
                {"id": "fine", "tape": "true", "env": {"A": "1"}},
            ]}))
            load(ops).run()
            rows = {r["id"]: r for r in map(json.loads, (ops / "fix-replay.jsonl").read_text().splitlines())}
            self.assertTrue(rows["fine"]["ok"])
            self.assertFalse(rows["prose-env"]["ok"])
            self.assertIn("malformed tape row", rows["prose-env"]["out"])
            self.assertFalse(rows["no-tape"]["ok"])
            self.assertTrue((ops / "BOARD.md").exists())

    def test_use_must_be_a_read_only_counter(self):
        # 2026-11-16: a `use` of `systemctl --user start kvnloo-fork-sync.service` turned a daily GitHub sync
        # into an hourly one (14 starts/24 h, ~150 s each) and prose notes were executed as shell.
        with tempfile.TemporaryDirectory() as tmp:
            ops, stub = Path(tmp) / "ops", Path(tmp) / "bin"
            ops.mkdir(); stub.mkdir()
            marker = Path(tmp) / "started"
            (stub / "systemctl").write_text(f"#!/bin/sh\necho \"$@\" >> {marker}\necho 0\n")
            (stub / "systemctl").chmod(0o755)
            (ops / "fix-tapes.json").write_text(json.dumps({"tapes": [
                {"id": "mutating", "tape": "true", "use": "systemctl --user start some-sync.service"},
                {"id": "placeholder", "tape": "true", "use": "systemctl --user show -P OnFailure <unit>"},
                {"id": "counter", "tape": "true", "use": "echo 3"},
            ]}))
            old = os.environ["PATH"]
            os.environ["PATH"] = f"{stub}:{old}"
            try:
                mod = load(ops)
                mod.run()
            finally:
                os.environ["PATH"] = old
            rows = {r["id"]: r for r in map(json.loads, (ops / "fix-replay.jsonl").read_text().splitlines())}
            self.assertFalse(marker.exists(), "a use command must never start or stop units")
            self.assertTrue(rows["mutating"]["use_refused"])
            self.assertTrue(rows["placeholder"]["use_refused"])
            self.assertEqual(rows["counter"]["uses"], 3)
            self.assertNotIn("use_refused", rows["counter"])
            state = json.loads((ops / "fix-state.json").read_text())
            self.assertTrue(state["mutating"]["use_refused"])
            self.assertIn("use refused", mod.board(state, 0))


if __name__ == "__main__":
    unittest.main()
