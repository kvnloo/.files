#!/usr/bin/env python3
"""Emit privacy-safe host telemetry for the Noctalia hardware monitor."""

from __future__ import annotations

import json
import math
import os
from pathlib import Path
import socket
import statistics
import subprocess
import time

RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "noctalia-hardware-monitor-state.json"


def number(value: str) -> float:
    try:
        parsed = float(value.strip())
        return parsed if math.isfinite(parsed) else 0.0
    except (TypeError, ValueError):
        return 0.0


def percentile(values: list[float], fraction: float = 0.95) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1)]


def gpu_stats() -> dict[str, object]:
    fields = (
        "name,utilization.gpu,temperature.gpu,fan.speed,power.draw,power.limit,"
        "memory.used,memory.total,clocks.current.graphics,clocks.current.memory,"
        "pstate,pcie.link.gen.current,pcie.link.width.current"
    )
    try:
        result = subprocess.run(
            ["nvidia-smi", f"--query-gpu={fields}", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return {"available": False}
    if result.returncode != 0 or not result.stdout.strip():
        return {"available": False, "error": result.stderr.strip()}
    values = [part.strip() for part in result.stdout.splitlines()[0].split(",")]
    if len(values) < 13:
        return {"available": False, "error": "Incomplete nvidia-smi response"}
    return {
        "available": True,
        "name": values[0],
        "utilization": number(values[1]),
        "temperature": number(values[2]),
        "fanPercent": number(values[3]),
        "powerWatts": number(values[4]),
        "powerLimitWatts": number(values[5]),
        "vramUsedMiB": number(values[6]),
        "vramTotalMiB": number(values[7]),
        "coreClockMHz": number(values[8]),
        "memoryClockMHz": number(values[9]),
        "performanceState": values[10],
        "pcieGeneration": values[11],
        "pcieWidth": values[12],
    }


def pressure_stats() -> dict[str, float]:
    result: dict[str, float] = {}
    for resource in ("cpu", "memory", "io"):
        try:
            lines = Path(f"/proc/pressure/{resource}").read_text().splitlines()
        except OSError:
            continue
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            level = parts[0]
            values = dict(item.split("=", 1) for item in parts[1:] if "=" in item)
            result[resource + level.title()] = number(values.get("avg10", "0"))
        result[resource] = result.get(resource + "Some", 0.0)
    return result


def read_kernel_counters() -> dict[str, int]:
    counters = {
        "interrupts": 0,
        "contextSwitches": 0,
        "softirqs": 0,
        "running": 0,
        "majorFaults": 0,
        "swapInPages": 0,
        "swapOutPages": 0,
    }
    try:
        for line in Path("/proc/stat").read_text().splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] == "intr":
                counters["interrupts"] = int(parts[1])
            elif parts[0] == "ctxt":
                counters["contextSwitches"] = int(parts[1])
            elif parts[0] == "procs_running":
                counters["running"] = int(parts[1])
    except (OSError, ValueError, IndexError):
        pass
    try:
        lines = Path("/proc/softirqs").read_text().splitlines()[1:]
        counters["softirqs"] = sum(
            int(value)
            for line in lines
            for value in line.split()[1:]
        )
    except (OSError, ValueError, IndexError):
        pass
    try:
        for line in Path("/proc/vmstat").read_text().splitlines():
            key, value = line.split()
            if key == "pgmajfault":
                counters["majorFaults"] = int(value)
            elif key == "pswpin":
                counters["swapInPages"] = int(value)
            elif key == "pswpout":
                counters["swapOutPages"] = int(value)
    except (OSError, ValueError):
        pass
    return counters


def rates(current: dict[str, int], now: float) -> dict[str, float]:
    previous: dict[str, object] = {}
    try:
        previous = json.loads(RUNTIME.read_text())
    except (OSError, json.JSONDecodeError):
        pass
    elapsed = max(0.001, now - float(previous.get("timestamp", now)))
    result = {}
    for key in (
        "interrupts",
        "softirqs",
        "contextSwitches",
        "majorFaults",
        "swapInPages",
        "swapOutPages",
    ):
        old = int(previous.get(key, current[key]))
        result[key + "PerSecond"] = max(0.0, (current[key] - old) / elapsed)
    payload = {"timestamp": now, **current}
    try:
        temporary = RUNTIME.with_suffix(".tmp")
        temporary.write_text(json.dumps(payload))
        temporary.replace(RUNTIME)
    except OSError:
        pass
    page_mib = os.sysconf("SC_PAGE_SIZE") / 1024 / 1024
    result["swapInMiBPerSecond"] = result.pop("swapInPagesPerSecond") * page_mib
    result["swapOutMiBPerSecond"] = result.pop("swapOutPagesPerSecond") * page_mib
    result["running"] = current["running"]
    return result


def latency_stats() -> dict[str, float]:
    wake_samples = []
    for _ in range(100):
        started = time.perf_counter_ns()
        time.sleep(0.001)
        wake_samples.append(max(0.0, (time.perf_counter_ns() - started - 1_000_000) / 1000))

    left, right = socket.socketpair()
    ipc_samples = []
    try:
        for _ in range(256):
            started = time.perf_counter_ns()
            left.send(b"x")
            right.recv(1)
            ipc_samples.append((time.perf_counter_ns() - started) / 1000)
    finally:
        left.close()
        right.close()
    return {
        "wakeP95Us": percentile(wake_samples),
        "wakeP99Us": percentile(wake_samples, 0.99),
        "wakeMaxUs": max(wake_samples, default=0.0),
        "wakeMedianUs": statistics.median(wake_samples),
        "ipcP95Us": percentile(ipc_samples),
        "ipcP99Us": percentile(ipc_samples, 0.99),
        "ipcMaxUs": max(ipc_samples, default=0.0),
        "ipcMedianUs": statistics.median(ipc_samples),
    }


def hwmon_stats() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    temperatures: list[dict[str, object]] = []
    fans: list[dict[str, object]] = []
    for hwmon in Path("/sys/class/hwmon").glob("hwmon*"):
        try:
            chip = (hwmon / "name").read_text().strip()
        except OSError:
            continue
        for source in hwmon.glob("temp*_input"):
            try:
                value = number(source.read_text()) / 1000
            except OSError:
                continue
            if value <= 0 or value >= 150:
                continue
            label_file = source.with_name(source.name.replace("_input", "_label"))
            try:
                label = label_file.read_text().strip()
            except OSError:
                label = source.stem.replace("_input", "")
            temperatures.append({"chip": chip, "label": label, "celsius": round(value, 1)})
        for source in hwmon.glob("fan*_input"):
            try:
                value = int(number(source.read_text()))
            except OSError:
                continue
            label_file = source.with_name(source.name.replace("_input", "_label"))
            try:
                label = label_file.read_text().strip()
            except OSError:
                label = source.stem.replace("_input", "")
            if value > 0:
                fans.append({"chip": chip, "label": label, "rpm": value})
    temperatures.sort(key=lambda item: (str(item["chip"]), str(item["label"])))
    fans.sort(key=lambda item: (str(item["chip"]), str(item["label"])))
    return temperatures, fans


def swap_stats() -> list[dict[str, object]]:
    swaps: list[dict[str, object]] = []
    try:
        lines = Path("/proc/swaps").read_text().splitlines()[1:]
    except OSError:
        return swaps
    for line in lines:
        parts = line.split()
        if len(parts) < 5:
            continue
        path, swap_type, size_kib, used_kib, priority = parts[:5]
        try:
            size = int(size_kib)
            used = int(used_kib)
            priority_value = int(priority)
        except ValueError:
            continue
        swaps.append({
            "path": path,
            "label": Path(path).name or path,
            "type": swap_type,
            "sizeGiB": round(size / 1024 / 1024, 2),
            "usedGiB": round(used / 1024 / 1024, 2),
            "percent": round(100 * used / size, 1) if size > 0 else 0.0,
            "priority": priority_value,
        })
    swaps.sort(key=lambda item: (-int(item["priority"]), str(item["path"])))
    return swaps


def main() -> None:
    now = time.monotonic()
    counters = read_kernel_counters()
    temperatures, fans = hwmon_stats()
    print(json.dumps({
        "timestamp": time.time(),
        "gpu": gpu_stats(),
        "latency": latency_stats(),
        "pressure": pressure_stats(),
        "kernel": rates(counters, now),
        "temperatures": temperatures,
        "fans": fans,
        "swaps": swap_stats(),
    }, separators=(",", ":")))


if __name__ == "__main__":
    main()
