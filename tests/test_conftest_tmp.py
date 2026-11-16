"""Suite runs must not leak temp fixtures into tmpfs /tmp.

11-16: ~90 leaked test_worktree_reap fixtures (sparse 51 MB footage.mp4 each) and 5298 /tmp/tmp*
dirs in total had piled up from mkdtemp() calls that nobody removed, so the F22 /tmp<2 GiB tape went red.
"""
import os, shutil, subprocess, sys, tempfile, unittest
from pathlib import Path

CONFTEST = Path(__file__).resolve().parent / "conftest.py"
PROBE = '''import subprocess, sys, tempfile
from pathlib import Path

def test_leaks_like_the_suite_does():
    d = Path(tempfile.mkdtemp())
    (d / "fixture").write_text("x")
    ro = d / "readonly"; (ro / "nested").mkdir(parents=True); (ro / "nested/f").write_text("x")
    (ro / "nested").chmod(0o555); ro.chmod(0o555)   # like test_verified_readonly_backup
    subprocess.run([sys.executable, "-c", "import tempfile; tempfile.mkdtemp()"], check=True)
'''


class SuiteCleansTmp(unittest.TestCase):
    def test_session_removes_every_mkdtemp(self):
        work = Path(tempfile.mkdtemp()).resolve()
        self.addCleanup(shutil.rmtree, work, True)
        (work / "t").mkdir(); (work / "base").mkdir()
        shutil.copy(CONFTEST, work / "t/conftest.py")
        (work / "t/test_probe.py").write_text(PROBE)
        env = dict(os.environ, TMPDIR=str(work / "base"))
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", str(work / "t")],
                           capture_output=True, text=True, env=env, cwd=work / "t")
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(sorted(p.name for p in (work / "base").iterdir()), [])


if __name__ == "__main__":
    unittest.main()
