"""Private stdlib primitives shared by the explicit PRoot host-lane adapters."""
import contextlib
import fcntl
import json
import os
from pathlib import Path
import re
import signal
import tempfile
import time


class Blocked(Exception):
    pass


def atomic(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, tmp = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, sort_keys=True)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, path)
        fd = os.open(path.parent, os.O_DIRECTORY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except FileNotFoundError:
        return default


@contextlib.contextmanager
def lock(path, blocking=True):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
        except BlockingIOError:
            raise Blocked("already running") from None
        yield stream


def identity(pid=None):
    pid = pid or os.getpid()
    try:
        stat = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        if stat[0] == "Z":
            return None
        return {"pid": int(pid), "start": stat[19],
                "boot": Path("/proc/sys/kernel/random/boot_id").read_text().strip()}
    except (OSError, IndexError):
        return None


def alive(value):
    return bool(value and identity(value.get("pid")) == value)


def notify(state, event):
    import socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as sock:
            sock.sendto(event.encode(), str(Path(state) / "events.sock"))
        return True
    except OSError:
        return False


def identifier(value):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,95}", value):
        raise Blocked("invalid job/service identifier")
    return value


def platform_supported():
    return "android" in os.uname().release.lower() and not Path("/run/systemd/system").exists()


CAPABILITIES = {"adapter": "proot-host-lane", "kubernetes_member": False,
                "kubelet": False, "android_root": False, "cgroups": False,
                "hard_memory_limit": False, "security_isolation": False,
                "network_isolation": False, "durable_stop": True,
                "execution": "trusted-owner-code-only"}


def host_health(probe, now=None, max_age=180, floor=1200, reserve=512):
    now = time.time() if now is None else now
    if probe.get("error"):
        return "unavailable", ["ssh/probe unavailable"]
    if not isinstance(probe.get("ts"), (int, float)) or not 0 <= now - probe["ts"] <= max_age:
        return "stale", ["health evidence expired or clock skew"]
    if probe.get("paused") or probe.get("maintenance"):
        return "paused", ["explicit owner pause/maintenance"]
    if probe.get("host_lane_supported") is False:
        return "unsupported", ["not an Android PRoot host lane"]
    bad = []
    if probe.get("mem_available_mb", 0) < floor + reserve:
        bad.append("memory below admission floor + reservation")
    pw = probe.get("power") or {}
    bats = pw.get("batteries") or []
    if not bats or pw.get("source") == "unreadable":
        bad.append("battery unreadable")
    else:
        for bat in bats:
            pct = bat.get("pct")
            if not isinstance(pct, (int, float)):
                bad.append("battery unreadable")
            elif pct < 50 and not (pw.get("on_ac") or bat.get("status") in ("Charging", "Full")):
                bad.append("battery below 50% off charger")
    temp, thermal = pw.get("battery_temp_c"), pw.get("android_thermal_status")
    if not isinstance(temp, (int, float)) or temp > 40:
        bad.append("battery temperature unreadable/hot")
    if not isinstance(thermal, (int, float)) or thermal > 1:
        bad.append("Android thermal unreadable/hot")
    if any(v != "active" for v in (probe.get("services") or {}).values()):
        bad.append("guest service degraded")
    return ("paused", bad) if bad else ("ready", [])


async def drain(proc, grace=15):
    import asyncio
    if proc.returncode is not None:
        return
    try:
        os.killpg(proc.pid, signal.SIGTERM)
    except ProcessLookupError:
        pass
    try:
        await asyncio.wait_for(proc.wait(), grace)
    except asyncio.TimeoutError:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        await proc.wait()
    # Also reap descendants left in this owned process group by an exiting shell.
    try:
        os.killpg(proc.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
