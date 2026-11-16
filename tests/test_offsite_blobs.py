"""offsite-blobs end to end against a local restic repo: snapshot taken, file restorable, manifest written."""
import json, os, shutil, subprocess, tempfile, unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/offsite-blobs"


@unittest.skipUnless(shutil.which("restic"), "restic not installed")
class Blobs(unittest.TestCase):
    def test_backup_restores_and_writes_manifest(self):
        t = Path(tempfile.mkdtemp())
        src = t / "project-artifacts/quackles/dreamloop-runs/day"; src.mkdir(parents=True)
        (src / "r1.blend").write_bytes(b"blend" * 1000)
        (src / "node_modules").mkdir(); (src / "node_modules/x.js").write_text("dep")
        (t / "pass").write_text("test-pass")
        env = dict(os.environ, RESTIC_REPOSITORY=str(t / "repo"), RESTIC_PASSWORD_FILE=str(t / "pass"),
                   OFFSITE_OPS=str(t / "ops"), OFFSITE_BLOBS_SRC=str(t / "project-artifacts"))
        subprocess.run(["restic", "init", "-q"], env=env, check=True, capture_output=True)
        r = subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stderr)
        m = json.loads((t / "ops/offsite-latest.json").read_text())
        self.assertEqual(m["paths"], [str(t / "project-artifacts")])
        subprocess.run(["restic", "restore", m["snapshot"], "--target", str(t / "out")], env=env, check=True,
                       capture_output=True)
        self.assertEqual((t / "out" / str(src / "r1.blend").lstrip("/")).read_bytes(), b"blend" * 1000)
        self.assertFalse((t / "out" / str(src / "node_modules").lstrip("/")).exists())


if __name__ == "__main__":
    unittest.main()
