#!/usr/bin/env python3
"""Emit current traffic rates per physical and tunnel interface."""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import time

STATE = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "noctalia-connection-center-network.json"
IGNORED_PREFIXES = ("lo", "docker", "br-", "veth", "virbr", "ifb", "dummy")
VPN_PREFIXES = ("tun", "tap", "wg", "zt", "nebula")


def read_text(path: Path, fallback: str = "") -> str:
    try:
        return path.read_text().strip()
    except OSError:
        return fallback


def classify(name: str, root: Path) -> str:
    if name == "tailscale0":
        return "tailnet"
    if (root / "wireless").exists():
        return "wifi"
    if name.startswith(VPN_PREFIXES):
        return "vpn"
    try:
        resolved = root.resolve()
    except OSError:
        resolved = root
    if "/virtual/" not in str(resolved):
        return "ethernet"
    return "other"


def counters() -> dict[str, dict[str, object]]:
    result: dict[str, dict[str, object]] = {}
    for root in Path("/sys/class/net").iterdir():
        name = root.name
        if name.startswith(IGNORED_PREFIXES):
            continue
        try:
            rx = int((root / "statistics/rx_bytes").read_text())
            tx = int((root / "statistics/tx_bytes").read_text())
        except (OSError, ValueError):
            continue
        result[name] = {
            "rx": rx,
            "tx": tx,
            "category": classify(name, root),
            "active": read_text(root / "operstate") in {"up", "unknown"},
        }
    return result


def ping_ms() -> float | None:
    try:
        completed = subprocess.run(
            ["ping", "-n", "-c", "1", "-W", "1", "1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=1.5,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    match = re.search(r"time[=<]([0-9.]+)\s*ms", completed.stdout)
    return round(float(match.group(1)), 1) if match else None


def main() -> None:
    now = time.monotonic()
    current = counters()
    previous: dict[str, object] = {}
    try:
        previous = json.loads(STATE.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    elapsed = max(0.05, now - float(previous.get("timestamp", now)))
    old_interfaces = previous.get("interfaces", {})
    if not isinstance(old_interfaces, dict):
        old_interfaces = {}

    interfaces = []
    aggregate = {
        key: {"rxBps": 0.0, "txBps": 0.0, "active": False, "interfaces": []}
        for key in ("tailnet", "ethernet", "wifi", "vpn", "other", "total")
    }
    for name, item in current.items():
        old = old_interfaces.get(name, {})
        if not isinstance(old, dict):
            old = {}
        rx_bps = max(0.0, (int(item["rx"]) - int(old.get("rx", item["rx"]))) / elapsed)
        tx_bps = max(0.0, (int(item["tx"]) - int(old.get("tx", item["tx"]))) / elapsed)
        category = str(item["category"])
        row = {
            "name": name,
            "category": category,
            "active": bool(item["active"]),
            "rxBps": round(rx_bps, 1),
            "txBps": round(tx_bps, 1),
        }
        interfaces.append(row)
        for bucket in (aggregate[category], aggregate["total"]):
            bucket["rxBps"] += rx_bps
            bucket["txBps"] += tx_bps
            bucket["active"] = bool(bucket["active"] or item["active"])
            bucket["interfaces"].append(name)

    for bucket in aggregate.values():
        bucket["rxBps"] = round(float(bucket["rxBps"]), 1)
        bucket["txBps"] = round(float(bucket["txBps"]), 1)

    payload = {
        "timestamp": time.time(),
        "pingMs": ping_ms(),
        "interfaces": sorted(interfaces, key=lambda row: (str(row["category"]), str(row["name"]))),
        **aggregate,
        "note": "Ethernet is physical-link traffic and includes encrypted tailnet carriage.",
    }
    print(json.dumps(payload, separators=(",", ":")))

    state_payload = {
        "timestamp": now,
        "interfaces": {name: {"rx": item["rx"], "tx": item["tx"]} for name, item in current.items()},
    }
    try:
        temporary = STATE.with_suffix(".tmp")
        temporary.write_text(json.dumps(state_payload))
        temporary.replace(STATE)
    except OSError:
        pass


if __name__ == "__main__":
    main()
