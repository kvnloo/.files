"""Run directly with python3 -B tests/test_research_engine.py."""
import contextlib
import io
from pathlib import Path
import runpy
import sys
import tempfile
import unittest
from unittest.mock import patch


CANONICAL = Path('/mnt/zer0models/workspace/zer0/products/pilot-program/engine/abab_state.py')
LAUNCHER = Path(__file__).resolve().parents[1] / 'scripts/research'


class ResearchEngineTest(unittest.TestCase):
    def setUp(self):
        self.cli = runpy.run_path(str(LAUNCHER))
        self.globals = self.cli['engine'].__globals__
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def test_configured_source(self):
        self.assertEqual(self.cli['ENGINE'], CANONICAL)

    @unittest.skipUnless(CANONICAL.is_file(), 'requires local pilot-program checkout')
    def test_canonical_source(self):
        module = self.cli['engine']()
        self.assertEqual(Path(module.__file__), CANONICAL.resolve(strict=True))

    def assert_unavailable(self, expected):
        with patch.dict(self.globals, ENGINE=expected):
            with self.assertRaises(SystemExit) as caught:
                self.cli['engine']()
        self.assertIn('research: ABAB engine unavailable', str(caught.exception))
        self.assertIn(str(expected), str(caught.exception))
        self.assertNotIn('ModuleNotFoundError', str(caught.exception))

    def test_missing_engine_names_expected_path(self):
        self.assert_unavailable(self.root / 'missing/abab_state.py')

    def test_dangling_engine_names_expected_path(self):
        link = self.root / 'abab_state.py'
        link.symlink_to(self.root / 'deleted/abab_state.py')
        self.assert_unavailable(link)

    def test_directory_is_not_an_engine(self):
        self.assert_unavailable(self.root)

    @unittest.skipUnless(CANONICAL.is_file(), 'requires local pilot-program checkout')
    def test_pythonpath_cannot_shadow_canonical_engine(self):
        (self.root / 'abab_state.py').write_text("raise RuntimeError('wrong engine')\n")
        with patch.object(sys, 'path', [str(self.root), *sys.path]):
            module = self.cli['engine']()
        self.assertEqual(Path(module.__file__), CANONICAL.resolve(strict=True))

    @unittest.skipUnless(CANONICAL.is_file(), 'requires local pilot-program checkout')
    def test_new_and_status_round_trip(self):
        output = io.StringIO()
        with patch.dict(self.globals, ROOT=self.root), contextlib.redirect_stdout(output):
            self.assertEqual(self.cli['main'](['new', 'fixture', 'RES2 round trip']), 0)
            self.assertEqual(self.cli['main'](['status', 'fixture']), 0)
            self.assertEqual(self.cli['main'](['new', 'fixture', 'must not overwrite']), 1)
        self.assertIn('objective: RES2 round trip', output.getvalue())
        self.assertIn('wave 0 | evidence 0 | experiments 0', output.getvalue())
        self.assertEqual(self.cli['engine']().load(self.root / 'fixture/world.json').objective, 'RES2 round trip')

    def test_help_and_list_do_not_require_engine(self):
        with patch.dict(self.globals, ENGINE=self.root / 'absent', ROOT=self.root):
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(self.cli['main'](['--help']), 0)
                self.assertEqual(self.cli['main'](['list']), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
