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
                row("done-unpushed", ["task_done:t_3(done)"], self.wts["done-unpushed"]),
                row("main", ["tree:origin/main"], repo)]
        link = self.tmp / "via-link"
        link.symlink_to(self.wts["done-clean"])              # network rows can name a worktree via a symlink
        rows[2]["worktree"] = str(link)
        self.link = link
        self.net = self.tmp / "branches.json"
        self.net.write_text(json.dumps({"generated_at": time.time(), "rows": rows}))
        self.out = self.tmp / "run"

    def run_reap(self, *extra):
        env = dict(os.environ, HOME=str(self.tmp),   # no T3 worktrees under the fake home
                   WORKTREE_REAP_ARCHIVE=str(self.tmp / "archive"))
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
        self.assertTrue((self.wts["done-clean"] / ".git").exists())  # reached via a symlink: refused
        self.assertIn("done-clean", left)                    # ...branch kept: unmerged in main, -d refuses
        self.assertTrue((self.wts["done-dirty"] / "scratch.txt").exists())
        self.assertTrue(self.wts["done-unpushed"].exists())
        self.assertTrue(self.repo.exists() and "main" in left)  # the main checkout is never a reap target
        recs = [json.loads(l) for l in (self.out / "receipts.jsonl").read_text().splitlines()]
        by = {x["branch"]: x for x in recs}
        self.assertEqual(set(by), {"merged-ref", "unmerged-ref"})
        self.assertTrue(by["merged-ref"]["branch_deleted"])
        self.assertIn("not fully merged", by["unmerged-ref"]["branch_kept"])
        self.assertNotIn("done-clean", by)

    def test_real_path_worktree_is_removed(self):
        rows = json.loads(self.net.read_text())
        rows["rows"][2]["worktree"] = str(self.wts["done-clean"])
        self.net.write_text(json.dumps(rows))
        self.run_reap("--apply")
        self.assertFalse(self.wts["done-clean"].exists())
        recs = [json.loads(l) for l in (self.out / "receipts.jsonl").read_text().splitlines()]
        self.assertTrue([r for r in recs if r["branch"] == "done-clean"][0]["worktree_removed"])

    def test_worktree_outside_repo_parent_tree_is_kept(self):
        outside = Path(tempfile.mkdtemp())   # not under the repo's parent directory
        wt = outside / "far"
        g(self.repo, "worktree", "add", "-q", "-b", "far", str(wt))
        g(wt, "commit", "-q", "--allow-empty", "-m", "far"); g(wt, "push", "-q", "origin", "far")
        d = json.loads(self.net.read_text())
        d["rows"].append({"repo": "repo", "commondir": self.cd, "branch": "far", "head": g(self.repo, "rev-parse", "far")[:12],
                          "finished": ["task_done:t_9(done)"], "worktree": str(wt), "creator": "test", "task": None})
        self.net.write_text(json.dumps(d))
        self.run_reap("--apply")
        self.assertTrue((wt / ".git").exists())

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
        body = SCRIPT.read_text().split('"""', 2)[2]
        # --force only in the tier-3 path, after the snapshot ref is verified
        self.assertEqual(body.count('"--force"'), 1)
        self.assertLess(body.index('snapshot(row, wt)'), body.index('"--force"'))
        self.assertNotIn('"-D"', SCRIPT.read_text())

    def age(self, wt, days=5):
        old = time.time() - days * 86400
        for d, dirs, files in os.walk(wt):
            dirs[:] = [x for x in dirs if x != ".git"]
            for n in files + dirs:
                os.utime(os.path.join(d, n), (old, old), follow_symlinks=False)
        os.utime(wt, (old, old))

    def add_idle(self, name, setup, days=5):
        wt = self.tmp / name
        stamp = f"@{int(time.time() - days * 86400)} +0000"
        env = dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp)
        g(self.repo, "worktree", "add", "-q", "-b", name, str(wt))
        subprocess.run(["git", "-C", str(wt), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                        "--allow-empty", "-m", name], check=True, env=env)
        setup(wt)
        self.age(wt, days)
        d = json.loads(self.net.read_text())
        d["rows"].append({"repo": "repo", "commondir": self.cd, "branch": name, "head": g(wt, "rev-parse", "HEAD")[:12],
                          "finished": [], "worktree": str(wt), "creator": "t3", "task": None})
        self.net.write_text(json.dumps(d))
        return wt

    def snapshots(self):
        return g(self.repo, "for-each-ref", "--format=%(refname)", "refs/reaped/").split()

    def test_idle_worktree_without_proof_is_snapshotted_then_removed(self):
        def work(wt):
            (wt / "notes.md").write_text("unsaved idea")                  # untracked, not ignored
            (wt / ".gitignore").write_text("node_modules/\n.env\n")
            (wt / ".env").write_text("TOKEN=local")                        # ignored, not regenerable
            (wt / "node_modules").mkdir(); (wt / "node_modules/big.js").write_text("x" * 1000)
        wt = self.add_idle("idle-dirty", work)
        r = self.run_reap("--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(wt.exists())
        self.assertIn("idle-dirty", self.branches())                    # branch kept
        ref = [x for x in self.snapshots() if "idle-dirty" in x]
        self.assertEqual(len(ref), 1)
        self.assertEqual(g(self.repo, "show", f"{ref[0]}:notes.md"), "unsaved idea")
        self.assertEqual(g(self.repo, "rev-parse", f"{ref[0]}^"), g(self.repo, "rev-parse", "idle-dirty"))
        self.assertNotIn("node_modules", g(self.repo, "ls-tree", "-r", "--name-only", ref[0]))
        rec = [json.loads(l) for l in (self.out / "receipts.jsonl").read_text().splitlines()]
        rec = [x for x in rec if x["branch"] == "idle-dirty"][0]
        self.assertEqual(rec["action"], "idle"); self.assertTrue(rec["worktree_removed"])
        names = subprocess.run(["tar", "-tzf", rec["ignored_archive"]], capture_output=True, text=True).stdout.split()
        self.assertIn(".env", names)                                     # ignored file archived
        self.assertFalse(any("node_modules" in n for n in names))         # deps not archived

    def test_idle_detached_unpushed_commits_survive_in_snapshot(self):
        def detach(wt):
            stamp = f"@{int(time.time() - 5 * 86400)} +0000"
            subprocess.run(["git", "-C", str(wt), "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q",
                            "--allow-empty", "-m", "only here"], check=True,
                           env=dict(os.environ, GIT_AUTHOR_DATE=stamp, GIT_COMMITTER_DATE=stamp))
            g(wt, "switch", "-q", "--detach")
            g(self.repo, "branch", "-D", "idle-detached")
        wt = self.add_idle("idle-detached", detach)
        d = json.loads(self.net.read_text()); d["rows"][-1]["branch"] = ""
        d["rows"][-1]["head"] = g(wt, "rev-parse", "HEAD")[:12]; self.net.write_text(json.dumps(d))
        head = g(wt, "rev-parse", "HEAD")
        self.run_reap("--apply")
        self.assertFalse(wt.exists())
        ref = [x for x in self.snapshots() if "idle-detached" in x]
        self.assertEqual(g(self.repo, "rev-parse", f"{ref[0]}^"), head)

    def test_recent_file_keeps_worktree(self):
        wt = self.add_idle("idle-but-touched", lambda wt: None)
        (wt / "today.txt").write_text("working")                        # written now
        self.run_reap("--apply")
        self.assertTrue((wt / "today.txt").exists())
        self.assertEqual(self.snapshots(), [])

    def test_big_untracked_file_keeps_worktree(self):
        def big(wt):
            with open(wt / "footage.mp4", "wb") as f:
                f.truncate(51 << 20)
        wt = self.add_idle("idle-big", big)
        self.run_reap("--apply")
        self.assertTrue((wt / "footage.mp4").exists())

    def test_idle_dry_run_touches_nothing(self):
        wt = self.add_idle("idle-dry", lambda wt: (wt / "x.txt").write_text("x"))
        self.run_reap()
        self.assertTrue((wt / "x.txt").exists())
        self.assertEqual(self.snapshots(), [])

    def test_in_use_idle_worktree_is_kept(self):
        wt = self.add_idle("idle-in-use", lambda wt: None)
        p = subprocess.Popen(["sleep", "60"], cwd=wt)
        try:
            self.run_reap("--apply")
        finally:
            p.kill()
        self.assertTrue(wt.exists())


if __name__ == "__main__":
    unittest.main()
