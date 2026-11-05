import importlib.machinery, importlib.util, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("fuw", str(ROOT / "scripts/failed-unit-watch"))
fuw = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(fuw)


def fake_run(failed):
    def run(cmd, **kw):
        if "--failed" in cmd:
            return SimpleNamespace(stdout="".join(f"{u} loaded failed failed x\n" for u in failed))
        u = cmd[3]
        return SimpleNamespace(stdout=f"StateChangeTimestampMonotonic={int(failed[u] * 1e6)}\nResult=exit-code\nExecMainStatus=1\n")
    return run


class FailedUnitWatch(unittest.TestCase):
    def test_lists_only_units_failed_longer_than_threshold(self):
        rows = fuw.failed_units(fake_run({"old-guard.service": 100.0, "fresh.service": 3500.0}))
        b = fuw.block(rows, now_mono=3600.0, min_minutes=30, stamp="T")
        self.assertIn("old-guard.service: failed 58 min", b)
        self.assertNotIn("fresh.service", b)

    def test_block_replaced_in_place_and_removed_when_clear(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "s.md"
            p.write_text("as of X\n- line\n")
            fuw.update(p, fuw.BEGIN + "\n- FAILED UNITS a\n" + fuw.END)
            fuw.update(p, fuw.BEGIN + "\n- FAILED UNITS b\n" + fuw.END)
            t = p.read_text()
            self.assertEqual(t.count(fuw.BEGIN), 1)
            self.assertIn("UNITS b", t)
            self.assertTrue(t.startswith("as of X\n- line\n"))
            fuw.update(p, "")
            self.assertEqual(p.read_text(), "as of X\n- line\n")

    def test_unit_runs_every_10_minutes(self):
        timer = (ROOT / "config/systemd/user/failed-unit-watch.timer").read_text()
        self.assertIn("OnUnitActiveSec=10min", timer)


if __name__ == "__main__":
    unittest.main()
