import pathlib
import runpy
import unittest


class WorkloadClassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.classify = staticmethod(runpy.run_path(str(pathlib.Path(__file__).parents[1] / 'scripts/fleet-kueue'))['workload_class'])

    def test_pytest_before_exclusive(self):
        self.assertEqual(self.classify(None, ['python3', '-m', 'pytest'], '4', 4), 'test')
        self.assertEqual(self.classify(None, ['/opt/venv/bin/pytest'], '2', 4), 'test')

    def test_explicit_override(self):
        self.assertEqual(self.classify('build', ['pytest'], '4', 4), 'build')

    def test_full_quota_benchmark(self):
        self.assertEqual(self.classify(None, ['python3', 'measure.py'], '4', 4), 'bench')
        self.assertEqual(self.classify(None, ['make'], '2', 4), 'build')

    def test_no_substring_false_positive(self):
        self.assertEqual(self.classify(None, ['cat', 'pytest-results.json'], '2', 4), 'build')
