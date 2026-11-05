#!/usr/bin/env python3
"""RP10: the chiefstaff profile is retired; nothing tracked may run tools from its bin/ (bws lives in ~/.hermes/tools)."""
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[1]


class NoRetiredProfileBin(unittest.TestCase):
    def test_no_tracked_file_runs_chiefstaff_bin(self):
        hits = subprocess.run(["git", "grep", "-n", "profiles/chiefstaff/bin", "--", ".", ":!tests/test_no_retired_profile_bin.py"],
                              cwd=ROOT, capture_output=True, text=True).stdout
        self.assertEqual(hits, "")

    def test_bws_default_is_the_shared_tools_copy(self):
        self.assertIn(".hermes/tools/bws-2.0.0-linux-x64/bws", (ROOT / "scripts/bws-env-exec").read_text())
        unit = (ROOT / "config/systemd/user/uniichat-luna.service").read_text()
        self.assertIn("/home/kvn/.hermes/tools/bws-2.0.0-linux-x64:", unit)


if __name__ == "__main__":
    unittest.main()
