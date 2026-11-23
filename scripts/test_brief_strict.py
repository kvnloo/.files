"""brief-sent.json must record 'sent' only after a real delivery (v0 fallback included).

Run: SCRIPT=<path to limitless-sync> python3 -I test_brief_strict.py
The fake dash-report behaves like the real one: circadian may hold (exit 0) unless CIRCADIAN_BYPASS is
set, then it execs kevin-push, which exits 0 unless KEVIN_PUSH_STRICT=1 and the message was not delivered.
"""
import importlib.machinery
import importlib.util
import json
import os
import stat
import sys
import tempfile
import unittest
from datetime import date
from pathlib import Path

SCRIPT = os.environ["SCRIPT"]


def load():
    loader = importlib.machinery.SourceFileLoader("limitless_sync_under_test", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


FAKE_DASH = """#!/bin/sh
if [ -z "${CIRCADIAN_BYPASS:-}" ]; then echo held; exit 0; fi
if [ "${DELIVER:-0}" = 1 ]; then exit 0; fi
if [ "${KEVIN_PUSH_STRICT:-}" = 1 ]; then exit 3; fi
exit 0
"""
FAKE_BRIEF = """#!/bin/sh
echo '{"notify_rc": 3}'
"""


class BriefStrict(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        home = Path(self.tmp.name)
        b = home / ".local/bin"
        b.mkdir(parents=True)
        for name, body in (("dash-report", FAKE_DASH), ("limitless-brief", FAKE_BRIEF)):
            p = b / name
            p.write_text(body)
            p.chmod(p.stat().st_mode | stat.S_IXUSR)
        self.st = home / "state"
        self.st.mkdir()
        self.mod = load()
        self.mod.Path.home = classmethod(lambda cls: home)   # module's own Path import
        self.mod.first_unlock_today = lambda st, tz, today: True
        self.mod.brief_line = lambda dg: "synthetic line"
        self.cfg = {"tz": "UTC", "brief": True}
        self.old_env = dict(os.environ)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.old_env)
        self.tmp.cleanup()

    def test_fallback_not_delivered_is_not_marked_sent(self):
        os.environ.pop("DELIVER", None)
        got = self.mod.maybe_brief(self.cfg, self.st, {}, date(2030, 1, 2))
        self.assertFalse((self.st / "brief-sent.json").exists(), got)
        self.assertNotIn("sent", got)

    def test_fallback_delivered_is_marked_sent(self):
        os.environ["DELIVER"] = "1"
        got = self.mod.maybe_brief(self.cfg, self.st, {}, date(2030, 1, 2))
        self.assertTrue((self.st / "brief-sent.json").exists(), got)
        self.assertEqual(json.loads((self.st / "brief-sent.json").read_text())["day"], "2030-01-02")


if __name__ == "__main__":
    unittest.main(verbosity=2)
