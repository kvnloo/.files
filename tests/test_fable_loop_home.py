"""The fix loop (astra/fable drains, fix-replay) ran from live-only copies no repo held: agents
edited them in place with no history (home tools/sysgraph.py `unhomed`). These are the sourced
copies; they must resolve per-user paths from $HOME, never a literal home, because this repo is public."""
import importlib.machinery, importlib.util, os, re, unittest
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


if __name__ == "__main__":
    unittest.main()
