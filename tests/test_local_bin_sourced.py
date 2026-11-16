"""~/.local/bin tools that timers run must come from this repo, not live-only copies.

home tools/sysgraph.py counts `unhomed` units: code no repo holds, edited in place with no
history or tests. Every managed ~/.local/bin script parses and names no literal home (this
repo is public; resolve per-user paths from $HOME).
"""
from pathlib import Path
import re
import subprocess
import tomllib
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCED = ("gh-pace", "hermes-gateway-rss-restart", "label-drift-doctor", "limitless-sync",
           "owner-canon-sync", "phone-worker", "reset-grant", "s22-stall-alarm",
           "sr-decision-shim.py", "t3code-sync-colors")


def rows():
    return [r for r in tomllib.loads((ROOT / "config/host/groot.toml").read_text())["user"]
            if r.get("live", "").startswith("~/.local/bin/") and r.get("source", "").startswith("scripts/")]


class LocalBinSourced(unittest.TestCase):
    def test_timer_tools_are_managed(self):
        managed = {r["live"].rsplit("/", 1)[1]: r["source"] for r in rows()}
        for name in SOURCED:
            self.assertEqual(managed.get(name), f"scripts/{name}", name)

    def test_sourced_tools_parse_and_name_no_literal_home(self):
        for name in SOURCED:
            path = ROOT / "scripts" / name
            text = path.read_text()
            self.assertIsNone(re.search(r"/home/[a-z]", text), name)
            if "python" in text.splitlines()[0]:
                compile(text, name, "exec")
            else:
                subprocess.run(["bash", "-n", str(path)], check=True)


if __name__ == "__main__":
    unittest.main()
