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


if __name__ == "__main__":
    unittest.main()
