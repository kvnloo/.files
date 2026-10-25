"""Controller transport for phone execution; invoked by existing fleet placement/health."""
import json

import shlex
import subprocess
import time
from typing import Any

from fleet_phone import Blocked, atomic, host_health, identifier, lock, read

REMOTE = "~/.local/lib/fleet/fleet-phone-worker"
TERMINAL = {"succeeded", "failed", "cancelled", "needs-confirmation"}


def strict_ssh(ssh):
    # OpenSSH uses the FIRST obtained value, so policy precedes generic options.
    return [ssh[0], "-o", "StrictHostKeyChecking=yes", "-o", "ControlMaster=no",
            "-o", "ControlPath=none", *ssh[1:]]


def transport(ssh, command, jid=None, payload=None) -> Any:
    argv = strict_ssh(ssh)
    remote = f"python3 {REMOTE} {shlex.quote(command)}"
    if jid:
        remote += " " + shlex.quote(identifier(jid))
    if command in ("submit", "lease", "heartbeat"):
        remote += " --ttl 300"
    try:
        proc = subprocess.run(argv + [remote], input=json.dumps(payload) if payload is not None else "",
                              text=True, capture_output=True, timeout=50)
    except (OSError, subprocess.TimeoutExpired):
        raise Blocked("unavailable: SSH transport timeout/error") from None
    if proc.returncode:
        raise Blocked("unavailable or blocked: strict SSH/guest API failed")
    if command == "logs":
        return proc.stdout
    try:
        value = json.loads(proc.stdout)
        if not isinstance(value, dict):
            raise ValueError("object required")
        return value
    except ValueError:
        raise Blocked("unavailable: invalid guest response") from None


def records(state, node):
    directory = state / "phone-jobs" / identifier(node)
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    return directory


def update_record(path, changes):
    with lock(path.with_suffix(".lock")):
        prior = read(path, {})
        # Stop/cancel is monotonic; concurrent status/health writers cannot erase it.
        value = {**prior, **changes}
        if prior.get("cancel"):
            value["cancel"] = True
        if prior.get("terminal"):
            value["terminal"] = True
        atomic(path, value)
        return value


def cancel(state, node, jid, ssh):
    path = records(state, node) / f"{identifier(jid)}.json"
    update_record(path, {"id": jid, "node": node, "cancel": True})
    try:
        result = transport(ssh, "cancel", jid)
        update_record(path, {"state": result["state"], "terminal": result["state"] in TERMINAL})
        return result
    except Blocked:
        return {"id": jid, "state": "cancel-pending", "availability": "unavailable"}


def reconcile(state, node, probe, ssh):
    phase, reasons = host_health(probe)
    directory = records(state, node)
    outcomes = []
    for path in directory.glob("*.json"):
        record = read(path, {})
        if record.get("terminal"):
            continue
        if phase != "ready" and not (record.get("cancel") and phase == "paused"):
            update_record(path, {"availability": phase, "reasons": reasons, "checked": time.time()})
            continue
        try:
            if record.get("cancel"):
                job = transport(ssh, "cancel", record["id"])
            else:
                job = transport(ssh, "recover", record["id"])
                if job["state"] == "queued":
                    leased = transport(ssh, "lease", record["id"])
                    record["lease"] = leased["lease"]
                if job["state"] in ("queued", "running", "starting"):
                    if "lease" not in record:
                        # Submit may have succeeded before its response was lost. Re-submit
                        # only identical durable spec to recover the original token/ID.
                        if "spec" not in record:
                            raise Blocked("missing owned lease/spec; explicit reconciliation required")
                        submitted = transport(ssh, "submit", record["id"], record["spec"])
                        record["lease"] = submitted["lease"]
                    transport(ssh, "heartbeat", record["id"], {"lease": record["lease"]})
            record.update(availability="ready", state=job["state"], checked=time.time(), terminal=job["state"] in TERMINAL)
        except Blocked:
            record.update(availability="unavailable", checked=time.time())
        record = update_record(path, record)
        outcomes.append({"id": record["id"], "state": record.get("state"), "availability": record["availability"]})
    return {"state": phase, "reasons": reasons, "jobs": outcomes}


def run(state, node, jid, spec, ssh, output):
    path = records(state, node) / f"{identifier(jid)}.json"
    record = update_record(path, {"id": jid, "node": node, "spec": spec, "state": "submitting", "terminal": False})
    try:
        job = transport(ssh, "submit", jid, spec)
        record = update_record(path, {"state": job["state"], "lease": job["lease"]})
        printed = 0
        while True:
            record = read(path, {})
            if record.get("cancel"):
                transport(ssh, "cancel", jid)
            job = transport(ssh, "status", jid)
            if job["state"] not in TERMINAL:
                try:
                    if job["state"] == "queued" and job.get("expires", 0) <= time.time():
                        leased = transport(ssh, "lease", jid)
                        record = update_record(path, {"lease": leased["lease"]})
                    transport(ssh, "heartbeat", jid, {"lease": record["lease"]})
                except Blocked:
                    # Completion can race either lease operation. Reconcile only
                    # read-only terminal evidence, never resubmit/replay the job.
                    job = transport(ssh, "status", jid)
                    if job["state"] not in TERMINAL:
                        raise
            logs = transport(ssh, "logs", jid)
            if len(logs) >= printed:
                output(logs[printed:])
                printed = len(logs)
            terminal = job["state"] in TERMINAL
            result = job.get("exit")
            exit_code = 128 - result if isinstance(result, int) and result < 0 else result
            termination_reason = job.get("reason")
            if exit_code == 137 and not termination_reason:
                termination_reason = "SIGKILL/exit137; possible OOM, not confirmed by guest"
            record = update_record(path, {"state": job["state"], "checked": time.time(), "availability": "ready",
                                          "terminal": terminal, "exit": exit_code,
                                          "termination_reason": termination_reason})
            if terminal:
                return 0 if job["state"] == "succeeded" else exit_code if job["state"] == "failed" and exit_code is not None else 255
            time.sleep(5)  # measured job status, never lifecycle survival
    except Blocked:
        update_record(path, {"availability": "unavailable", "checked": time.time()})
        return 255  # retain spool and ID, never speculative relocate/retry
