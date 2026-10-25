import importlib.util
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('release_retention', Path(__file__).parents[1] / 'scripts/release-retention.py')
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


class ReleaseRetentionTests(unittest.TestCase):
    def test_references_match_tree_not_text_prefix(self):
        source = Path('/home/kvn/.local/lib/test/' + 'a' * 40)
        self.assertTrue(retention.referenced(source, [str(source / 'python')]))
        self.assertFalse(retention.referenced(source, [str(source) + 'b/python']))
        self.assertTrue(retention.referenced(source, ['hostPath:/home/kvn']))
        self.assertFalse(retention.referenced(source, ['hostPath:/workspace']))

    def test_plan_preserves_current_previous_and_live_releases(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            family = root / 'family'
            family.mkdir()
            releases = []
            for index, name in enumerate('abcd'):
                path = family / (name * 40)
                path.mkdir()
                os.utime(path, (index, index))
                releases.append(path)
            (family / 'current').symlink_to(releases[3])
            evidence = {'errors': [], 'references': [str(releases[0] / 'bin/python')]}
            with patch.object(retention, 'BASE', root), patch.object(retention.subprocess, 'check_output', return_value='100 path'):
                rows = retention.plan(evidence)
            eligible = [row['source'] for row in rows if not row['keep']]
            self.assertEqual(eligible, [str(releases[1])])
            self.assertTrue(releases[1].exists())

    def test_unknown_visibility_keeps_every_release(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            family = root / 'family'
            family.mkdir()
            for name in 'abc':
                (family / (name * 40)).mkdir()
            with patch.object(retention, 'BASE', root), patch.object(retention.subprocess, 'check_output', return_value='100 path'):
                rows = retention.plan({'errors': ['maps denied'], 'references': []})
            self.assertTrue(all(row['keep'] for row in rows))


if __name__ == '__main__':
    unittest.main()
