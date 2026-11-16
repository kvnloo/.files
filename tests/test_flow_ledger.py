import importlib.machinery
import importlib.util
import json
import pathlib
import shutil
import sqlite3
import tempfile
import time
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).parents[1]
loader = importlib.machinery.SourceFileLoader("flow_ledger", str(ROOT / "scripts/flow-ledger"))
fl = importlib.util.module_from_spec(importlib.util.spec_from_loader("flow_ledger", loader))
loader.exec_module(fl)

SCHEMA = """
create table sessions(id text primary key, source text);
create index idx_sessions_source_id on sessions(source, id);
create table messages(id integer primary key autoincrement, session_id text, role text, timestamp real, content text);
create index idx_messages_session_id on messages(session_id, id);
create index idx_messages_session on messages(session_id, timestamp);
insert into sessions values ('own', 'tui'), ('bot', 'cron');
"""


class OwnerMsgs(unittest.TestCase):
    def setUp(self):
        self.home = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.home)
        self.db = self.home / ".hermes/profiles/p/state.db"
        self.db.parent.mkdir(parents=True)
        con = sqlite3.connect(self.db)
        con.executescript(SCHEMA)
        con.close()
        self.cache = str(self.home / "cache.json")
        self.now = time.time()
        p = mock.patch.object(fl.os.path, "expanduser", lambda s: s.replace("~", str(self.home)))
        p.start()
        self.addCleanup(p.stop)

    def add(self, *rows):
        con = sqlite3.connect(self.db)
        con.executemany("insert into messages(session_id, role, timestamp, content) values (?,?,?,?)", rows)
        con.commit()
        con.close()

    def test_incremental_matches_full_read_and_reads_only_new_ids(self):
        n = self.now
        self.add(("own", "user", n - 3600, "first idea"), ("bot", "user", n - 3000, "agent relay"),
                 ("own", "user", n - 2000, "[tool noise"), ("own", "assistant", n - 1900, "reply"))
        since = n - 14 * 86400
        self.assertEqual(fl.owner_msgs(since, self.cache), [round(n - 3600)])
        self.add(("own", "user", n - 60, "second idea"))
        inc = fl.owner_msgs(since, self.cache)
        full = fl.owner_msgs(since, str(self.home / "fresh.json"))
        self.assertEqual(inc, full)
        self.assertEqual(inc, [round(n - 3600), round(n - 60)])
        ent = json.load(open(self.cache))[str(self.db)]
        self.assertEqual(ent["max_id"], 5)
        self.assertEqual(oct(pathlib.Path(self.cache).stat().st_mode & 0o777), "0o600")

    def test_ids_going_backwards_forces_a_full_reread(self):
        self.add(("own", "user", self.now - 100, "kept"))
        fl.owner_msgs(self.now - 86400, self.cache)
        c = json.load(open(self.cache))
        c[str(self.db)]["max_id"] = 999
        c[str(self.db)]["ts"] = [123]  # stale junk from a db that was since restored
        json.dump(c, open(self.cache, "w"))
        self.assertEqual(fl.owner_msgs(self.now - 86400, self.cache), [round(self.now - 100)])


if __name__ == "__main__":
    unittest.main()
