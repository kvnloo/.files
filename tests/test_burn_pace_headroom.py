"""Regression for premature stops and stale copies hiding usable Claude accounts."""
import importlib.machinery
import json
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
bp = importlib.machinery.SourceFileLoader("burn_pace_headroom", str(ROOT / "scripts/burn-pace")).load_module()


class Headroom(unittest.TestCase):
    def test_remaining_quota_is_not_reported_exhausted(self):
        for used in (95, 96, 99.9, 100):
            with self.subTest(used=used):
                self.assertEqual(bp.knobs(0.3, used)["band"] == "hard-stop-exhausted", used >= 100)

    def test_probe_uses_native_account_credentials_not_stale_pool_copy(self):
        with tempfile.TemporaryDirectory() as tmp, patch.object(bp.Path, "home", return_value=Path(tmp)):
            home = Path(tmp)
            pool = home / ".hermes/auth.json"
            pool.parent.mkdir(parents=True)
            pool.write_text(json.dumps({"credential_pool": {"anthropic": [
                {"label": "claude-sub2", "access_token": "sk-ant-oat-stale-test"}]}}))
            native = home / ".claude-sub2/.credentials.json"
            native.parent.mkdir()
            native.write_text(json.dumps({"claudeAiOauth": {
                "accessToken": "sk-ant-oat-current-test", "expiresAt": (time.time() + 3600) * 1000}}))
            self.assertEqual(bp._pool_token("claude-sub2"), "sk-ant-oat-current-test")
            native.write_text(json.dumps({"claudeAiOauth": {
                "accessToken": "sk-ant-oat-expired-test", "expiresAt": (time.time() - 1) * 1000}}))
            self.assertEqual(bp._pool_token("claude-sub2"), "sk-ant-oat-stale-test")
            native.unlink()
            self.assertEqual(bp._pool_token("claude-sub2"), "sk-ant-oat-stale-test")


if __name__ == "__main__":
    unittest.main()
