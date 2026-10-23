"""No-network coverage for Avrea dispatch identity, receipts, and exit status."""
import importlib.machinery
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parents[1] / 'scripts/fleet-avrea'
LOADER = importlib.machinery.SourceFileLoader('fleet_avrea', str(PATH))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
CLIENT = importlib.util.module_from_spec(SPEC)
LOADER.exec_module(CLIENT)
SHA = 'a' * 40


class DispatchTests(unittest.TestCase):
    def dispatch(self, code=0, wrong_sha=False, budget_code=0, private=False):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name)
        calls = []
        def fake_process(argv, **kwargs):
            calls.append(argv)
            if argv[0].endswith('fleet-avrea-budget'):
                return subprocess.CompletedProcess(argv, budget_code, json.dumps({'allowed': not budget_code, 'reservation_id': 'reservation', 'max_parallel': 3}))
            if argv[:3] == ['gh', 'run', 'download']:
                receipt_dir = output / 'artifacts/fleet-result-0'
                receipt_dir.mkdir(parents=True)
                (receipt_dir / 'receipt.json').write_text(json.dumps({'repository': 'owner/repo', 'sha': 'b' * 40 if wrong_sha else SHA, 'run_id': '123', 'index': 0, 'exit_code': code, 'duration_seconds': 1.2}))
                return subprocess.CompletedProcess(argv, 0)
            raise AssertionError(argv)
        def fake_gh(*args):
            if args[:2] == ('api', 'repos/owner/repo'):
                return {'private': private, 'visibility': 'private' if private else 'public'}
            if args[:1] == ('api',):
                return {'sha': SHA}
            if args[:2] == ('run', 'list'):
                request = json.loads((output / 'request.json').read_text())
                return [{'databaseId': 999, 'displayTitle': 'fleet-someone-else'}, {'databaseId': 123, 'displayTitle': 'fleet-' + request['request_id']}]
            if args[:2] == ('run', 'view'):
                return {'status': 'completed', 'conclusion': 'success' if not code else 'failure', 'jobs': []}
            raise AssertionError(args)
        argv = ['fleet-avrea', '--repo', 'owner/repo', '--sha', SHA, '--out', str(output), '--', 'python3', '-m', 'unittest']
        with patch.object(sys, 'argv', argv), patch.object(CLIENT, 'gh_json', fake_gh), patch.object(CLIENT.subprocess, 'run', fake_process), patch.object(CLIENT, 'run') as dispatch:
            result = CLIENT.main()
            return result, calls, dispatch.call_args_list, output

    def test_exact_receipt_and_dispatch_identity(self):
        result, calls, dispatch, output = self.dispatch()
        self.assertEqual(result, 0)
        self.assertEqual(json.loads((output / 'run.json').read_text())['id'], 123)
        self.assertTrue(any('settle' in call.args[0] for call in dispatch))
        self.assertTrue(any('--parallel' in argv for argv in calls))

    def test_command_failure_propagates(self):
        self.assertEqual(self.dispatch(code=42)[0], 42)

    def test_wrong_exact_head_refused(self):
        with self.assertRaisesRegex(RuntimeError, 'does not match'):
            self.dispatch(wrong_sha=True)

    def test_budget_refusal_never_dispatches(self):
        result, calls, dispatch, output = self.dispatch(budget_code=75)
        self.assertEqual(result, 75)
        self.assertEqual(dispatch, [])
        self.assertFalse((output / 'request.json').exists())

    def test_private_source_refused(self):
        with self.assertRaises(SystemExit) as error:
            self.dispatch(private=True)
        self.assertEqual(error.exception.code, 2)


if __name__ == '__main__':
    unittest.main()
