import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch


spec = importlib.util.spec_from_file_location("hermes_guard", Path(__file__).with_name("__init__.py"))
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)


class HermesGuardTests(unittest.TestCase):
    def test_custody_cases(self):
        cases = json.loads((Path(__file__).parent.parent / "custody-cases.json").read_text())
        for name, args, denied in cases:
            with self.subTest(name=name, args=args):
                result = plugin.pre_tool_call(name, args)
                self.assertEqual(result is not None and result["action"] == "block", denied)

    def test_registration(self):
        class Context:
            def register_hook(self, name, handler):
                self.name, self.handler = name, handler
        ctx = Context()
        plugin.register(ctx)
        self.assertEqual(ctx.name, "pre_tool_call")
        self.assertIs(ctx.handler, plugin.pre_tool_call)

    def test_real_guard_subprocess(self):
        for name, args in [
            ("terminal", {"command": "sudo pass-cli --help"}),
            ("read_file", {"path": "~/.gnupg/key"}),
            ("search_files", {"path": "/var/lib/passd", "pattern": "x"}),
            ("write_file", {"path": "~/.local/share/proton-pass/state"}),
            ("patch", {"patch": "*** Begin Patch\n*** Update File: /var/lib/passd/db\n*** End Patch"}),
            ("execute_code", {"code": 'import subprocess; subprocess.run(["pass-cli"])'}),
            ("mcp__exec", {"command": "secret-tool lookup x y"}),
        ]:
            with self.subTest(name=name):
                self.assertEqual(plugin.pre_tool_call(name, args)["action"], "block")
        for name, args in [
            ("terminal", {"command": "grep pass-cli docs/README.md"}),
            ("write_file", {"path": "docs.md", "content": "pass-cli ~/.gnupg/key"}),
            ("execute_code", {"code": "print(42)"}),
        ]:
            self.assertIsNone(plugin.pre_tool_call(name, args))

    def test_failures_block_without_echo(self):
        for result in (subprocess.CompletedProcess([], 1, "CANARY", "CANARY"),
                       subprocess.CompletedProcess([], 0, "CANARY", "")):
            with patch.object(plugin.subprocess, "run", return_value=result):
                self.assertEqual(plugin.pre_tool_call("terminal", {"command": "pwd"}), plugin.FAILURE)
        for error in (OSError(), subprocess.TimeoutExpired("CANARY", 5)):
            with patch.object(plugin.subprocess, "run", side_effect=error):
                self.assertEqual(plugin.pre_tool_call("terminal", {}), plugin.FAILURE)


if __name__ == "__main__":
    unittest.main()
