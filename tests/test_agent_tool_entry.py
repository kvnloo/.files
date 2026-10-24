"""Entry policy fixtures: no build, browser, or compositor is ever launched."""
import importlib.machinery
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
entry=importlib.machinery.SourceFileLoader('agent_tool_entry',str(ROOT/'scripts/agent-tool-run')).load_module()

class EntryPolicy(unittest.TestCase):
    def test_known_cpu_work_and_mentions_gpu_remote(self):
        for command in ('cargo build','bun test','python3 -m pytest tests','ffmpeg -i input -c:v libx264 out',
                        'blender --background model.blend'):
            self.assertIsNotNone(entry.blocked(['bash','-c',command]),command)
        for command in ("printf 'cargo build'", "ssh mbp 'cargo build'",'fleet-build -- cargo test',
                        'ffmpeg -i in -c:v h264_nvenc out',
                        'blender --background model.blend -- --cycles-device OPTIX'):
            self.assertIsNone(entry.blocked(['bash','-c',command]),command)

    def test_explicit_interactive_program_has_no_workload_quota(self):
        with patch.object(sys,'argv',['agent-tool-run','--','firefox']), \
             patch.object(entry.socket,'gethostname',return_value='groot'), \
             patch.object(entry.subprocess,'run',return_value=types.SimpleNamespace(returncode=0)) as run:
            with self.assertRaises(SystemExit) as e:entry.main()
            self.assertEqual(e.exception.code,0)
            argv=run.call_args.args[0]
            self.assertIn('--slice=app.slice',argv)
            self.assertFalse(any('CPUQuota' in x or 'MemoryMax' in x for x in argv))

    def test_scope_failure_never_direct_exec_fallback(self):
        with patch.object(sys,'argv',['agent-tool-run','--','sh','-c','true']), \
             patch.object(entry.socket,'gethostname',return_value='groot'), \
             patch.object(entry.subprocess,'run',side_effect=FileNotFoundError('no systemd-run')), \
             patch.object(entry.os,'execvp',side_effect=AssertionError('unsafe direct fallback')):
            with self.assertRaises(SystemExit) as e:entry.main()
            self.assertEqual(e.exception.code,75)

if __name__=='__main__':unittest.main()
