"""Android speed-ups for phone-harness, loaded by agent_helpers.py.

  * fast tree  - Android._tree reads the accessibility tree from a persistent
                 uiautomator2 jar server (~20-50 ms) instead of a fresh
                 `uiautomator dump` (~2 s, or ~10 s and then a failure on
                 screens that never go idle). Same node shape, so screen(),
                 ui(), find_text(), tap_ui() and friends are unchanged.
                 Any error -> server stopped, stock dump used.
  * fast gate  - the awake/locked check is one adb round trip, not two.
  * wait_stable - hashes the screen on the phone (`screencap | md5sum`,
                 ~0.16 s) instead of pulling a ~2 MB PNG per poll.
  * wait_for_text - stock logic, 0.25 s poll.

Nothing is installed as an APK and no root is needed: the jar runs through
`app_process` as the shell user, like `uiautomator dump` itself.

Switches (per command, never global): PH_FAST_TREE=0, PH_FAST_WAIT=0,
PH_FAST_TREE_IDLE=<seconds, default 300>, PH_FAST_TREE_PORT=<device port>.
Helpers: fast_tree_status(), fast_tree_stop(), fast_tree_uninstall().
"""
import hashlib as _hashlib
import json as _json
import os as _os
import re as _re
import subprocess as _subprocess
import sys as _sys
import time as _time
import urllib.request as _urlreq
import xml.etree.ElementTree as _ET
from pathlib import Path as _Path

_WS = _Path(__file__).resolve().parent
_LOCAL_JAR = _WS / "vendor" / "u2.jar"            # uiautomator2 3.7.0 assets/u2.jar (MIT)
_LOCAL_RUN = _WS / "vendor" / "ph-u2-run.sh"
_FAIL_MARK = _WS / ".fast_tree_failed"            # skip the fast path for a while after a failure
_DEV_DIR = "/data/local/tmp/ph-u2"
_DEV_PORT = int(_os.environ.get("PH_FAST_TREE_PORT", "9118"))
# Short on purpose: while the server is up, a plain `uiautomator dump` from any
# other client (a workspace without this file, Maestro, ...) is killed.
_IDLE = int(_os.environ.get("PH_FAST_TREE_IDLE", "300"))
_FAIL_COOLDOWN = 600
_SETTLE_WINDOW = 1.5      # a read this soon after an input action waits for the tree to settle
_SETTLE_MAX = 1.5
_SETTLE_GAP = 0.12

_U2 = {"port": None, "ready": False, "disabled": None, "touch_at": 0.0,
       "last_action": 0.0, "fallbacks": 0, "fast_reads": 0}
_ORIG = {}


def _log(msg):
    print(f"[fast-tree] {msg}", file=_sys.stderr)


def _md5_file(p):
    return _hashlib.md5(_Path(p).read_bytes()).hexdigest()


def _fast_tree_wanted():
    if _os.environ.get("PH_FAST_TREE", "1") == "0" or _U2["disabled"]:
        return False
    if not _LOCAL_JAR.exists() or not _LOCAL_RUN.exists():
        return False
    try:
        if _FAIL_MARK.exists() and _time.time() - _FAIL_MARK.stat().st_mtime < _FAIL_COOLDOWN:
            return False
    except OSError:
        pass
    try:                                   # never push a jar onto a rented cloud phone
        from phone_harness import cloud as _cloud
        if _cloud.attached("adb"):
            return False
    except Exception:
        pass
    return True


def _serial():
    return _os.environ.get("ANDROID_SERIAL", "")


def _adb_run(*args, check=True, timeout=20):
    from phone_harness import android as _A
    return _A._run(*args, check=check, timeout=timeout)


def _u2_local_port():
    serial = _serial()
    for line in _adb_run("forward", "--list", check=False).splitlines():
        p = line.split()
        if len(p) == 3 and p[0] == serial and p[2] == f"tcp:{_DEV_PORT}" and p[1].startswith("tcp:"):
            return int(p[1][4:])
    return int(_adb_run("-s", serial, "forward", "tcp:0", f"tcp:{_DEV_PORT}").strip())


_VIA_ADB = "adb"   # sentinel port: talk to the server with on-phone curl over `adb exec-out`


def _u2_adb_http(path, body=None, timeout=10.0):
    """Same request, made by curl on the phone. Needed when the adb server is not on
    this host (ADB_SERVER_SOCKET through an SSH tunnel): `adb forward` then binds the
    port on the server's host, so the local 127.0.0.1:<port> answers nothing.
    One adb round trip (~0.15-0.2 s over a tunnel) instead of a ~2.5 s stock dump."""
    import shlex as _shlex
    data = "" if body is None else " -d " + _shlex.quote(_json.dumps(body, separators=(",", ":")))
    cmd = f"curl -s -m {max(1, int(timeout))}{data} http://127.0.0.1:{_DEV_PORT}{path}"
    out = _adb_run("-s", _serial(), "exec-out", cmd, check=False, timeout=timeout + 5)
    return out.encode("utf-8") if isinstance(out, str) else out


def _u2_http(port, path, body=None, timeout=10.0):
    if port == _VIA_ADB:
        return _u2_adb_http(path, body, timeout)
    data = None if body is None else _json.dumps(body).encode()
    req = _urlreq.Request(f"http://127.0.0.1:{port}{path}", data=data,
                          headers={"Content-Type": "application/json", "Accept-Encoding": ""})
    with _urlreq.urlopen(req, timeout=timeout) as r:
        return r.read()


def _u2_rpc(port, method, params=None, timeout=10.0):
    raw = _u2_http(port, "/jsonrpc/0", {"jsonrpc": "2.0", "id": 1, "method": method,
                                        "params": [] if params is None else params}, timeout)
    d = _json.loads(raw)
    if "error" in d:
        raise RuntimeError(f"u2 {method}: {str(d['error'].get('message'))[:200]}")
    return d.get("result")


def _u2_ping(port, timeout=2.0):
    try:
        return _u2_http(port, "/ping", timeout=timeout) == b"pong"
    except Exception:
        return False


# Kill only our own pids, and only if /proc confirms they are still ours.
_KILL_OURS = (f"cd {_DEV_DIR} 2>/dev/null && for p in $(cat supervisor.pid server.pid 2>/dev/null); do "
              f"tr '\\0' ' ' < /proc/$p/cmdline 2>/dev/null | grep -q -e com.wetest.uia2 -e ph-u2 "
              f"&& kill $p; done; rm -f supervisor.pid server.pid; true")


def _u2_start(phone):
    """Push jar + supervisor when missing or stale, then launch detached."""
    out = phone._sh(f"mkdir -p {_DEV_DIR}; md5sum {_DEV_DIR}/u2.jar {_DEV_DIR}/run.sh 2>/dev/null; true")
    if _md5_file(_LOCAL_JAR) not in out:
        phone._adb("push", str(_LOCAL_JAR), f"{_DEV_DIR}/u2.jar", timeout=120)
    if _md5_file(_LOCAL_RUN) not in out:
        phone._adb("push", str(_LOCAL_RUN), f"{_DEV_DIR}/run.sh", timeout=60)
    phone._sh(_KILL_OURS)                                  # a stale server that stopped answering
    phone._sh(f"setsid nohup sh {_DEV_DIR}/run.sh {_IDLE} {_DEV_PORT} >/dev/null 2>&1 </dev/null &")


def _u2_touch(force=False):
    """Keep the on-phone idle timer alive: non-blocking, at most once a minute."""
    now = _time.time()
    if not force and now - _U2["touch_at"] < 60:
        return
    _U2["touch_at"] = now
    try:
        from phone_harness import android as _A
        _subprocess.Popen([_A._adb_bin(), "-s", _serial(), "shell", f"touch {_DEV_DIR}/last_use"],
                          stdout=_subprocess.DEVNULL, stderr=_subprocess.DEVNULL)
    except Exception:
        pass


def _u2_ensure(phone):
    if _U2["ready"] and _U2["port"]:
        _u2_touch()
        return _U2["port"]
    port = _VIA_ADB if _os.environ.get("PH_FAST_TREE_VIA") == "adb" else _u2_local_port()
    if port != _VIA_ADB and not _u2_ping(port) and _u2_ping(_VIA_ADB, timeout=2.0):
        port = _VIA_ADB                                     # remote adb server: forward is not local
    if not _u2_ping(port):
        _u2_start(phone)
        deadline = _time.time() + 20
        checked_at = _time.time()
        while not _u2_ping(port, timeout=1.0):
            dead = False
            if _time.time() - checked_at > 1.0:              # server exited early? fail fast
                checked_at = _time.time()
                dead = "alive" not in phone._sh(
                    f"p=$(cat {_DEV_DIR}/server.pid 2>/dev/null) && kill -0 $p 2>/dev/null && echo alive; true")
                if not dead and port != _VIA_ADB and _u2_ping(_VIA_ADB, timeout=1.0):
                    port = _VIA_ADB                         # up, but the forward is not on this host
                    break
            if dead or _time.time() > deadline:
                log = phone._sh(f"tail -5 {_DEV_DIR}/server.log 2>/dev/null; true").strip()
                raise RuntimeError(f"u2 server did not come up: {log[-300:]}")
            _time.sleep(0.25)
    cfg = _u2_rpc(port, "getConfigurator")
    # uiAutomationFlags=1 is FLAG_DONT_SUPPRESS_ACCESSIBILITY_SERVICES. With the
    # server's default 0, the phone's own accessibility services (Lawnchair on
    # the phone) stay unbound for as long as the server runs.
    if cfg.get("uiAutomationFlags") != 1 or cfg.get("waitForIdleTimeout") != 0:
        cfg["uiAutomationFlags"] = 1
        cfg["waitForIdleTimeout"] = 0
        _u2_rpc(port, "setConfigurator", [cfg])
    _U2.update(port=port, ready=True)
    _u2_touch(force=True)
    return port


# root_in_active=True dumps the active window only, which is what the stock
# `uiautomator dump` returns (all windows adds e.g. empty status-bar nodes).
_DUMP_ARGS = [False, 50] if _os.environ.get("PH_FAST_TREE_ALL_WINDOWS") == "1" else [False, 50, True]


def _u2_dump(port):
    def once():
        try:
            return _u2_rpc(port, "dumpWindowHierarchy", _DUMP_ARGS, timeout=15)
        except RuntimeError:
            if len(_DUMP_ARGS) == 3:                        # older server without root_in_active
                del _DUMP_ARGS[2:]
                return _u2_rpc(port, "dumpWindowHierarchy", _DUMP_ARGS, timeout=15)
            raise
    xml = once()
    if not xml or "<node" not in xml:
        _time.sleep(0.3)                                    # transient empty tree: retry once
        xml = once()
        if not xml or "<node" not in xml:
            raise ValueError("empty hierarchy")
    return xml


def _parse_nodes(xml):
    """Same node dicts, same document order as phone_harness.android.Android._tree."""
    root = _ET.fromstring(xml.encode("utf-8") if isinstance(xml, str) else xml)
    nodes = []
    for el in root.iter("node"):
        if el.get("visible-to-user") == "false":
            continue
        m = _re.match(r"\[(\d+),(\d+)\]\[(\d+),(\d+)\]", el.get("bounds", ""))
        if not m:
            continue
        x1, y1, x2, y2 = map(int, m.groups())
        nodes.append({
            "text": el.get("text", ""), "desc": el.get("content-desc", ""),
            "id": el.get("resource-id", ""),
            "class": el.get("class", ""),
            "clickable": el.get("clickable") == "true",
            "x": (x1 + x2) // 2, "y": (y1 + y2) // 2,
            "w": x2 - x1, "h": y2 - y1,
            # Extra keys (the upstream run_goal PR adds the same to the stock tree): goal
            # loops use them to refuse switches and password fields.
            "checkable": el.get("checkable") == "true", "checked": el.get("checked") == "true",
            "password": el.get("password") == "true", "package": el.get("package", ""),
        })
    return nodes


def _fast_tree(self):
    _U2["last_xml"] = None                        # raw XML of this read, for callers needing more attributes
    if not _fast_tree_wanted():
        if not _U2.get("stopped_for_stock"):
            # A stock `uiautomator dump` is killed while our server holds
            # UiAutomation, so step aside once before using it.
            _U2["stopped_for_stock"] = True
            try:
                self._sh(_KILL_OURS)
            except Exception:
                pass
        return _ORIG["_tree"](self)
    self._screen_require()
    self._gate()                                  # locked / asleep raises here, as stock does
    try:
        port = _u2_ensure(self)
        xml = _u2_dump(port)
        if _time.time() - _U2["last_action"] < _SETTLE_WINDOW:
            # The stock dump waits for idle. Right after an input action,
            # emulate that cheaply: read until two dumps in a row agree.
            deadline = _time.time() + _SETTLE_MAX
            while _time.time() < deadline:
                _time.sleep(_SETTLE_GAP)
                nxt = _u2_dump(port)
                if nxt == xml:
                    break
                xml = nxt
        nodes = _parse_nodes(xml)
        if not nodes:
            raise ValueError("hierarchy parsed to zero nodes")
        _U2["last_xml"] = xml
        self._tree_busy_until = 0.0
        _U2["fast_reads"] += 1
        return nodes
    except Exception as e:
        reason = f"{type(e).__name__}: {e}"[:300]
        _U2.update(disabled=reason, ready=False)
        _U2["fallbacks"] += 1
        _log(f"falling back to `uiautomator dump` ({reason})")
        try:
            _FAIL_MARK.write_text(f"{_time.strftime('%Y-%m-%dT%H:%M:%S')} {reason}\n")
        except OSError:
            pass
        try:
            self._sh(_KILL_OURS)      # a stock dump is killed while another UiAutomation is up
        except Exception:
            pass
        return _ORIG["_tree"](self)


def _fast_screen_status(self):
    """Stock asks two dumpsys questions in two adb round trips; same questions, one trip."""
    out = self._sh("dumpsys power | grep -m1 mWakefulness=; "
                   "dumpsys window | grep -m1 isKeyguardShowing")
    return "Awake" in out, "isKeyguardShowing=true" in out


_ACTIONS = ("_input_tap", "_input_press", "_input_drag", "_input_scroll", "_input_keys",
            "_input_text", "_nav_home", "_nav_back", "_nav_recents", "_apps_launch")


def install():
    """Patch phone_harness.android.Android in place (idempotent)."""
    try:
        from phone_harness import android as _A
    except Exception:
        return False
    cls = _A.Android
    if getattr(cls._tree, "_ph_fast", False):
        return True
    _ORIG["_tree"] = cls._tree
    _ORIG["_screen_status"] = cls._screen_status
    _fast_tree._ph_fast = True
    cls._tree = _fast_tree
    cls._screen_status = _fast_screen_status

    def wrap(name):
        orig = getattr(cls, name, None)
        if orig is None:
            return

        def action(self, *a, **k):
            try:
                return orig(self, *a, **k)
            finally:
                _U2["last_action"] = _time.time()
        action.__name__ = name
        setattr(cls, name, action)
    for n in _ACTIONS:
        wrap(n)
    return True


def _helpers_mod():
    import phone_harness.helpers as h
    return h


def _is_android(p):
    try:
        from phone_harness import android as _A
        return isinstance(p, _A.Android)
    except Exception:
        return False


try:                                    # captured before agent_helpers overrides the name
    _ORIG_WAIT_STABLE = _helpers_mod().wait_stable
except Exception:
    _ORIG_WAIT_STABLE = None


def wait_stable(timeout=6.0, interval=0.3, settle=2):
    """Wait until `settle` consecutive captures are identical (animation done).
    Android: hashed on the phone (`screencap | md5sum`) instead of pulling a
    PNG per poll. Other devices, or PH_FAST_WAIT=0: stock behaviour."""
    ph = _helpers_mod().phone
    if not _is_android(ph) or _os.environ.get("PH_FAST_WAIT", "1") == "0":
        return _ORIG_WAIT_STABLE(timeout=timeout, interval=interval, settle=settle)
    ph._screen_require()
    prev, same = None, 0
    deadline = _time.time() + timeout
    while _time.time() < deadline:
        try:
            out = ph._adb("exec-out", "screencap | md5sum", timeout=15)
        except Exception:
            out = ""
        parts = out.split() if out else []
        digest = parts[0] if parts else ""
        if len(digest) != 32:                         # no md5sum here: stock path
            return _ORIG_WAIT_STABLE(timeout=max(0.5, deadline - _time.time()),
                                     interval=interval, settle=settle)
        same = same + 1 if digest == prev else 0
        if same >= settle - 1:
            return True
        prev = digest
        _time.sleep(interval)
    return False


def wait_for_text(query, timeout=10.0, exact=False, interval=0.25):
    """Poll until `query` is visible; -> its box or None (stock logic, faster poll)."""
    h = _helpers_mod()
    deadline = _time.time() + timeout
    while True:
        hits = h.find_text(query, exact=exact)
        if hits:
            return hits[0]
        if _time.time() >= deadline:
            return None
        _time.sleep(interval)


def fast_tree_status():
    """What the fast path is doing in this process, plus the on-phone server pid."""
    st = {"enabled": _fast_tree_wanted(),
          **{k: _U2[k] for k in ("ready", "port", "disabled", "fallbacks", "fast_reads")},
          "device_port": _DEV_PORT, "idle_s": _IDLE,
          "fail_mark": _FAIL_MARK.read_text().strip() if _FAIL_MARK.exists() else None}
    try:
        ph = _helpers_mod().phone
        if _is_android(ph):
            ph._screen_require()
            st["server_pid"] = ph._sh(f"cat {_DEV_DIR}/server.pid 2>/dev/null; true").strip() or None
    except Exception as e:
        st["server_pid"] = f"? {e}"
    return st


def fast_tree_last_xml():
    """Raw hierarchy XML behind the most recent fast read, or None after a stock read.
    For callers that need attributes the node dicts drop (password, focused, checkable...)."""
    return _U2.get("last_xml")


def fast_tree_stop():
    """Stop the on-phone server now and drop its adb forward; the next read restarts it."""
    ph = _helpers_mod().phone
    ph._screen_require()
    ph._sh(_KILL_OURS)
    serial = _serial()
    for line in _adb_run("forward", "--list", check=False).splitlines():
        p = line.split()
        if len(p) == 3 and p[0] == serial and p[2] == f"tcp:{_DEV_PORT}":
            _adb_run("-s", serial, "forward", "--remove", p[1], check=False)
    _U2.update(ready=False, port=None)
    return True


def fast_tree_uninstall():
    """Stop the server and delete everything it put on the phone (no APKs are involved)."""
    fast_tree_stop()
    _helpers_mod().phone._sh(f"rm -rf {_DEV_DIR} /data/local/tmp/u2; true")
    return True
