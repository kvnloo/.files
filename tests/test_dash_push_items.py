"""Regression tests for dash_push notice-item parsing (fix/dash-push-items-not-dict-20261107).

The watcher crashed (AttributeError at dash_push.py:80) when notices.json held bare
string items instead of dicts; it restarts every ~10 s and never pushes. This suite
reproduces that class and locks in tolerant parsing.
"""
import importlib.machinery
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
dp = importlib.machinery.SourceFileLoader(
    "dash_push", str(ROOT / "scripts/dash-push/dash_push.py")).load_module()


class NoticeItemsParsing(unittest.TestCase):
    def test_dict_items_with_ids_pass_through(self):
        payload = {"schema": "v1", "items": [
            {"id": "a", "title": "t1"}, {"id": "b", "title": "t2"},
            {"title": "no id"}, 123, None,
        ]}
        ids = [x["id"] for x in dp.notice_items(payload)]
        self.assertEqual(ids, ["a", "b"])

    def test_bare_string_items_never_crash(self):
        payload = {"schema": "v1", "items": ["a-bare-string-id", "just text"]}
        items = dp.notice_items(payload)
        self.assertEqual(items, [])

    def test_items_keyed_by_id_as_dict_never_crash(self):
        payload = {"schema": "v1", "items": {
            "a": {"id": "a", "title": "t1"},
            "b": {"title": "t2"},
        }}
        ids = [x["id"] for x in dp.notice_items(payload)]
        self.assertEqual(ids, ["a"])

    def test_top_level_list_payload(self):
        payload = [{"id": "x", "title": "tx"}, "stray string"]
        items = dp.notice_items(payload)
        self.assertEqual([x["id"] for x in items], ["x"])

    def test_plain_string_payload(self):
        self.assertEqual(dp.notice_items("not json"), [])

    def test_null_payload(self):
        self.assertEqual(dp.notice_items(None), [])


if __name__ == "__main__":
    unittest.main()
