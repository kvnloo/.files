"""Managed submission/retention lock protocol; no live fleet effects."""
import importlib.util
from pathlib import Path
import tempfile
import threading
import unittest

spec = importlib.util.spec_from_file_location('stage_lock', Path(__file__).resolve().parents[1] / 'scripts/fleet_stage_lock.py')
locks = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locks)


class StageLockTests(unittest.TestCase):
    def test_retention_waits_for_submission_and_blocks_new_submission(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'lock'
            retention_entered = threading.Event()
            release_retention = threading.Event()
            submission_entered = threading.Event()
            def retain():
                with locks.exclusive_retention_lock(path):
                    retention_entered.set()
                    release_retention.wait(5)
            def submit():
                with locks.submission_lock(path):
                    submission_entered.set()
            with locks.submission_lock(path):
                worker = threading.Thread(target=retain)
                worker.start()
                self.assertFalse(retention_entered.wait(.1))
            try:
                self.assertTrue(retention_entered.wait(2))
                producer = threading.Thread(target=submit)
                producer.start()
                self.assertFalse(submission_entered.wait(.1))
            finally:
                release_retention.set()
                worker.join(3)
                if 'producer' in locals():
                    producer.join(3)
            self.assertTrue(submission_entered.is_set())


if __name__ == '__main__':
    unittest.main()
