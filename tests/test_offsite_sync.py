"""offsite-sync end to end: local-only branches, reaped refs and dirty worktrees reach the remote."""
import os, subprocess, sys, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/offsite-sync"


def g(cd, *a):
    return subprocess.run(["git", "-C", str(cd), "-c", "user.name=t", "-c", "user.email=t@t", *a],
                          capture_output=True, text=True, check=True).stdout.strip()


class Offsite(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.bare, self.repo = self.tmp / "origin.git", self.tmp / "src/repo"
        subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(self.bare)], check=True)
        subprocess.run(["git", "clone", "-q", str(self.bare), str(self.repo)], check=True, capture_output=True)
        g(self.repo, "commit", "-q", "--allow-empty", "-m", "base"); g(self.repo, "push", "-q", "origin", "HEAD:main")

    def run_sync(self, *extra, remote_re="origin\\.git"):
        env = dict(os.environ, OFFSITE_ROOTS=f"{self.tmp / 'src'}:1", OFFSITE_REMOTE_RE=remote_re)
        return subprocess.run([sys.executable, str(SCRIPT), "--out", str(self.tmp / "run"), *extra],
                              capture_output=True, text=True, env=env)

    def remote(self, ref):
        return subprocess.run(["git", "-C", str(self.bare), "rev-parse", "--verify", "-q", ref],
                              capture_output=True, text=True).stdout.strip()

    def test_local_only_work_reaches_remote(self):
        g(self.repo, "switch", "-q", "-c", "feat/x"); g(self.repo, "commit", "-q", "--allow-empty", "-m", "x")
        g(self.repo, "update-ref", "refs/reaped/old-20261113-abc", "HEAD")
        wt = self.tmp / "wt"; g(self.repo, "worktree", "add", "-q", "-b", "feat/y", str(wt))
        (wt / "idea.md").write_text("unsaved")
        (wt / ".gitignore").write_text(".env\n"); (wt / ".env").write_text("TOKEN=x")
        r = self.run_sync("--apply"); self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(self.remote("refs/heads/feat/x"), g(self.repo, "rev-parse", "feat/x"))
        self.assertEqual(self.remote("refs/heads/reaped/old-20261113-abc"), g(self.repo, "rev-parse", "feat/x"))
        host = os.uname().nodename.split(".")[0]
        snap = self.remote(f"refs/offsite/{host}/feat/y")
        self.assertEqual(g(self.bare, "show", f"{snap}:idea.md"), "unsaved")
        self.assertNotIn(".env", g(self.bare, "ls-tree", "--name-only", snap).split())   # gitignore respected
        self.assertEqual(g(wt, "status", "--porcelain"), "?? .gitignore\n?? idea.md")    # local untouched

    def test_untracked_venvs_and_node_modules_are_not_snapshotted(self):
        # 2026-11-16: offsite.service ran 5 h hashing z0intelligence's .venv-311 site-packages (not in its
        # .gitignore) into git objects. Environments rebuild from lockfiles; they are not work product.
        (self.repo / "notes.md").write_text("keep")
        venv = self.repo / ".venv-311"; (venv / "lib").mkdir(parents=True)
        (venv / "pyvenv.cfg").write_text("home = /usr/bin\n"); (venv / "lib/mod.py").write_text("x")
        (self.repo / "web/node_modules/pkg").mkdir(parents=True); (self.repo / "web/node_modules/pkg/i.js").write_text("x")
        (self.repo / "web/app.js").write_text("app")
        r = self.run_sync("--apply"); self.assertEqual(r.returncode, 0, r.stderr)
        host = os.uname().nodename.split(".")[0]
        files = g(self.bare, "ls-tree", "-r", "--name-only", self.remote(f"refs/offsite/{host}/main")).split()
        self.assertEqual(sorted(files), ["notes.md", "web/app.js"])

    def test_dry_run_pushes_nothing(self):
        g(self.repo, "switch", "-q", "-c", "feat/x"); g(self.repo, "commit", "-q", "--allow-empty", "-m", "x")
        self.run_sync()
        self.assertEqual(self.remote("refs/heads/feat/x"), "")

    def test_repo_without_owner_remote_is_reported_as_sole_copy(self):
        g(self.repo, "switch", "-q", "-c", "feat/x"); g(self.repo, "commit", "-q", "--allow-empty", "-m", "x")
        self.run_sync("--apply", remote_re="github\\.com[:/]kvnloo/")
        self.assertEqual(self.remote("refs/heads/feat/x"), "")
        self.assertIn("no kvnloo remote", (self.tmp / "run/summary.json").read_text())

    def test_remote_without_url_does_not_crash(self):
        # 11-16 dry run died after 51 min: partial clones leave `remote.<url>.promisor` with no url,
        # which `git remote -v` prints as a lone name
        g(self.repo, "config", "remote.https://example.com/x.git.promisor", "true")
        g(self.repo, "switch", "-q", "-c", "feat/y"); g(self.repo, "commit", "-q", "--allow-empty", "-m", "y")
        r = self.run_sync("--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertNotEqual(self.remote("refs/heads/feat/y"), "")

    def test_diverged_branch_is_parked_not_lost(self):
        # 11-16 apply run: 21 repos failed whole pushes because one branch was behind its remote
        g(self.repo, "switch", "-q", "-c", "feat/d"); g(self.repo, "commit", "-q", "--allow-empty", "-m", "d")
        g(self.repo, "push", "-q", "origin", "feat/d")
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", "-b", "feat/d", str(self.bare), str(other)], check=True, capture_output=True)
        g(other, "commit", "-q", "--allow-empty", "-m", "remote-side"); g(other, "push", "-q", "origin", "feat/d")
        g(self.repo, "commit", "-q", "--allow-empty", "-m", "local-only")
        g(self.repo, "switch", "-q", "-c", "feat/e"); g(self.repo, "commit", "-q", "--allow-empty", "-m", "e")
        r = self.run_sync("--apply")
        self.assertEqual(r.returncode, 0, r.stderr)
        host = __import__("socket").gethostname().split(".")[0]
        self.assertEqual(self.remote(f"refs/offsite/{host}/heads/feat/d"), g(self.repo, "rev-parse", "feat/d"))
        self.assertNotEqual(self.remote("refs/heads/feat/e"), "")
        self.assertNotIn("no kvnloo remote", (self.tmp / "run/summary.json").read_text())
        self.assertEqual(__import__("json").loads((self.tmp / "run/summary.json").read_text())["sole_copies"], 0)


class PartialCloneFork(unittest.TestCase):
    """11-16: offsite pushes from a blob:none clone of hermes-agent to the shared kvnloo fork ran
    `git fetch --filter=blob:none --stdin` from upstream mid-push (one pull was 415k objects; the run
    took 5.6 h, read 101 G, wrote 71 G). Other clones push to the same fork, so it advertises commits
    this clone lacks, and every lookup lazy-fetches them. offsite-sync must never fetch."""

    def setUp(self):
        saved = os.environ.pop("GIT_NO_LAZY_FETCH", None)   # the fixture clone needs lazy fetch
        if saved is not None:
            self.addCleanup(os.environ.__setitem__, "GIT_NO_LAZY_FETCH", saved)
        self.tmp = Path(tempfile.mkdtemp()).resolve()
        self.up, self.fork, self.repo = self.tmp / "up.git", self.tmp / "fork.git", self.tmp / "src/repo"
        for bare in (self.up, self.fork):
            subprocess.run(["git", "init", "-q", "--bare", "-b", "main", str(bare)], check=True)
        g(self.up, "config", "uploadpack.allowFilter", "true"); g(self.up, "config", "uploadpack.allowAnySHA1InWant", "true")
        seed = self.tmp / "seed"
        subprocess.run(["git", "clone", "-q", str(self.up), str(seed)], check=True, capture_output=True)
        (seed / "a.txt").write_text("base\n"); g(seed, "add", "a.txt"); g(seed, "commit", "-q", "-m", "base")
        g(seed, "push", "-q", "origin", "HEAD:main"); g(seed, "push", "-q", str(self.fork), "HEAD:main")
        subprocess.run(["git", "clone", "-q", "--filter=blob:none", f"file://{self.up}", str(self.repo)], check=True, capture_output=True)
        # upstream moves on and another clone pushes a branch on the new upstream to the shared fork
        (seed / "b.txt").write_text("later\n"); g(seed, "add", "b.txt"); g(seed, "commit", "-q", "-m", "later")
        g(seed, "push", "-q", "origin", "HEAD:main"); g(seed, "push", "-q", str(self.fork), "HEAD:refs/heads/other-clone")
        url = "https://github.com/kvnloo/fork.git"
        g(self.repo, "remote", "add", "fork", url); g(self.repo, "config", f"url.file://{self.fork}.pushInsteadOf", url)
        g(self.repo, "switch", "-q", "-c", "feat/x"); g(self.repo, "commit", "-q", "--allow-empty", "-m", "local work")

    def promisor_packs(self):
        return len(list((self.repo / ".git/objects/pack").glob("*.promisor")))

    def test_push_to_a_shared_fork_never_lazy_fetches(self):
        before = self.promisor_packs()
        env = dict(os.environ, OFFSITE_ROOTS=f"{self.tmp / 'src'}:1", OFFSITE_REMOTE_RE=r"github\.com[:/]kvnloo/")
        r = subprocess.run([sys.executable, str(SCRIPT), "--out", str(self.tmp / "run"), "--apply"],
                           capture_output=True, text=True, env=env)
        self.assertEqual(r.returncode, 0, r.stderr)
        pushed = subprocess.run(["git", "-C", str(self.fork), "rev-parse", "--verify", "-q", "refs/heads/feat/x"],
                                capture_output=True, text=True).stdout.strip()
        self.assertEqual(pushed, g(self.repo, "rev-parse", "feat/x"))
        self.assertEqual(self.promisor_packs(), before)   # nothing fetched from upstream


if __name__ == "__main__":
    unittest.main()
