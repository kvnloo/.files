"""The fix loop (astra/fable drains, fix-replay) ran from live-only copies no repo held: agents
edited them in place with no history (home tools/sysgraph.py `unhomed`). These are the sourced
copies; they must resolve per-user paths from $HOME, never a literal home, because this repo is public."""
import importlib.machinery, importlib.util, json, os, re, unittest
from pathlib import Path
from unittest import mock

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
LOOP = ("astra-drain", "fable-drain", "fable-phase-watch", "fable-ingest", "fable-packet", "fix-replay")


def load(name):
    loader = importlib.machinery.SourceFileLoader(name.replace("-", "_"), str(SCRIPTS / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class FableLoopHome(unittest.TestCase):
    def test_loop_scripts_compile_and_name_no_literal_home(self):
        for name in LOOP:
            source = (SCRIPTS / name).read_text()
            compile(source, name, "exec")
            self.assertIsNone(re.search(r"/home/[a-z]", source), name)

    def test_per_user_paths_follow_home(self):
        with mock.patch.dict(os.environ, {"HOME": "/nonexistent/u"}):
            astra, fable = load("astra-drain"), load("fable-drain")
        self.assertEqual(astra.BIN, Path("/nonexistent/u/.local/bin"))
        self.assertEqual(fable.BIN, Path("/nonexistent/u/.local/bin"))
        self.assertIn(Path("/nonexistent/u/.hermes/hermes-agent"), astra.REPO_ROOTS)

    def test_noop_queue_update_leaves_the_file_alone(self):
        """astra-drain.path fires on queue writes; a drain run that changed nothing must not write."""
        import tempfile
        ingest = load("fable-ingest")
        with tempfile.TemporaryDirectory() as d:
            q = Path(d, "astra-queue.json")
            q.write_text(json.dumps({"jobs": [{"id": "a", "status": "applied"}]}))
            before = os.stat(q)
            self.assertEqual(ingest.update(q, lambda data: 0), 0)
            after = os.stat(q)
            self.assertEqual((before.st_ino, before.st_mtime_ns), (after.st_ino, after.st_mtime_ns))
            ingest.update(q, lambda data: data["jobs"].append({"id": "b", "status": "pending"}))
            self.assertEqual([j["id"] for j in json.loads(q.read_text())["jobs"]], ["a", "b"])

    def test_drain_path_unit_watches_the_queue_the_drain_reads(self):
        unit = (SCRIPTS.parent / "config/systemd/user/astra-drain.path").read_text()
        watched = re.findall(r"^PathChanged=(.+)$", unit, re.M)
        default = re.search(r'"ASTRA_OPS", "([^"]+)"', (SCRIPTS / "astra-drain").read_text()).group(1)
        self.assertEqual(watched, [f"{default}/astra-queue.json"])
        self.assertIn("Unit=astra-drain.service", unit)

    def test_fix_replay_keeps_failure_evidence_out_of_the_journal(self):
        """Its stdout lands in the journal. Printing the board there quoted each tape's failure text,
        so tapes grepping the journal for 'Failed with result' matched fix-replay itself and stayed red."""
        import subprocess, sys, tempfile
        with tempfile.TemporaryDirectory() as ops:
            Path(ops, "fix-tapes.json").write_text(json.dumps({"tapes": [
                {"id": "t", "class": "c", "what": "w", "tape": "echo \"x.service: Failed with result 'exit-code'\"; exit 1"}]}))
            env = {**os.environ, "FIX_OPS": ops, "HOME": ops}
            out = subprocess.run([sys.executable, str(SCRIPTS / "fix-replay")], env=env,
                                 capture_output=True, text=True, timeout=60).stdout
            self.assertIn("Failed with result", Path(ops, "BOARD.md").read_text())
        self.assertNotIn("Failed with result", out)
        self.assertIn("1 open", out)


if __name__ == "__main__":
    unittest.main()
