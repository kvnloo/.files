#!/usr/bin/env python3
"""Measure disk reserves without UI input. Repair only the existing uv cache policy."""
import argparse
import datetime
import fcntl
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import time
import uuid


MOUNTS = ("/", "/workspace", "/mnt/zer0models")
# Same hardware identities as the deployed scripts/fleet-adb HARDWARE registry.
PHONES = {"s25": "R5CY93G2WNH", "s22": "RFCTA1RZAQY"}
GIB = 1024 ** 3


def command(argv, timeout=8):
    result = subprocess.run(argv, stdin=subprocess.DEVNULL, capture_output=True,
                            text=True, timeout=timeout, check=True)
    return result.stdout + result.stderr if argv[0] == "uv" else result.stdout


def pressure(total, available):
    if total <= 0 or not 0 <= available <= total:
        raise ValueError("invalid disk measurement")
    return available < 15 * GIB or available / total < 0.10


def local_disk(path):
    try:
        stats = os.statvfs(path)
        total = stats.f_blocks * stats.f_frsize
        available = stats.f_bavail * stats.f_frsize
        return {"host": "groot", "path": path, "total_bytes": total,
                "available_bytes": available, "device": os.stat(path).st_dev,
                "status": "pressure" if pressure(total, available) else "ok"}
    except (OSError, ValueError) as exc:
        return {"host": "groot", "path": path, "status": "unknown", "error": type(exc).__name__}


def parse_df(text):
    rows = [line.split() for line in text.splitlines() if line.split()]
    # df /data can name a bind-mount alias such as /data/user/0 on Android.
    if len(rows) != 2 or len(rows[1]) != 6 or not rows[1][-1].startswith("/"):
        raise ValueError("unexpected df output")
    row = rows[1]
    total, used, available = (int(value) * 1024 for value in row[1:4])
    if used < 0 or used > total:
        raise ValueError("invalid used bytes")
    pressure(total, available)
    return total, available


def phone_disks(adb, run=command):
    base = [str(adb), "-H", "127.0.0.1", "-P", "5037"]
    found = {}
    errors = {}
    try:
        listing = run(base + ["devices"])
        transports = [parts[0] for line in listing.splitlines()
                      if len(parts := line.split()) == 2 and parts[1] == "device"]
        for transport in transports[:8]:
            try:
                serial = run(base + ["-s", transport, "shell", "getprop ro.serialno"]).strip()
                host = next((name for name, identity in PHONES.items() if serial == identity), None)
                if host is None or host in found:
                    continue
                total, available = parse_df(run(base + ["-s", transport, "shell", "df -kP /data"]))
                found[host] = {"host": host, "path": "/data", "serial": serial,
                               "transport": transport, "total_bytes": total,
                               "available_bytes": available,
                               "status": "pressure" if pressure(total, available) else "ok",
                               "repair": "none_authorized"}
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                errors[transport] = type(exc).__name__
    except (OSError, subprocess.SubprocessError) as exc:
        errors["adb"] = type(exc).__name__
    return [found.get(host, {"host": host, "path": "/data", "status": "unknown",
                             "error": "authenticated transport or disk measurement unavailable",
                             "probe_errors": errors, "repair": "none_authorized"})
            for host in PHONES]


def repair_uv(rows, cache, emit, run=command):
    cache = cache.resolve(strict=True)
    if not cache.is_dir():
        raise ValueError("uv cache is not a directory")
    # Match zer0_storage_autotier.py PRUNE_FORBIDDEN after resolving offload links.
    if cache == Path("/mnt/zer0models") or Path("/mnt/zer0models") in cache.parents:
        return {"status": "skipped", "cache": str(cache), "reason": "existing policy forbids pruning bulk storage"}
    device = cache.stat().st_dev
    if not any(row["status"] == "pressure" and row.get("device") == device for row in rows):
        return {"status": "skipped", "reason": "uv cache is not on a pressured measured device"}
    argv = ["uv", "cache", "prune", "--offline", "--no-config", "--cache-dir", str(cache)]
    before = shutil.disk_usage(cache).free
    emit({"event": "repair_planned", "argv": argv, "cache": str(cache), "free_before": before})
    try:
        output = run(argv, timeout=20)
        result = {"status": "completed", "output": output[-2048:]}
    except (OSError, subprocess.SubprocessError) as exc:
        result = {"status": "unknown" if isinstance(exc, subprocess.TimeoutExpired) else "failed",
                  "error": type(exc).__name__, "retry": "next scheduled tick only"}
    result.update({"cache": str(cache), "free_before": before, "free_after": shutil.disk_usage(cache).free})
    emit({"event": "repair_result", **result})
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--state-dir", type=Path, default=Path.home() / ".local/state/host-cleanup-pressure")
    parser.add_argument("--repair-uv", action="store_true", help="at most one 20-second offline prune on a pressured cache device")
    args = parser.parse_args()
    if socket.gethostname().split(".")[0] != "groot":
        parser.error("run on groot only; phone probes use groot's existing authenticated ADB server")
    os.umask(0o077)
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with (args.state_dir / ".lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({"status": "busy", "repair": "skipped"}))
            return 75
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        receipt = args.state_dir / f"{stamp}-{uuid.uuid4().hex}.jsonl"
        with receipt.open("x") as stream:
            def emit(row):
                stream.write(json.dumps({"ts": time.time(), **row}) + "\n")
                stream.flush()
                os.fsync(stream.fileno())

            emit({"event": "start", "repair_uv": args.repair_uv})
            rows = [local_disk(path) for path in MOUNTS]
            rows += phone_disks(Path.home() / "android/sdk/platform-tools/adb")
            emit({"event": "observations", "disks": rows})
            repair = {"status": "disabled"}
            if args.repair_uv:
                try:
                    repair = repair_uv(rows, Path.home() / ".cache/uv", emit)
                except (OSError, ValueError) as exc:
                    repair = {"status": "failed", "error": type(exc).__name__}
            after = [local_disk(path) for path in MOUNTS]
            unresolved = any(row["status"] != "ok" for row in after + rows[len(MOUNTS):])
            unresolved |= repair["status"] in ("failed", "unknown")
            summary = {"event": "summary", "receipt": str(receipt), "repair": repair,
                       "local_after": after, "unresolved": unresolved}
            emit(summary)
            print(json.dumps(summary))
            return 1 if unresolved else 0


if __name__ == "__main__":
    raise SystemExit(main())
