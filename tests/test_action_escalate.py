"""action-escalate: reap-receipt join -> restore command; unclaimed routed action -> one push per key."""
import importlib.machinery, importlib.util, json, sqlite3, tempfile, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
loader = importlib.machinery.SourceFileLoader("ae", str(ROOT / "scripts/action-escalate"))
ae = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(ae)

H = 3600
T0 = 1_800_000_000  # synthetic epoch


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.wt = "/mnt/zer0models/worktrees/demo-acp"
        app = self.tmp / "app"; app.mkdir()
        (app / "feed.py").write_text("import helper\nhelper.go()\n")
        (app / "helper.py").write_text(f"TERM = '{self.wt}/Term.ts'\n")
        self.units = {
            "feed.service": f"[Unit]\nRequires=srv.service\n[Service]\nExecStart=/usr/bin/python3 {app}/feed.py --pass\n",
            "srv.service": "[Service]\nExecStart=/usr/bin/true\n",
            "plain.service": "[Service]\nExecStart=/usr/bin/false\n",
            "direct.service": "[Service]\nWorkingDirectory=/mnt/zer0models/worktrees/gone-no-receipt\nExecStart=/usr/bin/true\n",
        }
        rc = self.tmp / "runs/worktree-reap-1/receipts.jsonl"; rc.parent.mkdir(parents=True)
        rows = [{"ts": "2027-01-15T02:00:00+00:00", "repo": "demo", "commondir": "/r/demo/.git", "branch": "feat/acp",
                 "head": "abc", "worktree": self.wt, "action": "idle", "applied": True, "worktree_removed": True,
                 "snapshot_ref": "refs/reaped/feat/acp-1"},
                {"ts": "2027-01-15T02:00:00+00:00", "worktree": "/x/kept", "applied": False, "worktree_removed": False}]
        rc.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
        self.receipts = ae.load_receipts(str(self.tmp / "runs/*/receipts.jsonl"))

    def cat(self, u):
        return self.units.get(u, "")


class Join(Base):
    def test_receipts_keep_only_applied_removals(self):
        self.assertEqual([r["worktree"] for r in self.receipts], [self.wt])

    def test_imported_module_and_dep_path_joins_receipt(self):
        f = ae.fix_for_unit("feed.service", self.receipts, cat=self.cat, exists=lambda p: False,
                            branch_exists=lambda g, b: True)
        self.assertEqual(f["fix"], f"git --git-dir=/r/demo/.git worktree add {self.wt} feat/acp")
        self.assertIn(self.wt, f["missing"])

    def test_branch_gone_restores_from_snapshot(self):
        f = ae.fix_for_unit("feed.service", self.receipts, cat=self.cat, exists=lambda p: False,
                            branch_exists=lambda g, b: False)
        self.assertEqual(f["fix"], f"git --git-dir=/r/demo/.git worktree add -b feat/acp {self.wt} refs/reaped/feat/acp-1")

    def test_restored_path_is_not_flagged_live(self):
        f = ae.fix_for_unit("feed.service", self.receipts, cat=self.cat, exists=lambda p: True)
        self.assertIsNone(f["fix"])

    def test_replay_uses_receipt_time_not_disk(self):
        at = self.receipts[0]["_at"]
        self.assertIsNone(ae.fix_for_unit("feed.service", self.receipts, at=at - 1, cat=self.cat)["fix"])
        self.assertIsNotNone(ae.fix_for_unit("feed.service", self.receipts, at=at + 1, cat=self.cat)["fix"])

    def test_missing_without_receipt_is_named(self):
        f = ae.fix_for_unit("direct.service", self.receipts, cat=self.cat, exists=lambda p: False)
        self.assertEqual((f["fix"], f["missing"]), (None, ["/mnt/zer0models/worktrees/gone-no-receipt"]))


class Escalate(Base):
    def log(self, *rows):
        p = self.tmp / "actions.jsonl"
        p.write_text("".join(json.dumps(r) + "\n" for r in rows))
        return p

    def rows(self, p, now, progress=lambda *a: None):
        orig = ae.fix_for_unit
        ae.fix_for_unit = lambda u, rc, at=None: orig(u, rc, at=at, cat=self.cat, exists=lambda x: False,
                                                         branch_exists=lambda g, b: True)
        try:
            return ae.escalate(p, now, receipts=self.receipts, replay=True, progress=progress)
        finally:
            ae.fix_for_unit = orig

    def test_six_hours_unclaimed_escalates_with_restore_fix(self):
        p = self.log({"at": T0, "key": "dead:os_service:feed.service", "owner": "reliability", "line": "dead"})
        self.assertEqual(self.rows(p, T0 + 6 * H - 1), [])
        [r] = self.rows(p, T0 + 6 * H)
        self.assertTrue(r["line"].startswith("reliability | feed.service | open 6.0 h"))
        self.assertIn("worktree add", r["fix"])

    def test_claim_resets_the_clock(self):
        p = self.log({"at": T0, "key": "dead:os_service:plain.service", "owner": "reliability", "line": "dead"})
        self.assertEqual(self.rows(p, T0 + 7 * H, progress=lambda *a: T0 + 2 * H), [])
        self.assertEqual(len(self.rows(p, T0 + 8 * H, progress=lambda *a: T0 + 2 * H)), 1)

    def test_flapping_unit_keeps_aging_and_cleared_unit_stops(self):
        k = "dead:os_service:plain.service"
        p = self.log({"at": T0, "key": k, "owner": "r", "line": "d"}, {"at": T0 + H, "key": k, "cleared": True},
                     {"at": T0 + 2 * H, "key": k, "owner": "r", "line": "d"})
        self.assertEqual(self.rows(p, T0 + 6 * H)[0]["opened"], T0)
        p = self.log({"at": T0, "key": k, "owner": "r", "line": "d"}, {"at": T0 + H, "key": k, "cleared": True})
        self.assertEqual(self.rows(p, T0 + 9 * H), [])

    def test_kinds_filter_skips_asks(self):
        p = self.log({"at": T0, "key": "ask:ask:X1", "owner": "r", "line": "a"})
        self.assertEqual(self.rows(p, T0 + 9 * H), [])

    def test_no_duplicate_push_per_key(self):
        p = self.log({"at": T0, "key": "dead:os_service:plain.service", "owner": "r", "line": "d"})
        st = {}
        self.assertEqual(len(ae.new_pushes(self.rows(p, T0 + 6 * H), st, T0 + 6 * H)), 1)
        self.assertEqual(ae.new_pushes(self.rows(p, T0 + 7 * H), st, T0 + 7 * H), [])

    def test_rate_cap_batches_and_never_exceeds_per_day(self):
        st, n = {}, 0
        for i in range(48):  # a new unclaimed unit every 30 min for a day
            now = T0 + i * 1800
            rows = [{"key": f"k{j}", "opened": T0, "idle_h": 6.0, "fix": "triage" if j % 4 else "restore x"}
                    for j in range(i + 1)]
            n += bool(ae.new_pushes(rows, st, now))
        self.assertLessEqual(n, 5)
        self.assertEqual(len(st["calls"]), n)

    def test_restore_row_bypasses_generic_budget_not_cap(self):
        st, g = {}, lambda k: {"key": k, "opened": T0, "idle_h": 6.0, "fix": "triage"}
        self.assertTrue(ae.new_pushes([g("a")], st, T0))
        self.assertEqual(ae.new_pushes([g("b")], st, T0 + H), [])  # generic: 4 h gap
        out = ae.new_pushes([g("b"), {"key": "c", "opened": T0, "idle_h": 6.0, "fix": "restore x"}], st, T0 + 2 * H)
        self.assertEqual({r["key"] for r in out}, {"b", "c"})  # restore goes now and carries pending rows

    def test_archived_owner_routes_to_live_lane(self):
        p = self.log({"at": T0, "key": "dead:os_service:plain.service", "owner": "reliability-archive-pre-1107", "line": "d"})
        self.assertEqual(self.rows(p, T0 + 6 * H)[0]["lane"], "reliability")

    def test_kanban_claim_rules(self):
        db = self.tmp / "kanban.db"
        c = sqlite3.connect(db)
        c.executescript("create table tasks(id text, title text, body text, assignee text, created_at int);"
                        "create table task_events(id int, task_id text, created_at int);"
                        "create table task_comments(id int, task_id text, author text, body text, created_at int);")
        c.execute("insert into tasks values('a','observer list','plain feed other','network',?)", (T0 + H,))
        c.execute("insert into task_events values(1,'a',?)", (T0 + 5 * H,))
        c.commit()
        kp = lambda: ae.kanban_progress("plain.service", T0, T0 + 6 * H, "reliability", dbs=[str(db)])
        self.assertIsNone(kp())  # body mention by another lane's card is not a claim
        c.execute("insert into tasks values('b','fix plain unit','x','reliability',?)", (T0 + 2 * H,)); c.commit()
        self.assertEqual(kp(), T0 + 2 * H)  # dedicated card (title names it)

    def test_failed_push_and_dry_run_never_mark_sent(self):
        p = self.log({"at": 0, "key": "dead:os_service:plain.service", "owner": "r", "line": "d"})
        st = self.tmp / "state.json"
        orig_push, orig_fix = ae.push, ae.proposed_fix
        ae.proposed_fix = lambda *a: ("triage", {})
        try:
            ae.main(["--actions", str(p), "--state", str(st), "--receipts", "/nonexistent/*"])
            self.assertFalse(st.exists())  # dry run writes nothing
            ae.push = lambda rows: 1  # kevin-push failed
            ae.main(["--actions", str(p), "--state", str(st), "--receipts", "/nonexistent/*", "--push"])
            s = json.loads(st.read_text())
            self.assertEqual((s.get("sent", {}), s.get("calls", []), s["last_push"]["rc"]), ({}, [], 1))
            ae.push = lambda rows: 0
            ae.main(["--actions", str(p), "--state", str(st), "--receipts", "/nonexistent/*", "--push"])
            s = json.loads(st.read_text())
            self.assertIn("dead:os_service:plain.service", s["sent"])
            self.assertEqual(len(s["calls"]), 1)
        finally:
            ae.push, ae.proposed_fix = orig_push, orig_fix


if __name__ == "__main__":
    unittest.main()
