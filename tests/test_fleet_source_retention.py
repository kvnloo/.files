import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import time
import types
import unittest
from unittest.mock import patch

SCRIPTS = Path(__file__).parents[1] / 'scripts'
sys.path.insert(0, str(SCRIPTS))
spec = importlib.util.spec_from_file_location('source_retention', SCRIPTS / 'fleet-source-retention.py')
retention = importlib.util.module_from_spec(spec)
spec.loader.exec_module(retention)


class RetentionTests(unittest.TestCase):
    def exercise(self, *, errors=(), live=False, terminal=True, apply=True, invalid=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runs = root / 'runs'
            source = runs / 'job' / 'src'
            source.mkdir(parents=True)
            (source / 'kept-user-bytes').write_text('preserve all bytes')
            job = source.parent
            (job / 'receipt.json').write_text('keep receipt')
            (job / '.artifact-lease.json').write_text(json.dumps({'kind': 'spool'}))
            if terminal:
                (job / 'exit').write_text('0')
            backend = types.SimpleNamespace(SIDECAR='.artifact-lease.json', backend=lambda: None,
                local_references=lambda *args: ({str(source / 'kept-user-bytes'): {'live'}} if live else {}, list(errors)),
                validate=lambda *args: 'invalid' if invalid else None)
            loader = types.SimpleNamespace(exec_module=lambda module: None)
            with patch.object(retention, 'runs_dir', return_value=runs), patch.object(retention, 'storage_policy', return_value={'source_retention_days': 7}), patch.object(retention.time, 'time', return_value=time.time() + 8 * 86400), patch.object(retention.importlib.util, 'spec_from_file_location', return_value=types.SimpleNamespace(loader=loader)), patch.object(retention.importlib.util, 'module_from_spec', return_value=backend):
                retention.retain(apply)
            moved = root / 'fleet-source-archive/job'
            should_move = apply and not errors and not live and terminal and not invalid
            self.assertEqual(moved.exists(), should_move)
            self.assertEqual(source.exists(), not should_move)
            self.assertEqual((moved if should_move else source).joinpath('kept-user-bytes').read_text(), 'preserve all bytes')
            self.assertEqual((job / 'receipt.json').read_text(), 'keep receipt')

    def test_archives_source_preserving_bytes_and_receipts(self):
        self.exercise()

    def test_keeps_when_liveness_unknown(self):
        self.exercise(errors=['permission denied'])

    def test_keeps_live_source(self):
        self.exercise(live=True)

    def test_keeps_unknown_terminal(self):
        self.exercise(terminal=False)

    def test_keeps_invalid_lease(self):
        self.exercise(invalid=True)

    def test_dry_run_preserves_source(self):
        self.exercise(apply=False)


if __name__ == '__main__':
    unittest.main()
