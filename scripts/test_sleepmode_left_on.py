"""A Sleep rule left on all day must not hold every push: after a long-on rule plus proof the owner is up
(an own message or a phone unlock), the poller writes one inferred off row and ignores that same rule after.

Run: SCRIPT=<path to limitless-sync> python3 -I test_sleepmode_left_on.py
Synthetic phone output and a fixed clock only; nothing is sent (nap_return is stubbed).
"""
import importlib.machinery
import importlib.util
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCRIPT = os.environ["SCRIPT"]
NOW = datetime(2030, 1, 2, 12, 0, tzinfo=timezone.utc)


def load():
    loader = importlib.machinery.SourceFileLoader("limitless_sync_under_test", SCRIPT)
    spec = importlib.util.spec_from_loader(loader.name, loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def rule_text(created: datetime) -> str:
    ms = int(created.timestamp() * 1000)
    return (f"ZenRule[id=abc123,state=STATE_TRUE,enabled=TRUE,snoozing=false,name=Sleep,zenMode=1,"
            f"conditionId=scheme:,creationTime={ms}]\n")


class LeftOn(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.st = Path(self.tmp.name)
        self.mod = load()
        self.phone = ""
        self.unlocks = []
        self.msg = None
        self.returns = []
        self.mod.adb = lambda cfg, *a, timeout=30: self.phone
        self.mod.first_owner_msg_after = lambda after: self.msg if self.msg and self.msg > after else None
        self.mod.aw_events = lambda st: (sorted(self.unlocks), [], max(self.unlocks or [0]))

        def nap(cfg, start, end):
            self.returns.append((start, end))
            return "stub"
        self.mod.nap_return = nap
        self.cfg = {"tz": "UTC"}

    def tearDown(self):
        self.tmp.cleanup()

    def rows(self):
        p = self.st / "sleepmode.jsonl"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []

    def seed_on(self, created, at=None):
        row = {"at": self.mod.iso(at or created), "on": True, "seen": self.mod.iso(at or created)}
        (self.st / "sleepmode.jsonl").write_text(json.dumps(row) + "\n")

    def test_rule_on_far_longer_than_a_night_with_an_unlock_is_closed_once(self):
        created = NOW - timedelta(hours=20)
        self.seed_on(created)
        self.phone = rule_text(created)
        self.unlocks = [(NOW - timedelta(hours=2)).timestamp()]
        got = self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        last = self.rows()[-1]
        self.assertFalse(last["on"], got)
        self.assertEqual(last["left_on"], str(int(created.timestamp() * 1000)))
        self.assertEqual(len(self.returns), 1)

    def test_the_same_rule_still_on_after_closing_is_ignored(self):
        created = NOW - timedelta(hours=20)
        self.seed_on(created)
        self.phone = rule_text(created)
        self.unlocks = [(NOW - timedelta(hours=2)).timestamp()]
        self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        n = len(self.rows())
        got = self.mod.sync_sleepmode(self.cfg, self.st, NOW + timedelta(minutes=2))
        self.assertEqual(len(self.rows()), n, got)
        self.assertFalse(self.rows()[-1]["on"])

    def test_a_night_length_rule_stays_on_despite_an_unlock(self):
        created = NOW - timedelta(hours=3)
        self.seed_on(created)
        self.phone = rule_text(created)
        self.unlocks = [(NOW - timedelta(hours=1)).timestamp()]
        got = self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        self.assertEqual(got, "on (unchanged)")
        self.assertEqual(len(self.rows()), 1)

    def test_a_long_rule_with_no_sign_of_the_owner_stays_on(self):
        created = NOW - timedelta(hours=20)
        self.seed_on(created)
        self.phone = rule_text(created)
        got = self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        self.assertEqual(got, "on (unchanged)")
        self.assertEqual(len(self.rows()), 1)

    def test_an_owner_message_also_proves_the_owner_is_up(self):
        created = NOW - timedelta(hours=20)
        self.seed_on(created)
        self.phone = rule_text(created)
        self.msg = (NOW - timedelta(hours=1)).timestamp()
        self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        self.assertFalse(self.rows()[-1]["on"])

    def test_activity_only_before_the_long_mark_proves_nothing(self):
        created = NOW - timedelta(hours=20)
        self.seed_on(created)
        self.phone = rule_text(created)
        self.unlocks = [(created + timedelta(hours=2)).timestamp()]
        got = self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        self.assertEqual(got, "on (unchanged)")

    def test_a_new_activation_after_a_left_on_close_counts_again(self):
        created = NOW - timedelta(hours=20)
        self.seed_on(created)
        self.phone = rule_text(created)
        self.unlocks = [(NOW - timedelta(hours=2)).timestamp()]
        self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        fresh = NOW + timedelta(hours=1)
        self.phone = rule_text(fresh)
        got = self.mod.sync_sleepmode(self.cfg, self.st, fresh + timedelta(minutes=1))
        self.assertEqual(got, "on")
        self.assertTrue(self.rows()[-1]["on"])

    def test_an_unreachable_inferred_off_keeps_the_rule_ignored_when_the_phone_returns(self):
        created = NOW - timedelta(hours=5)
        self.phone = rule_text(created)
        self.mod.sync_sleepmode(self.cfg, self.st, created + timedelta(minutes=1))   # opens with the rule
        self.assertTrue(self.rows()[-1]["on"])

        def gone(cfg, *a, timeout=30):
            raise RuntimeError("unreachable")
        self.mod.adb = gone
        self.msg = (NOW - timedelta(hours=1)).timestamp()
        self.mod.sync_sleepmode(self.cfg, self.st, NOW)
        self.assertFalse(self.rows()[-1]["on"])
        self.mod.adb = lambda cfg, *a, timeout=30: self.phone
        n = len(self.rows())
        got = self.mod.sync_sleepmode(self.cfg, self.st, NOW + timedelta(minutes=2))
        self.assertEqual(len(self.rows()), n, got)


if __name__ == "__main__":
    unittest.main(verbosity=2)
