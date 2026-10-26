"""networkState sampler -- read-only, runs on groot (never on mbp).

Per the Revisions (R8): the laptop (mbp) is read with ONE cheap pull over an
existing ssh channel -- a cat of /proc files, a 2s timeout, no `ps` fan-out.
Top-RSS is fetched only when a lag has already been detected, at most once per
cycle. If mbp does not answer in 2s, it is treated as lagging (fail safe) and is
not retried in a loop.

groot (the host this runs on) is read from local /proc and nvidia-smi directly,
so sampling costs the laptop nothing.

No tailnet IPs or host literals are embedded: the peer alias comes from the
environment (NETOPT_PEER_HOST, default "mbp"), which resolves via ~/.ssh/config.
Output: ~/tmp/network/state/latest.json  (+ a rolling history line).
"""

from __future__ import annotations

import json
import os
import pathlib
import shutil
import subprocess
import time

PEER = os.environ.get("NETOPT_PEER_HOST", "mbp")
SELF = os.environ.get("NETOPT_SELF_HOST", "groot")
BASE = pathlib.Path(os.environ.get(
    "NETOPT_BASE", str(pathlib.Path.home() / "tmp" / "network")))
STATE_DIR = BASE / "state"
KILLS = pathlib.Path(os.environ.get(
    "NETOPT_KILLS", str(pathlib.Path.home() / ".local/state/agent-oom/kills.jsonl")))
PULL_TIMEOUT_S = 2
KILL_WINDOW_S = 600


def _parse_pressure(blob: str) -> dict:
    """Parse /proc/pressure/<res> text into {some_avg10, some_avg60, full_avg10...}."""
    out = {}
    for line in blob.splitlines():
        parts = line.split()
        if not parts:
            continue
        kind = parts[0]  # some | full
        for p in parts[1:]:
            if "=" in p:
                k, v = p.split("=", 1)
                if k.startswith("avg"):
                    try:
                        out[f"{kind}_{k}"] = float(v)
                    except ValueError:
                        pass
    return out


def _mem_from_meminfo(blob: str) -> dict:
    mi = {}
    for line in blob.splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            mi[k.strip()] = v.strip()

    def kib(key):
        try:
            return int(mi.get(key, "0 kB").split()[0])
        except (ValueError, IndexError):
            return 0
    swap_total = kib("SwapTotal")
    swap_free = kib("SwapFree")
    swap_used = swap_total - swap_free
    return {
        "mem_total_mib": kib("MemTotal") // 1024,
        "mem_available_mib": kib("MemAvailable") // 1024,
        "swap_total_mib": swap_total // 1024,
        "swap_used_mib": swap_used // 1024,
        "swap_frac": round(swap_used / swap_total, 4) if swap_total else 0.0,
    }


def _host_fields(cpu: str, mem: str, io: str, loadavg: str, meminfo: str) -> dict:
    cpup = _parse_pressure(cpu)
    memp = _parse_pressure(mem)
    iop = _parse_pressure(io)
    la = loadavg.split()
    return {
        "psi_cpu_some_avg10": cpup.get("some_avg10", 0.0),
        "psi_cpu_some_avg60": cpup.get("some_avg60", 0.0),
        "psi_mem_some_avg10": memp.get("some_avg10", 0.0),
        "psi_mem_full_avg10": memp.get("full_avg10", 0.0),
        "psi_mem_full_avg60": memp.get("full_avg60", 0.0),
        "psi_io_some_avg10": iop.get("some_avg10", 0.0),
        "load1": float(la[0]) if la else 0.0,
        "load5": float(la[1]) if len(la) > 1 else 0.0,
        **_mem_from_meminfo(meminfo),
    }


def sample_local() -> dict:
    """groot: read local /proc directly (free)."""
    def rd(p):
        try:
            return pathlib.Path(p).read_text()
        except OSError:
            return ""
    h = _host_fields(
        rd("/proc/pressure/cpu"), rd("/proc/pressure/memory"),
        rd("/proc/pressure/io"), rd("/proc/loadavg"), rd("/proc/meminfo"))
    h.update(reachable=True, vram_free_mib=_gpu_free_mib(),
             kills_last_10min=_kill_rate(), source="local")
    return h


def _gpu_free_mib() -> int | None:
    if not shutil.which("nvidia-smi"):
        return None
    try:
        out = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5)
        return int(out.stdout.strip().splitlines()[0])
    except (subprocess.SubprocessError, ValueError, IndexError):
        return None


def _kill_rate() -> int:
    """How many agent-oom kills in the last 10 min (the gate's storm signal)."""
    if not KILLS.exists():
        return 0
    now = time.time()
    n = 0
    try:
        for line in KILLS.read_text(errors="ignore").splitlines()[-500:]:
            try:
                rec = json.loads(line)
            except ValueError:
                continue
            ts = rec.get("ts") or rec.get("timestamp") or 0
            if isinstance(ts, str):
                try:
                    ts = time.mktime(time.strptime(ts[:19], "%Y-%m-%dT%H:%M:%S"))
                except ValueError:
                    ts = 0
            if now - float(ts) <= KILL_WINDOW_S:
                n += 1
    except OSError:
        return 0
    return n


def sample_peer(detail: bool = False) -> dict:
    """mbp: ONE cheap ssh pull (R8). stdout only; fish login noise -> stderr.
    If it does not answer in PULL_TIMEOUT_S, treat as lagging (fail safe)."""
    cmd = ("cat /proc/pressure/cpu; echo @@; cat /proc/pressure/memory; echo @@; "
           "cat /proc/pressure/io; echo @@; cat /proc/loadavg; echo @@; "
           "cat /proc/meminfo")
    try:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={PULL_TIMEOUT_S}",
             PEER, cmd],
            capture_output=True, text=True, timeout=PULL_TIMEOUT_S + 3)
        if out.returncode != 0 or "@@" not in out.stdout:
            raise subprocess.SubprocessError(out.stderr[:200])
        cpu, mem, io, load, meminfo = out.stdout.split("@@")
        h = _host_fields(cpu, mem, io, load, meminfo)
        h.update(reachable=True, source="ssh-pull")
        if detail:
            h["top_rss"] = _peer_top_rss()
        return h
    except (subprocess.SubprocessError, subprocess.TimeoutExpired, ValueError):
        # Fail safe: unreachable == lagging (do not retry in a loop).
        return {"reachable": False, "source": "ssh-pull",
                "psi_cpu_some_avg10": 100.0, "psi_mem_full_avg60": 100.0,
                "swap_frac": 1.0, "note": "peer unreachable -> treated as lagging"}


def _peer_top_rss(n: int = 5) -> list:
    """Only called once a lag is already detected (R8)."""
    cmd = ("ps -eo rss,comm --sort=-rss --no-headers | head -n %d" % n)
    try:
        out = subprocess.run(
            ["ssh", "-o", "BatchMode=yes", "-o", f"ConnectTimeout={PULL_TIMEOUT_S}",
             PEER, cmd], capture_output=True, text=True, timeout=PULL_TIMEOUT_S + 3)
        rows = []
        for line in out.stdout.splitlines():
            parts = line.split(None, 1)
            if len(parts) == 2:
                rows.append({"rss_mib": int(parts[0]) // 1024, "comm": parts[1]})
        return rows
    except (subprocess.SubprocessError, ValueError):
        return []


def sample() -> dict:
    local = sample_local()
    peer = sample_peer(detail=False)
    # Fetch peer top-RSS only if the peer is already lagging (R8).
    peer_lagging = (peer.get("psi_cpu_some_avg10", 0) > 60
                    or peer.get("psi_mem_full_avg60", 0) > 5
                    or peer.get("swap_frac", 0) > 0.6)
    if peer.get("reachable") and peer_lagging:
        peer["top_rss"] = _peer_top_rss()
    return {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "epoch": int(time.time()),
        "hosts": {SELF: local, PEER: peer},
    }


def write_state(state: dict) -> pathlib.Path:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    latest = STATE_DIR / "latest.json"
    snap = STATE_DIR / f"{state['epoch']}.json"
    body = json.dumps(state, indent=2)
    snap.write_text(body)
    latest.write_text(body)
    # keep last ~120 snapshots (~2h at 60s)
    snaps = sorted(STATE_DIR.glob("[0-9]*.json"))
    for old in snaps[:-120]:
        try:
            old.unlink()
        except OSError:
            pass
    return latest


if __name__ == "__main__":
    st = sample()
    p = write_state(st)
    print(json.dumps(st, indent=2))
    print(f"\n# wrote {p}", flush=True)
