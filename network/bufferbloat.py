#!/usr/bin/env python3
"""Run Ookla's native throughput and latency-under-load measurement."""

from __future__ import annotations

import argparse
import json
import subprocess
from pathlib import Path

from rich.console import Console
from rich.table import Table


CONSOLE = Console()
ROOT = Path(__file__).resolve().parents[1]
SPEEDTEST = ROOT / ".local/network-tools/speedtest"


def default_interface() -> str:
    route = subprocess.run(
        ["ip", "-json", "route", "get", "1.1.1.1"],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(route.stdout)[0]["dev"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interface", help="network interface; defaults to the Internet route")
    parser.add_argument("--json", action="store_true", help="also print the native result JSON")
    args = parser.parse_args()

    if not SPEEDTEST.exists():
        raise SystemExit(
            "Missing native Ookla client at .local/network-tools/speedtest; "
            "see network/README.md"
        )

    interface = args.interface or default_interface()
    completed = subprocess.run(
        [
            str(SPEEDTEST),
            "--accept-license",
            "--accept-gdpr",
            "--progress=no",
            "--format=json",
            f"--interface={interface}",
        ],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    if completed.returncode != 0:
        raise SystemExit(completed.stderr.strip() or completed.stdout.strip())

    result = json.loads(completed.stdout.strip().splitlines()[-1])
    idle = result["ping"]["latency"]
    download_latency = result["download"]["latency"]
    upload_latency = result["upload"]["latency"]

    table = Table(title=f"Internet responsiveness via {interface}")
    table.add_column("Phase")
    table.add_column("Throughput", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Added", justify="right")
    table.add_column("Peak", justify="right")
    table.add_row("Idle", "—", f"{idle:.1f} ms", "—", f"{result['ping']['high']:.1f} ms")
    table.add_row(
        "Download",
        f"{result['download']['bandwidth'] * 8 / 1_000_000:.1f} Mbps",
        f"{download_latency['iqm']:.1f} ms",
        f"{download_latency['iqm'] - idle:+.1f} ms",
        f"{download_latency['high']:.1f} ms",
    )
    table.add_row(
        "Upload",
        f"{result['upload']['bandwidth'] * 8 / 1_000_000:.1f} Mbps",
        f"{upload_latency['iqm']:.1f} ms",
        f"{upload_latency['iqm'] - idle:+.1f} ms",
        f"{upload_latency['high']:.1f} ms",
    )
    CONSOLE.print(table)
    CONSOLE.print(
        f"Server: {result['server']['sponsor']} — {result['server']['location']}  "
        f"Loss: {result.get('packetLoss', 0):.1f}%"
    )
    if args.json:
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
