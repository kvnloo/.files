import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from datetime import datetime, timezone


SCRIPT = Path(__file__).resolve().parents[1] / "scripts/fable-intake"


class FableIntakeTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.work = self.base / "work"
        self.ops = self.base / "ops"
        self.work.mkdir()
        (self.ops / "bin").mkdir(parents=True)
        (self.ops / "bin/fable-ingest").write_text(
            "import json\nfrom pathlib import Path\n"
            "def update(path, fn, default=None):\n"
            "    path = Path(path)\n"
            "    data = json.loads(path.read_text()) if path.exists() else default\n"
            "    result = fn(data)\n"
            "    path.write_text(json.dumps(data))\n"
            "    path.with_suffix('.called').write_text('update')\n"
            "    return result\n"
        )
        self.queue = self.ops / "fable-queue.json"
        self.queue.write_text(json.dumps({"jobs": [], "keep": True}))
        self.now = int(time.time())
        self.open = {}
        self.events = []

    def announce(self, key, count, age=0):
        self.open[key] = self.now
        for i in range(count):
            self.events.append({"at": self.now - age - 60 * (i + 1),
                                "key": key, "owner": "reliability",
                                "line": "Investigate " + key + " with evidence " * 8})

    def run_intake(self, *args):
        (self.work / "actions-seen.json").write_text(json.dumps(self.open))
        (self.work / "actions.jsonl").write_text(
            "".join(json.dumps(row) + "\n" for row in self.events)
        )
        result = subprocess.run(
            [sys.executable, str(SCRIPT), *args], capture_output=True, text=True,
            env=dict(os.environ, NM_WORK=str(self.work), FIX_OPS=str(self.ops)),
            timeout=10,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def jobs(self):
        return json.loads(self.queue.read_text())["jobs"]

    def test_admit_at_three(self):
        key = "dead:os_service:example.service"
        self.announce(key, 3)
        self.run_intake()
        line = self.events[0]["line"]
        date = datetime.fromtimestamp(self.now - 180, timezone.utc).date().isoformat()
        self.assertEqual(self.jobs(), [{
            "id": "N" + hashlib.sha1(key.encode()).hexdigest()[:6],
            "title": line[:90], "class": "systemd dead unit",
            "owner": "reliability", "keywords": ["example.service"],
            "brief": line + f"\nannounced 3 times since {date}",
            "status": "pending", "src": "network " + key,
        }])
        self.assertTrue(self.queue.with_suffix(".called").exists())
        self.assertTrue(json.loads(self.queue.read_text())["keep"])

    def test_skip_at_two(self):
        self.announce("stale:lane:analyst", 2)
        self.run_intake()
        self.assertEqual(self.jobs(), [])

    def test_no_duplicate_on_second_run(self):
        self.announce("ask:ask:G01", 3)
        self.run_intake()
        original = self.jobs()
        self.run_intake()
        self.assertEqual(self.jobs(), original)
        self.assertEqual(original[0]["class"], "open ask without evidence")

    def test_cap_two_highest_counts_first(self):
        for name, count in [("low", 3), ("high", 5), ("middle", 4)]:
            self.announce("stale:lane:" + name, count)
        self.run_intake()
        self.assertEqual([j["keywords"] for j in self.jobs()], [["high"], ["middle"]])
        self.assertTrue(all(j["class"] == "stale lane" for j in self.jobs()))
        self.run_intake()
        self.assertEqual(len(self.jobs()), 2)

    def test_close_on_clear(self):
        key = "dead:os_service:example.service"
        self.announce(key, 3)
        self.run_intake()
        self.open.clear()
        self.events.append({"at": self.now, "key": key, "cleared": True})
        self.run_intake()
        self.assertEqual(len(self.jobs()), 1)
        self.assertEqual(self.jobs()[0]["status"], "done")
        self.assertEqual(self.jobs()[0]["note"], "cleared upstream")

    def test_hash_suffix_collapse(self):
        keys = ["dead:os_service:z0int-choice-" + digit * 64 + ".service"
                for digit in "abc"]
        for key in keys:
            self.announce(key, 1)
        self.open = {keys[-1]: self.now}
        self.run_intake()
        self.assertEqual(len(self.jobs()), 1)
        self.assertIn("announced 3 times", self.jobs()[0]["brief"])
        # Existing rows can retain a concrete hash from an older producer.
        queue = {"jobs": [dict(self.jobs()[0], src="network " + keys[0])]}
        self.queue.write_text(json.dumps(queue))
        self.run_intake()
        self.assertEqual(self.jobs(), queue["jobs"])

    def test_only_recent_announcements_count(self):
        key = "stale:lane:analyst"
        self.announce(key, 2)
        self.announce(key, 1, age=8 * 86400)
        self.events.append({"at": self.now, "key": key, "cleared": True})
        self.run_intake()
        self.assertEqual(self.jobs(), [])

    def test_running_duplicate_and_unrelated_rows(self):
        key = "stale:lane:analyst"
        self.announce(key, 3)
        rows = [{"status": "running", "src": "network " + key},
                {"status": "pending", "src": "fable F1"}]
        self.queue.write_text(json.dumps({"jobs": rows}))
        self.run_intake()
        self.assertEqual(self.jobs(), rows)
        self.open.clear()
        self.run_intake()
        self.assertEqual(self.jobs(), rows)

    def test_clear_frees_a_pending_slot(self):
        self.queue.write_text(json.dumps({"jobs": [
            {"status": "pending", "src": "network stale:lane:gone"}
        ]}))
        self.announce("stale:lane:first", 3)
        self.announce("stale:lane:second", 4)
        self.run_intake()
        self.assertEqual([j["status"] for j in self.jobs()], ["done", "pending", "pending"])

    def test_dry_prints_changes_without_writes(self):
        self.announce("stale:lane:analyst", 3)
        self.queue.write_text(json.dumps({"jobs": [
            {"status": "pending", "src": "network stale:lane:gone"}
        ]}))
        before = {p.relative_to(self.ops): p.read_bytes()
                  for p in self.ops.rglob("*") if p.is_file()}
        rows = self.run_intake("--dry")
        self.assertEqual([j["status"] for j in rows], ["done", "pending"])
        after = {p.relative_to(self.ops): p.read_bytes()
                 for p in self.ops.rglob("*") if p.is_file()}
        self.assertEqual(after, before)


if __name__ == "__main__":
    unittest.main()
