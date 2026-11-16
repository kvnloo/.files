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


class Body(unittest.TestCase):
    def test_body_covers_every_device_and_seeks_the_primary_key(self):
        st = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, st)
        (st / "noop").mkdir()
        con = sqlite3.connect(st / "noop/noop_whoop.db")
        con.executescript("""
            CREATE TABLE hrSample(deviceId TEXT NOT NULL, ts INTEGER NOT NULL, bpm INTEGER NOT NULL, synced INTEGER NOT NULL,
                                  PRIMARY KEY(deviceId, ts));
            CREATE TABLE rrInterval(deviceId TEXT NOT NULL, ts INTEGER NOT NULL, rrMs INTEGER NOT NULL, seq INTEGER NOT NULL,
                                    synced INTEGER NOT NULL, ord INTEGER, srcChannel INTEGER, tsSuspect INTEGER,
                                    PRIMARY KEY(deviceId, ts, rrMs, seq));""")
        con.executemany("insert into hrSample values (?,?,?,0)",
                        [("oura", t, 60) for t in range(100, 110)] + [("whoop", t, 80) for t in range(100, 110)]
                        + [("whoop", 500, 200)])
        con.executemany("insert into rrInterval values ('whoop',?,?,?,0,?,0,0)",
                        [(100 + i // 10, 800 + (i % 2) * 20, i, i) for i in range(120)])
        con.commit()
        plan = " ".join(r[3] for r in con.execute(
            "explain query plan select bpm from hrSample where deviceId in ('a','b') and ts between 1 and 2"))
        con.close()
        self.assertNotIn("SCAN", plan)
        with mock.patch.object(fl, "ST", str(st)):
            self.assertEqual(fl.devices(sqlite3.connect(st / "noop/noop_whoop.db"), "hrSample"), ["oura", "whoop"])
            self.assertEqual(fl.body(100, 120), {"hrMean": 70, "rmssdMs": 20.0})
            self.assertEqual(fl.body(1000, 2000), {})


if __name__ == "__main__":
    unittest.main()
