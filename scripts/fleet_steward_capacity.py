"""Fleet-health projection of the #133/#134 z0.capacity.snapshot.v1 contract.

This is an input proposal, not a scheduler or the canonical joined snapshot.
Performance lessons remain in parameters.json because v1 has no such fields.
"""
import json
import math
import os
from pathlib import Path
import time


RESOURCE_KEYS = ("cpu_logical", "ram_total_bytes", "ram_available_bytes",
                 "storage_total_bytes", "storage_free_bytes", "gpu_count")


def number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0 else None


def scaled(value, multiplier):
    value = number(value)
    return int(value * multiplier) if value is not None else None


def build_capacity(records, now=None):
    now = time.time() if now is None else now
    hosts = []
    caveats = set()
    for record in records:
        name = record.get("node")
        if not isinstance(name, str) or not name:
            continue
        probe = record.get("probe") or {}
        observed = number(probe.get("ts")) or number(record.get("ts"))
        fresh = observed is not None and 0 <= now - observed <= 300 and "error" not in probe
        resources = dict.fromkeys(RESOURCE_KEYS)
        resources["gpus"] = []
        if fresh:
            resources.update(cpu_logical=number(probe.get("ncpu")),
                             ram_total_bytes=scaled(probe.get("mem_total_mb"), 2**20),
                             ram_available_bytes=scaled(probe.get("mem_available_mb"), 2**20))
            disk = probe.get("disk_lane") or probe.get("disk_root") or {}
            resources["storage_total_bytes"] = number(disk.get("total_bytes"))
            resources["storage_free_bytes"] = number(disk.get("free_bytes"))
            if resources["storage_total_bytes"] is None:
                resources["storage_total_bytes"] = scaled(disk.get("total_gb"), 2**30)
            if resources["storage_free_bytes"] is None:
                resources["storage_free_bytes"] = scaled(disk.get("free_gb"), 2**30)
            if disk and ("total_bytes" not in disk or "free_bytes" not in disk):
                caveats.add("legacy disk bytes are approximate conversions from rounded probe GiB")
        else:
            caveats.add("stale/unavailable hosts retain identity but numeric resources are unknown")
        host_id = probe.get("host_id")
        if not isinstance(host_id, str) or not host_id:
            host_id = "fleet:" + name
            caveats.add("legacy fleet: identities require canonical producer alias review, not hostname deduplication")
        hosts.append({"host_id": host_id, "label": name, "mode": "remote",
                      "status": "online" if fresh and record.get("healthy") else "degraded" if fresh else "unknown",
                      "rtt_ms": None, "resources": resources, "observed_at": observed})
    caveats.add("physical host resources are not lane headroom or placement offers")
    caveats.add("thermal/runtime/toolchain lessons remain in parameters.json; no v1 extension fields")
    return {"schema": "z0.capacity.snapshot.v1", "generated_at": now,
            "status": "ok" if hosts and all(host["status"] == "online" for host in hosts) else "degraded",
            "sources": {"fleet": {"status": "ok" if hosts else "missing", "observed_at": now,
                                   "reason": "; ".join(sorted(caveats))},
                        "tern": {"status": "missing", "reason": "not joined by fleet steward"},
                        "kerdoios": {"status": "missing", "reason": "placement remains downstream-owned"},
                        "leases": {"status": "missing", "reason": "not observed"}},
            "hosts": sorted(hosts, key=lambda host: host["host_id"]), "sessions": [], "offers": [], "leases": [],
            "summary": {"hosts": len(hosts), "sessions": 0, "offers": 0, "leases": 0}}


def export_capacity(state: Path, output: Path):
    records = []
    for path in sorted((Path(state) / "health").glob("*.json")):
        try:
            record = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(record, dict) and "node" in record and "probe" in record:
            records.append(record)
    snapshot = build_capacity(records)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    temporary = output / f".capacity.{os.getpid()}.tmp"
    temporary.write_text(json.dumps(snapshot, indent=2, sort_keys=True, allow_nan=False) + "\n")
    temporary.chmod(0o600)
    temporary.replace(output / "capacity.json")
    return snapshot
