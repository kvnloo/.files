"""Exercise exact production probe function without importing unrelated adapters."""
import ast
import json
from pathlib import Path
import subprocess
import sys
import types
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]


def load_probe(source):
    tree = ast.parse(source)
    names = {'decode_probe_output', 'probe', 'probe_error'}
    selected = ast.Module(body=[node for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in names], type_ignores=[])
    namespace = {'json': json, 'subprocess': subprocess, 'sys': sys, 'REPO': ROOT}
    exec(compile(selected, 'fleet-production-probe', 'exec'), namespace)
    return namespace['probe']


class BoatProbeTests(unittest.TestCase):
    def setUp(self):
        self.probe = load_probe((ROOT/'scripts/fleet').read_text())
        self.node = {'name': 'boat', 'kind': 'boat', 'role': 'worker'}

    def response(self, output, code=0, stderr=''):
        with patch.object(subprocess, 'run', return_value=types.SimpleNamespace(
                stdout=output, stderr=stderr, returncode=code)):
            return self.probe(self.node)

    def test_pretty_boat_json_document(self):
        result = self.response(json.dumps({'canStart': True, 'machineTypes': [{'name': 'cpu'}]}, indent=2))
        self.assertTrue(result['boat_limits']['canStart'])

    def test_compact_and_ssh_banner_last_line_are_compatible(self):
        for text in ('{"canStart":false}', 'banner\n{"canStart":false}\n'):
            self.assertFalse(self.response(text)['boat_limits']['canStart'])

    def test_failed_transport_cannot_use_valid_stdout_or_leak_stderr(self):
        result = self.response('{"canStart":true}', 1, 'PRIVATE_CREDENTIAL')
        self.assertEqual(result['status'], 'probe_error')
        self.assertNotIn('boat_limits', result)
        self.assertNotIn('PRIVATE_CREDENTIAL', json.dumps(result))

    def test_arrays_empty_and_malformed_never_invent_capacity(self):
        for text in ('', '[]', 'null', '{broken', 'banner\n{\n"canStart":true\n}'):
            self.assertEqual(self.response(text)['status'], 'probe_error')


if __name__ == '__main__':
    unittest.main()
