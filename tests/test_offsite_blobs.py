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

    def test_a_second_run_skips_while_one_holds_the_lock(self):
        # 2026-11-16: a manual start overlapped a running backup; two restics split Drive's per-minute
        # quota and both kept failing on rateLimitExceeded/500. Only one run may talk to the repo.
        t = Path(tempfile.mkdtemp())
        (t / "src").mkdir(); (t / "src/a").write_text("a"); (t / "pass").write_text("test-pass")
        (t / "ops").mkdir()
        env = dict(os.environ, RESTIC_REPOSITORY=str(t / "repo"), RESTIC_PASSWORD_FILE=str(t / "pass"),
                   OFFSITE_OPS=str(t / "ops"), OFFSITE_BLOBS_SRC=str(t / "src"))
        subprocess.run(["restic", "init", "-q"], env=env, check=True, capture_output=True)
        holder = subprocess.Popen(["flock", str(t / "ops/offsite-blobs.lock"), "sleep", "30"])
        try:
            for _ in range(50):
                if subprocess.run(["flock", "-n", str(t / "ops/offsite-blobs.lock"), "true"]).returncode:
                    break
                subprocess.run(["sleep", "0.1"])
            r = subprocess.run([str(SCRIPT)], env=env, capture_output=True, text=True, timeout=30)
        finally:
            holder.kill(); holder.wait()
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertIn("another offsite-blobs run", r.stdout + r.stderr)
        self.assertFalse((t / "ops/offsite-latest.json").exists())
        rows = [json.loads(x) for x in next((t / "ops/runs").glob("offsite-*/blobs.jsonl")).read_text().splitlines()]
        self.assertEqual(rows[-1]["skipped"], "locked")
        snaps = subprocess.run(["restic", "snapshots", "--json"], env=env, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(snaps.stdout), [])


if __name__ == "__main__":
    unittest.main()
