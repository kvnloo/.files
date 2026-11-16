import importlib.machinery
import importlib.util
import pathlib
import shutil
import sqlite3
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).parents[1]
loader = importlib.machinery.SourceFileLoader("limitless_sync", str(ROOT / "scripts/limitless-sync"))
spec = importlib.util.spec_from_loader("limitless_sync", loader)
ls = importlib.util.module_from_spec(spec)
loader.exec_module(ls)

FAKE_ADB = textwrap.dedent("""\
    #!{py}
    import os, sys
    phone = {phone!r}
    a = sys.argv[3:]  # drop -s SERIAL
    if a[0] == "exec-out" and a[3] == "cat":
        p = os.path.join(phone, a[4])
        if not os.path.exists(p):
            sys.exit(1)
        with open(p, "rb") as f:
            sys.stdout.buffer.write(f.read())
    elif a[0] == "shell" and "stat" in a:
        p = os.path.join(phone, a[-1])
        if not os.path.exists(p):
            sys.exit(1)
        st = os.stat(p)
        print(f"{{int(st.st_mtime)}}.{{st.st_size}}")
    else:
        print("123")  # pidof: app alive
""")


class SyncNoop(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp())
        self.phone = self.tmp / "phone"
        (self.phone / "databases").mkdir(parents=True)
        adb = self.tmp / "adb"
        adb.write_text(FAKE_ADB.format(py=sys.executable, phone=str(self.phone)))
        adb.chmod(0o755)
        self.cfg = {"adb": str(adb), "serial": "x", "noopPackage": "pkg"}
        self.st = self.tmp / "state"
        self.st.mkdir()

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def phone_db_with_wal_rows(self, n):
        """A live app's db: rows still only in the WAL when the copy happens."""
        src = self.tmp / "live.db"
        con = sqlite3.connect(src)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute("PRAGMA wal_autocheckpoint=0")
        con.execute("create table hrSample(ts int, bpm int)")
        con.executemany("insert into hrSample values (?,?)", [(i, 60) for i in range(n)])
        con.commit()
        for suf in ("", "-wal"):
            shutil.copy(f"{src}{suf}", self.phone / "databases" / f"noop_whoop.db{suf}")
        con.close()

    def test_wal_rows_fold_into_a_read_only_openable_copy(self):
        self.phone_db_with_wal_rows(500)
        self.assertEqual(ls.sync_noop(self.cfg, self.st), "copied")
        out = self.st / "noop" / "noop_whoop.db"
        con = sqlite3.connect(f"file:{out}?mode=ro", uri=True)
        self.assertEqual(con.execute("select count(*) from hrSample").fetchone()[0], 500)
        self.assertEqual(con.execute("PRAGMA journal_mode").fetchone()[0], "delete")
        con.close()
        self.assertEqual(sorted(p.name for p in (self.st / "noop").iterdir()), ["noop_whoop.db", "stamp"])
        self.assertEqual(oct(out.stat().st_mode & 0o777), "0o600")

    def test_pull_streams_instead_of_buffering_the_db_in_ram(self):
        """MemoryMax=256M and a 184 MB db: buffering it swapped ~220 MB every run."""
        src = self.phone / "databases" / "noop_whoop.db"
        con = sqlite3.connect(src)
        con.execute("create table blob(b)")
        con.executemany("insert into blob values (randomblob(1000000))", [()] * 120)
        con.commit()
        con.close()
        probe = textwrap.dedent(f"""\
            import importlib.machinery, importlib.util, json, pathlib, resource
            ld = importlib.machinery.SourceFileLoader("m", {str(ROOT / "scripts/limitless-sync")!r})
            m = importlib.util.module_from_spec(importlib.util.spec_from_loader("m", ld)); ld.exec_module(m)
            base = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
            r = m.sync_noop({self.cfg!r}, pathlib.Path({str(self.st)!r}))
            print(json.dumps([r, resource.getrusage(resource.RUSAGE_SELF).ru_maxrss - base]))
        """)
        import json
        import subprocess
        r, grew_kb = json.loads(subprocess.run([sys.executable, "-I", "-c", probe], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(r, "copied")
        self.assertLess(grew_kb, 40 * 1024, "the 120 MB db was held in RAM")

    def test_failed_or_corrupt_pull_keeps_last_good_copy(self):
        self.phone_db_with_wal_rows(10)
        self.assertEqual(ls.sync_noop(self.cfg, self.st), "copied")
        good = (self.st / "noop" / "noop_whoop.db").read_bytes()
        db = self.phone / "databases" / "noop_whoop.db"
        db.write_bytes(b"SQLite format 3\x00" + b"\xff" * 8192)  # torn header page
        (self.phone / "databases" / "noop_whoop.db-wal").unlink()
        self.assertEqual(ls.sync_noop(self.cfg, self.st), "unreachable")
        self.assertEqual((self.st / "noop" / "noop_whoop.db").read_bytes(), good)
        self.assertFalse((self.st / "noop" / "incoming").exists())


class LastThread(unittest.TestCase):
    def test_owner_turn_wins_over_agent_turns_and_uses_indexes(self):
        home = pathlib.Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, home)
        db = home / ".hermes/profiles/p/state.db"
        db.parent.mkdir(parents=True)
        con = sqlite3.connect(db)
        con.executescript("""
            create table sessions(id text primary key, source text, title text, display_name text, cwd text);
            create index idx_sessions_source_id on sessions(source, id);
            create table messages(id integer primary key, session_id text, role text, timestamp real, content text);
            create index idx_messages_session on messages(session_id, timestamp);
            insert into sessions values ('own', 'tui', 'garden', null, null), ('bot', 'cron', 'cron job', null, null);
            insert into messages(session_id, role, timestamp, content) values
              ('own', 'user', 1000, 'old idea'), ('own', 'user', 5000, 'ship the planter'),
              ('bot', 'user', 6000, 'agent relay'), ('own', 'user', 9000, 'after the nap');""")
        con.commit()
        plan = " ".join(r[3] for r in con.execute(
            "explain query plan select m.timestamp from messages m join sessions s on s.id=m.session_id "
            "where m.role='user' and m.timestamp<? and m.timestamp>? and s.source in ('tui') order by m.timestamp desc limit 1", (1, 0)))
        con.close()
        self.assertNotIn("SCAN m", plan)
        old = ls.Path.home
        ls.Path.home = staticmethod(lambda: home)
        try:
            self.assertEqual(ls.last_thread(8000), ("garden", "ship the planter"))
            self.assertIsNone(ls.last_thread(5000 + 4 * 86400))
        finally:
            ls.Path.home = old


if __name__ == "__main__":
    unittest.main()
