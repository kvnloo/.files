"""worktree-reap end to end on real git repos: proof-gated, never forced, receipts per item."""
import importlib.machinery, importlib.util, json, os, subprocess, sys, tempfile, time, unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/worktree-reap"
loader = importlib.machinery.SourceFileLoader("wtr", str(SCRIPT))
wtr = importlib.util.module_from_spec(importlib.util.spec_from_loader(loader.name, loader))
loader.exec_module(wtr)


def g(cd, *a):
    return subprocess.run(["git", "-C", str(cd), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, check=True).stdout.strip()


class Reap(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bare, repo = self.tmp / "origin.git", self.tmp / "repo"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        subprocess.run(["git", "clone", "-q", str(bare), str(repo)], check=True, capture_output=True)
        g(repo, "commit", "-q", "--allow-empty", "-m", "base")
        g(repo, "push", "-q", "origin", "HEAD:main")
        self.repo, self.cd = repo, str(repo / ".git")
        g(repo, "branch", "merged-ref")                       # tier 1: merged, not checked out
        g(repo, "branch", "unmerged-ref"); g(repo, "switch", "-q", "unmerged-ref")
        g(repo, "commit", "-q", "--allow-empty", "-m", "unique"); g(repo, "switch", "-q", "main")
        self.wts = {}
        for name, setup in (("done-clean", "push"), ("done-dirty", "dirty"), ("done-unpushed", "local")):
            wt = self.tmp / name
            g(repo, "worktree", "add", "-q", "-b", name, str(wt))
            g(wt, "commit", "-q", "--allow-empty", "-m", name)
            if setup in ("push", "dirty"):
                g(wt, "push", "-q", "origin", name)
            if setup == "dirty":
                (wt / "scratch.txt").write_text("work")
            self.wts[name] = wt
        def row(br, proof, wt=None):
            return {"repo": "repo", "commondir": self.cd, "branch": br, "head": g(repo, "rev-parse", br)[:12],
                    "finished": proof, "worktree": str(wt) if wt else None, "creator": "test", "task": None}
        rows = [row("merged-ref", ["ancestor:main"]), row("unmerged-ref", ["pr:#1"]),
                row("done-clean", ["task_done:t_1(done)"], self.wts["done-clean"]),
                row("done-dirty", ["task_done:t_2(done)"], self.wts["done-dirty"]),
                row("done-unpushed", ["task_done:t_3(done)"], self.wts["done-unpushed"])]
        self.net = self.tmp / "branches.json"
        self.net.write_text(json.dumps({"generated_at": time.time(), "rows": rows}))
        self.out = self.tmp / "run"

    def run_reap(self, *extra):
        env = dict(os.environ, HOME=str(self.tmp))   # no T3 worktrees under the fake home
        return subprocess.run([sys.executable, str(SCRIPT), "--network", str(self.net), "--out", str(self.out), *extra],
                              capture_output=True, text=True, env=env)

    def branches(self):
        return set(g(self.repo, "branch", "--format=%(refname:short)").split())

    def test_dry_run_touches_nothing(self):
        before = self.branches()
        r = self.run_reap()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.branches(), before)
        self.assertTrue(self.wts["done-clean"].exists())

    def test_apply_deletes_only_proven_items_with_receipts(self):
        r = self.run_reap("--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        left = self.branches()
        self.assertNotIn("merged-ref", left)                 # tier 1 deleted
        self.assertIn("unmerged-ref", left)                  # git -d refused a wrong proof
        self.assertFalse(self.wts["done-clean"].exists())    # tier 2 worktree removed
        self.assertIn("done-clean", left)                    # ...branch kept: unmerged in main, -d refuses
        self.assertTrue((self.wts["done-dirty"] / "scratch.txt").exists())
        self.assertTrue(self.wts["done-unpushed"].exists())
        recs = [json.loads(l) for l in (self.out / "receipts.jsonl").read_text().splitlines()]
        by = {x["branch"]: x for x in recs}
        self.assertEqual(set(by), {"merged-ref", "unmerged-ref", "done-clean"})
        self.assertTrue(by["merged-ref"]["branch_deleted"])
        self.assertIn("not fully merged", by["unmerged-ref"]["branch_kept"])
        self.assertTrue(by["done-clean"]["worktree_removed"])

    def test_moved_head_is_kept(self):
        g(self.wts["done-clean"], "commit", "-q", "--allow-empty", "-m", "new work")
        g(self.wts["done-clean"], "push", "-q", "origin", "done-clean")
        self.run_reap("--apply")
        self.assertTrue(self.wts["done-clean"].exists())

    def test_stale_network_proofs_refused(self):
        d = json.loads(self.net.read_text()); d["generated_at"] = time.time() - 3 * 86400
        self.net.write_text(json.dumps(d))
        self.assertNotEqual(self.run_reap("--apply").returncode, 0)
        self.assertTrue(self.wts["done-clean"].exists())

    def test_daily_timer(self):
        t = (ROOT / "config/systemd/user/worktree-reap.timer").read_text()
        self.assertIn("OnCalendar=daily", t)
        s = (ROOT / "config/systemd/user/worktree-reap.service").read_text()
        self.assertIn("--apply", s)
        self.assertNotIn("--force", SCRIPT.read_text().split('"""', 2)[2])
        self.assertNotIn('"-D"', SCRIPT.read_text())


if __name__ == "__main__":
    unittest.main()
