#!/usr/bin/env python3
"""Correlate Proton monitor metadata with exported approvals. Output counts only."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
import math
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys


REASON = re.compile(r"^passd\s+capability=([\w.:-]+)\s+lease=([\w.:-]+)(?:\s+.*)?$", re.S)
ALERT = "passd agent access alert; inspect custody-side audit metadata."
ERROR = "passd agent monitor collection failed; no subprocess output is disclosed."
ACTIONS = frozenset("read view reveal copy use access get decrypt update create delete autofill totp password".split())


def field(row, *keys):
    normalized = {re.sub(r"[_\s-]", "", str(k)).lower(): value for k, value in row.items()}
    return next((normalized[key.replace("_", "").lower()] for key in keys
                 if key.replace("_", "").lower() in normalized), None)


def identifier(value):
    if isinstance(value, dict):
        value = field(value, "id", "item_id", "agent_id")
    return str(value) if isinstance(value, (str, int)) and not isinstance(value, bool) else None


def timestamp(value):
    if isinstance(value, bool) or value is None:
        raise ValueError("missing time")
    try:
        number = float(value)
    except (TypeError, ValueError):
        date = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if date.tzinfo is None:
            raise ValueError("time requires zone")
        number = date.timestamp()
    if not math.isfinite(number):
        raise ValueError("invalid time")
    return number / 1000 if number > 100_000_000_000 else number


def records(payload):
    if isinstance(payload, list) and all(isinstance(row, dict) for row in payload):
        return payload
    if isinstance(payload, dict):
        for key in ("events", "data", "results", "logs", "items"):
            if key in payload:
                return records(payload[key])
    raise ValueError("unrecognized monitor schema")


def load_leases(path):
    """Canonical JSONL approvals or native audit rows enriched with exact validity."""
    rows = []
    with Path(path).expanduser().open(encoding="utf-8") as stream:
        for line in stream:
            if line.strip():
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("invalid audit row")
                rows.append(row)
    leases, revocations = {}, {}
    for row in rows:
        detail = row.get("detail", {})
        if not isinstance(detail, dict):
            raise ValueError("invalid audit detail")
        lease_id = identifier(field(row, "lease_id") or field(detail, "lease_id", "request_id"))
        operation = field(row, "operation", "action")
        if operation == "access.revoke":
            if not lease_id:
                raise ValueError("missing revoked lease id")
            when = timestamp(field(row, "ts", "time", "timestamp"))
            revocations[lease_id] = min(when, revocations.get(lease_id, when))
            continue
        approved = row.get("status") == "approved" or (operation == "access.approve" and row.get("allowed") is True)
        if not approved:
            continue
        if not lease_id:
            raise ValueError("missing approved lease id")
        start = timestamp(field(row, "approved_at", "reviewed_at"))
        end = timestamp(field(row, "expires_at", "valid_until"))
        if not math.isfinite(end) or end <= start:
            raise ValueError("invalid lease interval")
        lease = {"start": start, "end": end,
                 "item": identifier(field(row, "item_id", "item")),
                 "capability": identifier(field(row, "capability_id") or field(detail, "capability_id")),
                 "agent": identifier(field(row, "proton_agent"))}
        revoked = field(row, "revoked_at")
        if revoked is not None:
            lease["end"] = min(end, timestamp(revoked))
        if lease_id in leases and leases[lease_id] != lease:
            raise ValueError("conflicting approval rows")
        leases[lease_id] = lease
    for lease_id, when in revocations.items():
        if lease_id in leases:
            leases[lease_id]["end"] = min(leases[lease_id]["end"], when)
    return leases


def summarize(events, leases, known_agents):
    totals = Counter(events=len(events), flagged_events=0)
    per_item = defaultdict(Counter)
    per_event = []
    for event in events:
        flags = Counter()
        item = identifier(field(event, "item_id", "item"))
        agent = identifier(field(event, "agent_id", "agent", "agent_name"))
        action = field(event, "action", "event", "type")
        # Hash identifiers and allowlist action labels; never emit arbitrary upstream text.
        bucket = hashlib.sha256(item.encode()).hexdigest() if item else "unknown"
        action = action.lower() if isinstance(action, str) else "unknown"
        per_item[bucket][action if action in ACTIONS else "other"] += 1
        if not item:
            flags["missing_item"] += 1
        if agent not in known_agents:
            flags["unknown_agent"] += 1
        try:
            when = timestamp(field(event, "time", "create_time", "timestamp", "created_at", "ts"))
        except (ValueError, TypeError, OverflowError):
            when = None
            flags["invalid_time"] += 1
        reason = field(event, "reason")
        match = REASON.fullmatch(reason.strip()) if isinstance(reason, str) else None
        if not match:
            flags["unstructured_reason"] += 1
        else:
            capability, lease_id = match.groups()
            lease = leases.get(lease_id)
            if lease is None:
                flags["no_approved_lease"] += 1
            else:
                if when is not None and not lease["start"] <= when < lease["end"]:
                    flags["outside_lease_validity"] += 1
                if lease["capability"] is not None and capability != lease["capability"]:
                    flags["capability_mismatch"] += 1
                if lease["item"] is not None and item != lease["item"]:
                    flags["item_mismatch"] += 1
                if lease["agent"] is not None and agent != lease["agent"]:
                    flags["lease_agent_mismatch"] += 1
        if flags:
            totals["flagged_events"] += 1
        totals.update(flags)
        # One entry per event, in input order. Every value is a count, never event content.
        per_event.append(dict(flags))
    return {"counts": dict(totals), "per_item_action_counts": dict(per_item), "event_flag_counts": per_event}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--agent", required=True, help="Proton AGENT to monitor")
    parser.add_argument("--known-agent", action="append", required=True, help="accepted Proton agent ID/name; repeatable")
    parser.add_argument("--session-dir", required=True, help="passd user's Proton AGENT session directory")
    parser.add_argument("--audit-jsonl", required=True, help="custody-side approval metadata export")
    parser.add_argument("--pass-cli", default="pass-cli", help="binary path; fixtures use a fake executable")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--timeout", type=float, default=20)
    parser.add_argument("--notify", action="store_true", help="send a static notify-send alert")
    parser.add_argument("--alert-command", help="argv parsed with shlex, no shell; receives a static message argument")
    args = parser.parse_args(argv)
    if args.limit < 1 or args.timeout <= 0 or not math.isfinite(args.timeout):
        parser.error("limit and timeout must be positive")
    failed = False
    try:
        env = dict(os.environ, PROTON_PASS_SESSION_DIR=str(Path(args.session_dir).expanduser()))
        result = subprocess.run([args.pass_cli, "agent", "monitor", args.agent, "--output", "json", "--limit", str(args.limit)],
                                env=env, capture_output=True, text=True, timeout=args.timeout, check=False)
        if result.returncode:
            raise ValueError("monitor failed")
        events = records(json.loads(result.stdout))
        summary = summarize(events, load_leases(args.audit_jsonl), set(args.known_agent))
        if len(events) >= args.limit:
            summary["counts"]["possibly_truncated_window"] = 1
        failed = bool(summary["counts"]["flagged_events"] or summary["counts"].get("possibly_truncated_window"))
    except (OSError, ValueError, TypeError, KeyError, OverflowError, RecursionError, subprocess.SubprocessError):
        summary = {"counts": {"collection_errors": 1}}
        failed = True
        print(ERROR, file=sys.stderr)
    print(json.dumps(summary, sort_keys=True))
    if failed:
        print(ALERT, file=sys.stderr)
        commands = []
        if args.notify:
            commands.append(["notify-send", "passd agent alert", ALERT])
        if args.alert_command:
            try:
                commands.append(shlex.split(args.alert_command) + [ALERT])
            except ValueError:
                print("Alert command configuration failed.", file=sys.stderr)
        for command in commands:
            try:
                subprocess.run(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                               stderr=subprocess.DEVNULL, timeout=5, check=True)
            except (OSError, subprocess.SubprocessError):
                print("Alert delivery failed.", file=sys.stderr)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
