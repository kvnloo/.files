"""limitless-sync lives in a public repo: no private paths, device ids or names; host specifics come from config.

Run: SCRIPT=<path to limitless-sync> python3 -I test_limitless_sync_public.py
"""
import importlib.machinery
import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path

SCRIPT = os.environ["SCRIPT"]

PRIVATE = [
    (r"/mnt/", "a host mount path"),
    (r"(?<![\w.])/workspace/", "a host workspace path"),
    (r"/home/\w", "a home directory"),
    (r"SM_[A-Z]\d{3}", "a phone model id"),
    (r"R5C[A-Z0-9]{6,}", "a device serial"),
    (r"\bKevin\b", "the owner's name"),
    (r"ts\.net|100\.\d+\.\d+\.\d+|192\.168\.", "a host address"),
]


def load():
    loader = importlib.machinery.SourceFileLoader("limitless_sync_under_test", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


class PublicHygiene(unittest.TestCase):
    def test_no_private_strings(self):
        text = Path(SCRIPT).read_text()
        hits = [(why, m.group(0)) for pat, why in PRIVATE for m in re.finditer(pat, text)]
        self.assertEqual(hits, [])


class FocusSafeFromConfig(unittest.TestCase):
    def setUp(self):
        self.mod = load()
        self.calls = []
        real = self.mod.subprocess.run

        def fake(cmd, **kw):
            self.calls.append((cmd, kw))

            class R:
                returncode = 0
            return R()
        self.mod.subprocess.run = fake
        self.addCleanup(setattr, self.mod.subprocess, "run", real)

    def test_unset_dir_runs_nothing(self):
        rc = self.mod.focus_safe_start({}, "pkg/.Main")
        self.assertNotEqual(rc, 0)
        self.assertEqual(self.calls, [])

    def test_dir_and_cache_come_from_config(self):
        rc = self.mod.focus_safe_start({"focusSafeDir": "/tmp/fs", "uvCacheDir": "/tmp/uvc"}, "pkg/.Main")
        self.assertEqual(rc, 0)
        (cmd, kw), = self.calls
        self.assertEqual(str(kw["cwd"]), "/tmp/fs")
        self.assertEqual(kw["env"]["UV_CACHE_DIR"], "/tmp/uvc")
        self.assertIn("pkg/.Main", cmd[-1])

    def test_model_comes_from_config_only(self):
        out = "List of devices attached\nabc device usb:1 model:XYZ_1 transport_id:1\n"

        def fake(cmd, **kw):
            class R:
                stdout = out
                returncode = 0
            return R()
        self.mod.subprocess.run = fake
        self.assertEqual(self.mod.resolve_s25_serial({"adb": "adb", "s25Model": "XYZ_1"}), "abc")
        self.assertIsNone(self.mod.resolve_s25_serial({"adb": "adb"}))


if __name__ == "__main__":
    unittest.main()
