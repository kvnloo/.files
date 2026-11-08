"""Regression tests for dash_push notice-item parsing (fix/dash-push-items-not-dict-20261107).

The watcher crashed (AttributeError at dash_push.py:80) when notices.json held bare
string items instead of dicts; it restarts every ~10 s and never pushes. This suite
reproduces that class and locks in tolerant parsing.
"""
import importlib.machinery
import os
import tempfile
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


class PhoneIpResolution(unittest.TestCase):
    """phone_ip() must never return a hard-coded tailnet address."""

    def setUp(self):
        self._saved_env = os.environ.pop("DASH_PHONE_IP", None)
        self._saved_config = dp.PHONE_IP_CONFIG
        self.tmp = Path(tempfile.mkdtemp(prefix="dash-push-test-"))
        dp.PHONE_IP_CONFIG = self.tmp / "phone.env"

    def tearDown(self):
        if self._saved_env is None:
            os.environ.pop("DASH_PHONE_IP", None)
        else:
            os.environ["DASH_PHONE_IP"] = self._saved_env
        dp.PHONE_IP_CONFIG = self._saved_config

    def test_phone_ip_from_env(self):
        os.environ["DASH_PHONE_IP"] = "100.117.226.39"
        self.assertEqual(dp.phone_ip(), "100.117.226.39")

    def test_phone_ip_from_local_config(self):
        dp.PHONE_IP_CONFIG.write_text("# local only, never in git\nPHONE_IP=100.117.226.39\n")
        self.assertEqual(dp.phone_ip(), "100.117.226.39")

    def test_phone_ip_config_strips_quotes(self):
        dp.PHONE_IP_CONFIG.write_text('PHONE_IP=" 100.117.226.39 "\n')
        self.assertEqual(dp.phone_ip(), "100.117.226.39")

    def test_phone_ip_env_wins_over_config(self):
        os.environ["DASH_PHONE_IP"] = "100.117.226.39"
        dp.PHONE_IP_CONFIG.write_text("PHONE_IP=100.64.0.1\n")
        self.assertEqual(dp.phone_ip(), "100.117.226.39")

    def test_phone_ip_unset_fail_closed(self):
        dp.PHONE_IP_CONFIG.write_text("# nothing configured\n")
        self.assertEqual(dp.phone_ip(), "")
        self.assertEqual(dp.phone_serial(), None)

    def test_no_hard_coded_tailnet_address(self):
        source = Path(dp.__file__).read_text()
        self.assertNotIn("100.117.226.39", source)
        self.assertNotIn('(owner 2026-11-03:', source)
        self.assertNotIn('"notifications only happen if i open the app"', source.lower())


if __name__ == "__main__":
    unittest.main()
