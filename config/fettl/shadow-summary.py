#!/usr/bin/env python3
"""Summarize private Fettl logs without scanning source or calling a model."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import json
import math
import os
from pathlib import Path


def summarize(directory, since):
    scans = defaultdict(dict)
    rules = defaultdict(Counter)
    excluded = 0
    for path in directory.glob("*.jsonl"):
        for line in path.read_text().splitlines():
            try:
                row = json.loads(line)
                stamp = datetime.fromisoformat(row["time"])
            except (ValueError, KeyError, TypeError):
                continue
            if stamp < since:
                continue
            cwd = row.get("cwd", "")
            # Synthetic bridge probes predate provenance fields. Controlled
            # fixture sessions use the same explicit fettl-prefixed directories.
            if not cwd or "fettl-shadow-probe-" in cwd or "fettl-agent-eval" in cwd or "fettl-eval" in cwd:
                excluded += 1
                continue
            agent = row["agent"]
            scans[agent][row.get("scan_id", row["time"])] = row
            if row.get("rule"):
                rules[agent][row["rule"]] += 1
    now = datetime.now(timezone.utc)
    agents = {}
    for agent, records in sorted(scans.items()):
        values = sorted(row["latency_ms"] for row in records.values())
        agents[agent] = {
            "scans": len(values),
            "p50_ms": values[math.ceil(len(values) * .50) - 1],
            "p95_ms": values[math.ceil(len(values) * .95) - 1],
            "scanner_errors": sum(row["exit_code"] not in (0, 1) or bool(row.get("diagnostic")) for row in records.values()),
            "findings_per_rule": dict(rules[agent]),
        }
    return {
        "generated_at": now.isoformat(), "since": since.isoformat(),
        "window_complete": now >= since + timedelta(hours=24),
        "excluded_fixture_or_unattributed_rows": excluded,
        "agents": agents,
        "note": "Finding counts are observations, not unique bugs or accuracy labels. No findings is not proof that a hook was active. Enforcement remains unchanged.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--since", required=True, type=datetime.fromisoformat)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--logs", type=Path, default=Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "fettl-shadow")
    args = parser.parse_args()
    if args.since.tzinfo is None:
        parser.error("--since must include a timezone")
    os.umask(0o077)
    report = summarize(args.logs, args.since)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    temporary = args.output.with_suffix(args.output.suffix + ".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n")
    temporary.replace(args.output)
