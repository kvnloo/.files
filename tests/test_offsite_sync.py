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


if __name__ == "__main__":
    unittest.main()
