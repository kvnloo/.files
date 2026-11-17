#!/usr/bin/env python3
"""Read local update history; never refresh databases, install packages or reboot."""
import argparse
from datetime import datetime
import json
from pathlib import Path
import re
import statistics

# Headers follow their kernels. Libraries may need process restarts rather than
# reboot, but belong in the same complete maintenance transaction on this host.
PACKAGES = {
    "linux-cachyos": "reboot: kernel",
    "linux-cachyos-lts": "reboot: fallback kernel",
    "linux-cachyos-nvidia-open": "reboot: loaded GPU module",
    "nvidia-utils": "maintenance: GPU userspace/module consistency",
    "intel-ucode": "reboot: early CPU microcode",
    "linux-firmware": "maintenance: device firmware reload",
    "systemd": "maintenance: init and running services",
    "glibc": "maintenance: long-lived processes",
}


def summarize(text):
    dates = {name: set() for name in PACKAGES}
    for line in text.splitlines():
        match = re.match(r"\[(.*?)\] \[ALPM\] upgraded (\S+) ", line)
        if match and match[2] in dates:
            dates[match[2]].add(datetime.fromisoformat(match[1]).date())
    rows = []
    for name, days in dates.items():
        ordered = sorted(days)
        intervals = [(b - a).days for a, b in zip(ordered, ordered[1:])]
        rows.append({"package": name, "handling": PACKAGES[name],
                     "observed_upgrade_days": len(ordered),
                     "last_local_upgrade": str(ordered[-1]) if ordered else None,
                     "median_local_interval_days": statistics.median(intervals) if intervals else None})
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=Path("/var/log/pacman.log"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    report = {"caveat": "Local install cadence is not upstream publication cadence.",
              "policy": "Weekly maintenance opportunity; skip when busy; never force reboot or partial upgrades.",
              "packages": summarize(args.log.read_text())}
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(report["caveat"])
        for row in report["packages"]:
            print(f'{row["package"]}: last={row["last_local_upgrade"]}, local median={row["median_local_interval_days"]} days; {row["handling"]}')
        print("\nSync database timestamps (not refreshed by this audit):")
        for path in sorted(Path("/var/lib/pacman/sync").glob("*.db")):
            print(datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds"), path.name)
        print("\n" + report["policy"])


if __name__ == "__main__":
    main()
