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

    def test_unit_failing_on_every_run_is_listed(self):
        """artifact-leases fails each timer run, so its failed-since clock resets every few minutes and
        it never crossed 30 min (ayo 17:2x). Consecutive failures are counted across watcher runs."""
        state = {}
        for now, t in ((600.0, 590.0), (1200.0, 1190.0), (1800.0, 1790.0)):  # fails anew each run
            rows = [("artifact-leases.service", t, "exit-code", "1")]
            state = fuw.track(state, rows, lambda u: "exit-code", now)
            b = fuw.block(rows, now, 30, "T", state)
        self.assertIn("artifact-leases.service", b)
        self.assertIn("3 consecutive failures", b)

    def test_streak_survives_a_run_seen_mid_restart_and_clears_on_success(self):
        state = fuw.track({}, [("x.service", 10.0, "exit-code", "1")], lambda u: "exit-code", 20.0)
        state = fuw.track(state, [], lambda u: "exit-code", 620.0)          # activating, not success
        self.assertEqual(state["x.service"]["streak"], 1)
        state = fuw.track(state, [], lambda u: "success", 1220.0)
        self.assertEqual(state, {})

    def test_failed_unit_names_its_deleted_worktree(self):
        # 11-15: a reaped worktree killed z0-ghcache via a drop-in; the block should say so, not just "exit-code"
        with tempfile.TemporaryDirectory() as d:
            live = "/mnt/zer0models/worktrees/oss-factory-substrate"
            gone = "/mnt/zer0models/worktrees/zz-deleted-for-test"
            cat = (f"# {gone}/old.conf\nDocumentation=file://{gone}/README\n[Service]\n"
                   f"Environment=FACTORY_TOOLS={gone}/tools/factory\nExecStart={live}/x.py\n")
            run = lambda cmd, **kw: SimpleNamespace(stdout=cat)
            self.assertEqual(fuw.missing_paths("z0-ghcache.service", run), [gone])
            b = fuw.block([("z0-ghcache.service", 100.0, "exit-code", "1")], 3600.0, 30, "T",
                          missing=lambda u: fuw.missing_paths(u, run))
            self.assertIn(f"MISSING PATH {gone}", b)

    def test_unit_runs_every_10_minutes(self):
        timer = (ROOT / "config/systemd/user/failed-unit-watch.timer").read_text()
        self.assertIn("OnUnitActiveSec=10min", timer)


if __name__ == "__main__":
    unittest.main()
