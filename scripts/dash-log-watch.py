#!/usr/bin/env python3
"""Report-only, foreground-gated Dash log sidecar. No model idle polling."""
import argparse
import asyncio
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import sqlite3
import sys
import time

PACKAGE = "app.dash.mobile"
MODEL = "gpt-6-luna"
UNITS = {
    "dash-bridge-4747.service": "bridge",
    "dash-metro-native-8108.service": "metro-native",
    "dash-metro-preview-8098.service": "metro-preview",
    "dash-metro-8097.service": "metro-stable",
}
# Only finite classifications cross the model boundary. No free-text redaction gamble.
SIGNATURES = {
    "js_type_error": r"\bTypeError\s*:",
    "js_reference_error": r"\bReferenceError\s*:",
    "js_syntax_error": r"\bSyntaxError\s*:",
    "module_resolution": r"(?:Unable to resolve module|Cannot find module)",
    "connection_refused": r"\bECONNREFUSED\b",
    "connection_reset": r"\bECONNRESET\b",
    "timeout": r"(?:\bETIMEDOUT\b|\bTimeoutError\s*:)",
    "out_of_memory": r"(?:JavaScript heap out of memory|\bOutOfMemoryError\b)",
    "uncaught_exception": r"(?:\buncaughtException\b|\bUnhandledPromiseRejection\b)",
    "native_fatal": r"\bFATAL EXCEPTION\s*:",
    "bridge_failure": r"(?:\[bridge\].{0,40}\b(?:error|failed)\b|\[ws\].{0,40}\b(?:error|failed)\b)",
}
CRITICAL = {"out_of_memory", "native_fatal", "uncaught_exception"}
EVENT_TAGS = ("wm_set_resumed_activity", "wm_on_top_resumed_gained_called",
              "wm_on_top_resumed_lost_called", "wm_on_paused_called", "wm_on_stop_called")


def atomic(path, value):
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    tmp = path.with_suffix(".new")
    with open(tmp, "w") as stream:
        json.dump(value, stream, sort_keys=True)
        stream.flush()
        os.fsync(stream.fileno())
    os.chmod(tmp, 0o600)
    os.replace(tmp, path)


def validate(config):
    if config.get("package") != PACKAGE or config.get("model") != MODEL or config.get("provider") != "openai-codex":
        raise ValueError("explicit exact native identity/provider/model required")
    if config.get("hardware_serial") != "R5CY93G2WNH" or config.get("phone_host") != "100.117.226.39":
        raise ValueError("unapproved phone")
    if config.get("units") != UNITS:
        raise ValueError("explicit actual units required")
    for key, maximum in (("concurrency", 3), ("calls_per_hour", 12), ("reserved_tokens_per_hour", 60000)):
        if type(config.get(key)) is not int or not 1 <= config[key] <= maximum:
            raise ValueError("invalid budget")
    if not 1 <= config.get("debounce_seconds", 0) <= 5:
        raise ValueError("invalid debounce")
    helper = Path(config["helper"])
    if hashlib.sha256(helper.read_bytes()).hexdigest() != config["helper_sha256"]:
        raise ValueError("OAuth helper changed")
    qualification = json.loads(Path(config["qualification"]).read_text())
    if not (qualification.get("ok") and qualification.get("provider") == "openai-codex"
            and qualification.get("requested_model") == MODEL and qualification.get("returned_model") == MODEL
            and qualification.get("catalog", {}).get("slug") == MODEL and qualification["catalog"].get("fresh")):
        raise ValueError("fresh-catalog plus real exact-model qualification required")



def classify(message):
    if not isinstance(message, str) or len(message) > 65536:
        return []
    return sorted(code for code, pattern in SIGNATURES.items() if re.search(pattern, message))


def foreground_snapshot(text):
    # Only primary top-resumed activity is evidence; never websocket/Expo presence.
    matches = re.findall(r"topResumedActivity=.*?\bu0\s+([\w.]+)/", text)
    if not matches:
        return "UNKNOWN"
    return "ACTIVE" if matches[-1] == PACKAGE else "BACKGROUND"


def foreground_event(line, previous):
    if len(line) > 4096:
        return "UNKNOWN"
    match = re.search(r"\b(" + "|".join(EVENT_TAGS) + r")\s*:\s*\[([^]]+)\]", line)
    if not match:
        return previous
    tag, fields = match.groups()
    parts = fields.split(",")
    if len(parts) < 2:
        return "UNKNOWN"
    component = parts[1].strip()
    ours = component.startswith(PACKAGE + "/") or component == PACKAGE + ".MainActivity"
    if tag == "wm_on_top_resumed_gained_called":
        return "ACTIVE" if ours else "BACKGROUND"
    if tag == "wm_set_resumed_activity" and not ours:
        return "BACKGROUND"
    if ours and tag in ("wm_on_top_resumed_lost_called", "wm_on_paused_called", "wm_on_stop_called"):
        return "BACKGROUND"
    return previous


async def capture(argv, timeout=15):
    proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                               stderr=asyncio.subprocess.DEVNULL, limit=131072,
                                               start_new_session=True)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout)
        return proc.returncode, out.decode(errors="replace")
    finally:
        if proc.returncode is None:
            os.killpg(proc.pid, signal.SIGKILL)
            await proc.wait()


async def terminate(proc):
    if proc and proc.returncode is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()


class Watch:
    def __init__(self, config, state, fixture=False):
        self.config, self.state, self.fixture = config, Path(state), fixture
        self.state.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.state, 0o700)
        self.db = sqlite3.connect(self.state / "state.sqlite")
        self.db.executescript("""CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
            CREATE TABLE IF NOT EXISTS seen(fingerprint TEXT PRIMARY KEY, ts REAL);
            CREATE TABLE IF NOT EXISTS admissions(ts REAL, reserved INTEGER);
        """)
        os.chmod(self.state / "state.sqlite", 0o600)
        self.gate = "UNKNOWN"
        self.transport_online = None
        self.generation = 0
        self.pending = []
        self.flush_task = None
        self.running = set()
        self.active_seats = set()
        self.counts = {k: 0 for k in ("lines", "healthy", "background_dropped", "deduplicated", "backpressure",
                                     "budget_dropped", "model_calls", "model_failures", "incidents", "cursor_gaps")}
        self.streams = {"journal": "starting", "activity": "starting", "transport": "starting"}
        self.started = time.time()
        self.status_pending = None
        self.cursor_pending = None
        self.review_available = self.meta("review_health") != "unavailable"
        self.status()

    def meta(self, key):
        row = self.db.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
        return row[0] if row else None

    def checkpoint(self, key, value):
        self.db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (key, value))
        self.db.commit()

    def status(self):
        if self.cursor_pending is not None:
            self.checkpoint("journal_cursor", self.cursor_pending)
            self.cursor_pending = None
        now = time.time()
        row = self.db.execute("SELECT count(*),coalesce(sum(reserved),0) FROM admissions WHERE ts>?", (now - 3600,)).fetchone()
        atomic(self.state / "status.json", {"schema": 1, "pid": os.getpid(), "updated_at": now,
               "started_at": self.started, "foreground": self.gate, "package": PACKAGE,
               "hardware_serial": self.config["hardware_serial"], "provider": "openai-codex", "model": MODEL,
               "report_only": True, "fixture": self.fixture, "streams": self.streams,
               "review_available": self.review_available, "review_health_semantics": "last_verified_not_idle_probed",
               "review_qualification": self.config["qualification"],
               "counts": self.counts, "running": len(self.running), "pending": len(self.pending),
               "admissions_last_hour": row[0], "reserved_tokens_last_hour": row[1],
               "cursor": self.meta("journal_cursor"), "notification_delivery": "local_reports_only",
               "limits": {k: self.config[k] for k in ("concurrency", "calls_per_hour", "reserved_tokens_per_hour")}})

    def schedule_status(self):
        if self.status_pending is None or self.status_pending.cancelled():
            def update():
                self.status_pending = None
                self.status()
            self.status_pending = asyncio.get_running_loop().call_later(1, update)

    def set_gate(self, gate):
        if gate == "ACTIVE" and self.transport_online is False:
            gate = "UNKNOWN"
        if gate != self.gate:
            self.generation += 1
            self.gate = gate
            if gate != "ACTIVE":
                self.pending.clear()
            self.status()

    def event(self, record, source=None):
        self.counts["lines"] += 1
        if source is None:
            source = UNITS.get(record.get("_SYSTEMD_USER_UNIT"))
        cursor = record.get("__CURSOR", "")
        if cursor:
            self.cursor_pending = cursor
            self.schedule_status()
        if source not in set(UNITS.values()):
            return
        codes = classify(record.get("MESSAGE"))
        if not codes:
            self.counts["healthy"] += 1
            self.schedule_status()
            return
        if self.gate != "ACTIVE":
            self.counts["background_dropped"] += 1
            self.status()
            return
        fingerprint = hashlib.sha256(json.dumps([source, codes]).encode()).hexdigest()
        now = time.time()
        previous = self.db.execute("SELECT ts FROM seen WHERE fingerprint=?", (fingerprint,)).fetchone()
        if previous and previous[0] > now - 3600:
            self.counts["deduplicated"] += 1
            return
        if len(self.pending) >= 24:
            self.counts["backpressure"] += 1
            return
        self.db.execute("INSERT OR REPLACE INTO seen VALUES (?,?)", (fingerprint, now))
        self.db.commit()
        self.pending.append({"source": source, "codes": codes, "fingerprint": fingerprint,
                             "evidence_sha256": hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest(),
                             "cursor": cursor[:1024], "observed_at": now})
        if self.flush_task is None or self.flush_task.done():
            self.flush_task = asyncio.create_task(self.flush_later(self.generation))
        self.status()

    async def flush_later(self, generation):
        await asyncio.sleep(self.config["debounce_seconds"])
        if self.gate != "ACTIVE" or generation != self.generation:
            # A new foreground session owns its own burst, never stale pending work.
            if self.pending and self.gate == "ACTIVE":
                self.flush_task = asyncio.create_task(self.flush_later(self.generation))
            return
        batch, self.pending = self.pending, []
        if not batch:
            return
        roles = {"bridge" if e["source"] == "bridge" else "runtime" for e in batch}
        if len(roles) > 1 or any(CRITICAL.intersection(e["codes"]) for e in batch):
            seat = "correlation"
        else:
            seat = roles.pop()
        now = time.time()
        row = self.db.execute("SELECT count(*),coalesce(sum(reserved),0) FROM admissions WHERE ts>?", (now - 3600,)).fetchone()
        if now < float(self.meta("review_retry_after") or 0):
            self.local_report({"seat": seat, "evidence": batch, "result": {"ok": False, "code": "review_unavailable_cooldown"}})
            self.status()
            return
        if len(self.running) >= self.config["concurrency"] or seat in self.active_seats:
            self.counts["backpressure"] += len(batch)
            self.local_report({"seat": seat, "evidence": batch, "result": {"ok": False, "code": "concurrency_backpressure"}})
            self.status()
            return
        if row[0] >= self.config["calls_per_hour"] or row[1] + 5000 > self.config["reserved_tokens_per_hour"]:
            self.counts["budget_dropped"] += len(batch)
            self.local_report({"seat": seat, "evidence": batch, "result": {"ok": False, "code": "budget_exhausted"}})
            self.status()
            return
        # Charge before spawning; refusals/timeouts cannot bypass budget across restarts.
        self.db.execute("INSERT INTO admissions VALUES (?,5000)", (now,))
        self.db.execute("DELETE FROM admissions WHERE ts<?", (now - 86400,))
        self.db.execute("DELETE FROM seen WHERE ts<?", (now - 86400,))
        self.db.commit()
        self.counts["model_calls"] += 1
        self.active_seats.add(seat)
        task = asyncio.create_task(self.review(seat, batch))
        self.running.add(task)
        def finished(done):
            self.running.discard(done)
            self.active_seats.discard(seat)
            self.status()
        task.add_done_callback(finished)
        self.status()

    def local_report(self, incident):
        now = time.time()
        ident = hashlib.sha256(json.dumps(incident, sort_keys=True).encode()).hexdigest()
        target = self.state / "incidents" / (str(time.time_ns()) + "-" + ident[:12] + ".json")
        atomic(target, {"schema": 1, "id": ident, "created_at": now, "fixture": self.fixture,
                        "report_only": True, "delivery": "protected_local_only", **incident})
        reports = sorted(target.parent.glob("*.json"))
        for old in reports[:-200]:
            old.unlink()
        for old in reports[-200:]:
            if old.stat().st_mtime < now - 7 * 86400:
                old.unlink()
        self.counts["incidents"] += 1

    async def review(self, seat, batch):
        model_events = [{k: e[k] for k in ("source", "codes", "evidence_sha256", "observed_at") if k in e}
                        for e in batch[:8]]
        req = {"helper": self.config["helper"], "helper_sha256": self.config["helper_sha256"],
               "facts": {"fixture": self.fixture, "seat": seat, "events": model_events,
                         "omitted_event_count": max(0, len(batch) - 8)}}
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                sys.executable, str(Path(__file__).resolve().with_name("dash-log-watch-model.py")),
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, limit=32768, start_new_session=True,
                env={**os.environ, "HERMES_HOME": self.config["hermes_home"]})
            out, _ = await asyncio.wait_for(proc.communicate(json.dumps(req).encode()), 45)
            result = json.loads(out) if len(out) <= 8192 else {"ok": False, "code": "output_limit"}
            if result.get("ok") and (result.get("provider") != "openai-codex" or result.get("returned_model") != MODEL):
                result = {"ok": False, "code": "model_mismatch"}
        except (TimeoutError, ValueError, OSError):
            result = {"ok": False, "code": "timeout_or_transport_failure"}
        finally:
            await terminate(proc)
        if not result.get("ok"):
            self.counts["model_failures"] += 1
            self.review_available = False
            self.checkpoint("review_health", "unavailable")
            self.checkpoint("review_retry_after", str(time.time() + 300))
        else:
            self.review_available = True
            self.checkpoint("review_health", "available")
            self.checkpoint("review_retry_after", "0")
        self.local_report({"seat": seat, "evidence": batch, "result": result})
        self.status()

    async def journal(self):
        backoff = 1
        while True:
            cursor = self.meta("journal_cursor")
            argv = ["journalctl", "--user", "--no-pager", "-f", "-o", "json",
                    "--output-fields=MESSAGE,_SYSTEMD_USER_UNIT,__CURSOR,__REALTIME_TIMESTAMP"]
            for unit in UNITS:
                argv += ["-u", unit]
            # Never flood stale logs after downtime; at most two minutes of cursor recovery.
            argv += ["--after-cursor", cursor, "--since=-2min", "--no-tail"] if cursor else ["-n", "0"]
            proc = await asyncio.create_subprocess_exec(*argv, stdout=asyncio.subprocess.PIPE,
                                                       stderr=asyncio.subprocess.DEVNULL,
                                                       start_new_session=True, limit=131072)
            self.streams["journal"] = "following"
            self.status()
            started = time.monotonic()
            assert proc.stdout is not None
            try:
                while line := await proc.stdout.readline():
                    try:
                        if len(line) <= 131072:
                            self.event(json.loads(line))
                            if self.counts["lines"] % 64 == 0:
                                await asyncio.sleep(0)  # foreground events cannot starve behind a log burst
                    except (ValueError, TypeError):
                        self.counts["backpressure"] += 1
            except (ValueError, OSError):
                self.counts["backpressure"] += 1
            finally:
                await terminate(proc)
            self.streams["journal"] = "reconnecting"
            if time.monotonic() - started < 2 and cursor:
                self.checkpoint("journal_cursor", "")
                self.counts["cursor_gaps"] += 1
            self.status()
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2) if time.monotonic() - started < 60 else 1

    def endpoint(self):
        data = json.loads(Path(self.config["phone_state"]).read_text())
        if data.get("host") != self.config["phone_host"] or data.get("serial") != self.config["hardware_serial"]:
            raise ValueError("phone identity mismatch")
        port = data.get("port")
        if type(port) is not int or not 1 <= port <= 65535:
            raise ValueError("invalid phone port")
        return data["host"] + ":" + str(port)

    async def activity(self):
        backoff = 1
        while True:
            self.set_gate("UNKNOWN")
            proc = None
            started = time.monotonic()
            try:
                endpoint = self.endpoint()
                rc, serial = await capture(["adb", "-s", endpoint, "shell", "getprop", "ro.serialno"])
                if rc or serial.strip() != self.config["hardware_serial"]:
                    if not rc and serial.strip():
                        # Wrong hardware is a hard stop, never reconnect fallback.
                        self.streams["activity"] = "hardware_mismatch"
                        self.status()
                        await asyncio.Future()
                    raise OSError("offline")
                # Subscribe BEFORE snapshot, then discard events older than the snapshot watermark.
                proc = await asyncio.create_subprocess_exec(
                    "adb", "-s", endpoint, "logcat", "-b", "events", "-v", "epoch", "-T", "1",
                    *[tag + ":I" for tag in EVENT_TAGS], "*:S", stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.DEVNULL, start_new_session=True, limit=8192)
                rc, snapshot = await capture(["adb", "-s", endpoint, "shell",
                    "date +%s.%N; dumpsys activity activities"])
                if rc or proc.returncode is not None:
                    raise OSError("snapshot unavailable")
                watermark = float(snapshot.splitlines()[0])
                self.streams["activity"] = "following"
                self.set_gate(foreground_snapshot(snapshot))
                self.status()
                assert proc.stdout is not None
                while line := await proc.stdout.readline():
                    text = line.decode(errors="replace")
                    timestamp = re.match(r"^\s*(\d+\.\d+)\s", text)
                    if timestamp and float(timestamp[1]) >= watermark:
                        self.set_gate(foreground_event(text, self.gate))
            except (ValueError, OSError, TimeoutError, KeyError):
                pass
            finally:
                self.set_gate("UNKNOWN")
                await terminate(proc)
            self.streams["activity"] = "reconnecting"
            self.status()
            # Existing pinned identity/reconnect helper only; no scan or other-device fallback.
            try:
                await capture([self.config["phone_reconnect"], "reconnect"], timeout=35)
            except (OSError, TimeoutError):
                pass
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2) if time.monotonic() - started < 60 else 1

    async def transport(self):
        # ADB server device change events are supplementary fail-closed loss signals.
        backoff = 1
        while True:
            proc = await asyncio.create_subprocess_exec("adb", "track-devices", stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.DEVNULL, start_new_session=True, limit=32768)
            self.streams["transport"] = "following"
            self.status()
            try:
                # adb track-devices emits four ASCII hex length bytes followed by a full list.
                assert proc.stdout is not None
                while True:
                    length = int(await proc.stdout.readexactly(4), 16)
                    if length > 32768:
                        raise ValueError("oversize device list")
                    block = (await proc.stdout.readexactly(length)).decode(errors="replace").splitlines()
                    endpoint = self.endpoint()
                    self.transport_online = endpoint + "\tdevice" in block
                    if not self.transport_online:
                        self.set_gate("UNKNOWN")
            except (OSError, ValueError, KeyError, asyncio.IncompleteReadError):
                pass
            finally:
                self.set_gate("UNKNOWN")
                await terminate(proc)
            self.streams["transport"] = "reconnecting"
            self.transport_online = False
            self.status()
            await asyncio.sleep(backoff)
            backoff = min(60, backoff * 2)

    async def serve(self):
        try:
            await asyncio.gather(self.journal(), self.activity(), self.transport())
        finally:
            for task in self.running:
                task.cancel()
            await asyncio.gather(*self.running, return_exceptions=True)
            self.set_gate("UNKNOWN")
            self.streams = {k: "stopped" for k in self.streams}
            self.status()


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("run", "status", "check", "qualify", "replay"))
    parser.add_argument("--config", default=str(Path.home() / ".config/dash-log-watch/config.json"))
    parser.add_argument("--state", default=str(Path.home() / ".local/state/dash-log-watch"))
    parser.add_argument("--journal-file", help="owned synthetic journal JSON only, replay command")
    args = parser.parse_args()
    if args.command == "replay":
        live = Path.home() / ".local/state/dash-log-watch"
        if not args.journal_file or Path(args.state).resolve() == live.resolve():
            raise SystemExit("Replay requires an explicit isolated --state and owned --journal-file")
        if Path(args.journal_file).stat().st_size > 1024 * 1024:
            raise SystemExit("Owned fixture input exceeds 1MiB")
    if args.command == "status":
        print((Path(args.state) / "status.json").read_text())
        return
    config = json.loads(Path(args.config).read_text())
    if args.command == "qualify":
        req = {"helper": config["helper"], "helper_sha256": config["helper_sha256"], "qualify": True,
               "facts": {"fixture": True, "seat": "runtime", "codes": ["js_type_error"], "count": 1}}
        import subprocess
        proc = subprocess.run([sys.executable, str(Path(__file__).resolve().with_name("dash-log-watch-model.py"))],
            input=json.dumps(req), text=True, capture_output=True, timeout=50,
            env={**os.environ, "HERMES_HOME": config["hermes_home"]})
        result = json.loads(proc.stdout)
        if not result.get("ok"):
            raise SystemExit("Exact-model qualification failed; no fallback")
        atomic(Path(config["qualification"]), result)
        print(json.dumps(result))
        return
    validate(config)
    if args.command == "check":
        print("DASH_LOG_WATCH_CONFIG_OK")
        return
    state = Path(args.state)
    state.mkdir(mode=0o700, parents=True, exist_ok=True)
    with open(state / "watch.lock", "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        watch = Watch(config, state, fixture=args.command == "replay")
        async def go():
            loop = asyncio.get_running_loop()
            task = asyncio.current_task()
            assert task is not None
            for sig in (signal.SIGTERM, signal.SIGINT):
                loop.add_signal_handler(sig, task.cancel)
            if args.command == "replay":
                watch.set_gate("ACTIVE")  # explicit isolated fixture ONLY, never production config.
                for line in Path(args.journal_file).read_text().splitlines():
                    record = json.loads(line)
                    message = record.get("MESSAGE", "")
                    if not record.get("_SYSTEMD_USER_UNIT", "").startswith("dash-log-watch-fixture-") or not message.startswith("FIXTURE_"):
                        raise ValueError("Replay accepts owned synthetic journal fixtures only")
                    source = "bridge" if message.startswith("FIXTURE_BRIDGE ") else "metro-native"
                    watch.event(record, source=source)
                if watch.flush_task:
                    await watch.flush_task
                await asyncio.gather(*watch.running)
                watch.running.clear()
                watch.status()
            else:
                await watch.serve()
        try:
            asyncio.run(go())
        except asyncio.CancelledError:
            pass


if __name__ == "__main__":
    main()
