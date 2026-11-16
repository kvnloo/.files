"""The Bot Screen's idle stop must not leave failed companion units behind, and a companion that
fails while its display is still up must still fail."""
from importlib.machinery import SourceFileLoader
from importlib.util import module_from_spec, spec_from_loader
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
loader = SourceFileLoader("botscreen_companions", str(ROOT / "scripts/botscreen-companions"))
spec = spec_from_loader(loader.name, loader)
assert spec is not None
bc = module_from_spec(spec)
loader.exec_module(bc)


class RunBound(unittest.TestCase):
    def setUp(self):
        self.x11 = Path(tempfile.mkdtemp())
        self.sock = self.x11 / "X20"

    def run_cmd(self, code: str) -> int:
        return bc.run_bound([sys.executable, "-c", code], ":20", self.x11)

    def test_exit_after_display_stopped_is_a_normal_end(self):
        self.sock.touch()
        # the screen's idle stop removes the X socket while the companion runs; it then exits 1
        self.assertEqual(self.run_cmd(f"import os; os.unlink({str(self.sock)!r}); raise SystemExit(1)"), 0)

    def test_failure_while_display_is_up_still_fails(self):
        self.sock.touch()
        self.assertEqual(self.run_cmd("raise SystemExit(1)"), 1)

    def test_crash_by_signal_is_never_masked(self):
        self.assertLess(self.run_cmd("import os, signal; os.kill(os.getpid(), signal.SIGSEGV)"), 0)

    def test_companions_all_run_on_the_screen_display(self):
        home = Path(tempfile.mkdtemp())
        (home / "bot-desktop").mkdir()
        (home / "bot-desktop/display").write_text("20\n")
        display, bd = bc.screen(home)
        units = bc.companions(home, display, bd)
        self.assertEqual(set(units), {"kvn-chrome-botscreen", "botscreen-chromium", "cua-botscreen"})
        for env, _argv in units.values():
            self.assertEqual((env["DISPLAY"], env["WAYLAND_DISPLAY"]), (":20", ""))


if __name__ == "__main__":
    unittest.main()
