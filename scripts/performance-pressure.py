#!/usr/bin/env python3
"""Enable unified desktop performance mode after sustained resource saturation."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import time

ROOT = Path(__file__).resolve().parent.parent
MODE = ROOT / "scripts" / "performance-mode.sh"
RUNTIME = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / f"performance-pressure-{os.getuid()}"
COOLDOWN_FILE = RUNTIME / "cancelled-until"
INTERVAL = float(os.environ.get("PERFORMANCE_SAMPLE_SECONDS", "5"))
TRIGGER = float(os.environ.get("PERFORMANCE_TRIGGER_PERCENT", "85"))
TRIGGER_SAMPLES = int(os.environ.get("PERFORMANCE_TRIGGER_SAMPLES", "2"))
RECOVERY = float(os.environ.get("PERFORMANCE_RECOVERY_PERCENT", "55"))
RECOVERY_SAMPLES = int(os.environ.get("PERFORMANCE_RECOVERY_SAMPLES", "24"))
ALERT_SECONDS = int(os.environ.get("PERFORMANCE_ALERT_SECONDS", "10"))
CANCEL_SECONDS = int(os.environ.get("PERFORMANCE_CANCEL_SECONDS", "600"))
SWAP_FULL_SCALE_MIB_S = 64.0


def read_fields(path: str) -> dict[str, int]:
    fields: dict[str, int] = {}
    try:
        for line in Path(path).read_text().splitlines():
            key, value, *_ = line.replace(":", "").split()
            fields[key] = int(value)
    except (OSError, ValueError):
        pass
    return fields


def cpu_counters() -> tuple[int, int]:
    try:
        values = [int(value) for value in Path("/proc/stat").read_text().splitlines()[0].split()[1:]]
    except (OSError, ValueError, IndexError):
        return (0, 0)
    idle = values[3] + (values[4] if len(values) > 4 else 0)
    return sum(values), idle


def pressure_average(resource: str, level: str = "full") -> float:
    try:
        lines = Path(f"/proc/pressure/{resource}").read_text().splitlines()
        selected = next(line for line in lines if line.startswith(f"{level} "))
        return float(next(field[6:] for field in selected.split() if field.startswith("avg10=")))
    except (OSError, ValueError, StopIteration, IndexError):
        return 0.0
def saturation_score(value: float, start: float, full: float) -> float:
    if value <= start:
        return 0.0
    return max(0.0, min((value - start) / (full - start) * 100.0, 100.0))



def gpu_percent() -> float:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu", "--format=csv,noheader,nounits"],
            text=True,
            capture_output=True,
            timeout=2,
            check=False,
        )
        values = [float(line.strip()) for line in result.stdout.splitlines() if line.strip()]
        return max(values, default=0.0)
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 0.0


def mode_status() -> tuple[bool, str]:
    try:
        result = subprocess.run([str(MODE), "status"], text=True, capture_output=True, timeout=3, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return False, ""
    words = result.stdout.strip().split()
    if not words or words[0] != "enabled":
        return False, ""
    origin = next((word.removeprefix("origin=") for word in words if word.startswith("origin=")), "manual")
    return True, origin


def set_mode(enabled: bool) -> None:
    action = "enable" if enabled else "disable"
    subprocess.run([str(MODE), action, "auto"], timeout=30, check=False)


def cancelled() -> bool:
    try:
        return time.time() < float(COOLDOWN_FILE.read_text().strip())
    except (OSError, ValueError):
        return False


def cancel_for_cooldown() -> None:
    RUNTIME.mkdir(mode=0o700, parents=True, exist_ok=True)
    COOLDOWN_FILE.write_text(f"{time.time() + CANCEL_SECONDS}\n")


def alert(score: float, cause: str) -> str:
    sustained = round(INTERVAL * TRIGGER_SAMPLES)
    body = (
        f"Performance mode activated at {score:.0f}% pressure ({cause}) after {sustained}s. "
        "Cancel only if you need full desktop effects during this workload."
    )
    command = [
        "notify-send",
        "--app-name=performance-pressure",
        "--urgency=critical",
        f"--expire-time={ALERT_SECONDS * 1000}",
        "--action=cancel=Restore effects for 10 min",
        "Performance mode enabled",
        body,
    ]
    try:
        result = subprocess.run(command, text=True, capture_output=True, check=False)
    except OSError:
        return "timeout"
    return result.stdout.strip() or "timeout"


class Sampler:
    def __init__(self) -> None:
        self.previous_cpu = cpu_counters()
        vmstat = read_fields("/proc/vmstat")
        self.previous_swap_pages = vmstat.get("pswpin", 0) + vmstat.get("pswpout", 0)
        self.previous_major_faults = vmstat.get("pgmajfault", 0)
        self.previous_time = time.monotonic()
        self.page_mib = os.sysconf("SC_PAGE_SIZE") / 1024 / 1024

    def sample(self) -> dict[str, float | str]:
        now = time.monotonic()
        elapsed = max(now - self.previous_time, 0.001)

        total, idle = cpu_counters()
        old_total, old_idle = self.previous_cpu
        total_delta = total - old_total
        cpu = 100.0 * (1.0 - (idle - old_idle) / total_delta) if total_delta > 0 else 0.0
        self.previous_cpu = (total, idle)

        memory = read_fields("/proc/meminfo")
        memory_total = memory.get("MemTotal", 0)
        memory_used = 100.0 * (1.0 - memory.get("MemAvailable", memory_total) / memory_total) if memory_total else 0.0

        vmstat = read_fields("/proc/vmstat")
        swap_pages = vmstat.get("pswpin", 0) + vmstat.get("pswpout", 0)
        swap_mib_s = max(0, swap_pages - self.previous_swap_pages) * self.page_mib / elapsed
        major_faults = vmstat.get("pgmajfault", 0)
        major_faults_s = max(0, major_faults - self.previous_major_faults) / elapsed
        self.previous_swap_pages = swap_pages
        self.previous_major_faults = major_faults
        self.previous_time = now

        metrics = {
            "CPU": max(0.0, min(cpu, 100.0)),
            "memory headroom": saturation_score(memory_used, 80.0, 98.0),
            "GPU": max(0.0, min(gpu_percent(), 100.0)),
            "I/O stall": saturation_score(pressure_average("io"), 0.0, 20.0),
            "memory stall": saturation_score(pressure_average("memory"), 0.0, 10.0),
            "swap churn": max(0.0, min(swap_mib_s / SWAP_FULL_SCALE_MIB_S * 100.0, 100.0)),
            "major faults": saturation_score(major_faults_s, 20.0, 500.0),
        }
        cause, score = max(metrics.items(), key=lambda item: item[1])
        return {"score": round(score, 1), "cause": cause, **{key: round(value, 1) for key, value in metrics.items()}}


def run_once() -> None:
    sampler = Sampler()
    time.sleep(min(INTERVAL, 1.0))
    print(json.dumps(sampler.sample(), sort_keys=True))


def monitor(simulated_score: float | None = None, simulated_cause: str = "test") -> None:
    sampler = Sampler()
    high_samples = 0
    recovery_samples = 0
    while True:
        time.sleep(INTERVAL)
        metrics = sampler.sample()
        score = simulated_score if simulated_score is not None else float(metrics["score"])
        cause = simulated_cause if simulated_score is not None else str(metrics["cause"])
        active, origin = mode_status()

        if active:
            high_samples = 0
            if origin == "auto" and score <= RECOVERY:
                recovery_samples += 1
                if recovery_samples >= RECOVERY_SAMPLES:
                    set_mode(False)
                    recovery_samples = 0
            else:
                recovery_samples = 0
            continue

        recovery_samples = 0
        if cancelled():
            high_samples = 0
            continue
        high_samples = high_samples + 1 if score >= TRIGGER else 0
        if high_samples < TRIGGER_SAMPLES:
            continue

        set_mode(True)
        action = alert(score, cause)
        high_samples = 0
        if action == "cancel":
            set_mode(False)
            cancel_for_cooldown()
        simulated_score = None


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="print one pressure sample and exit")
    parser.add_argument("--simulate", type=float, metavar="PERCENT", help="inject one sustained-pressure alert")
    parser.add_argument("--cause", default="test", help="label used with --simulate")
    args = parser.parse_args()
    if args.once:
        run_once()
    else:
        monitor(args.simulate, args.cause)


if __name__ == "__main__":
    main()
