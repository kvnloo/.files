#!/usr/bin/env python3
"""Explicit local lightweight service verification, not a build or production crash."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(sys.argv[1])
CONFIG = Path(sys.argv[2])
os.umask(0o077)
OUT.mkdir(mode=0o700, parents=True, exist_ok=True)
results = []
for phase in ("runtime", "bridge", "correlation"):
    unit = f"dash-log-watch-fixture-{phase}-{time.time_ns()}"
    subprocess.run(["systemd-run", "--user", "--unit=" + unit, "--wait", "--collect",
                    "--property=StandardOutput=journal", sys.executable,
                    str(ROOT / "tests/fixtures/dash_log_watch_journal_emitter.py"), phase],
                   check=True, timeout=20, capture_output=True)
    # Journald synchronization is event-driven via the synchronous user service exit and journal sync.
    subprocess.run(["journalctl", "--sync"], timeout=10, capture_output=True)
    journal = subprocess.check_output(["journalctl", "--user", "-u", unit + ".service", "-o", "json",
        "--no-pager", "--output-fields=MESSAGE,_SYSTEMD_USER_UNIT,__CURSOR,__REALTIME_TIMESTAMP"], text=True, timeout=10)
    records = [json.loads(line) for line in journal.splitlines() if line.strip()]
    records = [record for record in records if record.get("MESSAGE", "").startswith("FIXTURE_")]
    if not records:
        raise RuntimeError("Owned journal fixture missing")
    fixture = OUT / (phase + "-journal.jsonl")
    fixture.write_text("\n".join(json.dumps(r, sort_keys=True) for r in records) + "\n")
    state = OUT / (phase + "-state")
    subprocess.run([sys.executable, str(ROOT / "scripts/dash-log-watch.py"), "replay", "--config", str(CONFIG),
                    "--state", str(state), "--journal-file", str(fixture)], check=True, timeout=55)
    status = json.loads((state / "status.json").read_text())
    incidents = [json.loads(path.read_text()) for path in (state / "incidents").glob("*.json")]
    assert status["counts"]["model_calls"] == 1, status
    assert len(incidents) == 1, incidents
    incident = incidents[0]
    assert incident["seat"] == phase and incident["fixture"] is True, incident
    assert incident["result"]["ok"] and incident["result"]["returned_model"] == "gpt-6-luna", incident
    assert incident["result"]["provider"] == "openai-codex", incident
    assert all(e["cursor"] and e["evidence_sha256"] for e in incident["evidence"]), incident
    results.append({"phase": phase, "unit": unit + ".service", "journal_entries": len(records),
                    "status": status, "incident": incident})
    (OUT / "exercise-results.json").write_text(json.dumps(results, indent=2))
    print(json.dumps({"phase": phase, "model_calls": 1, "returned_model": "gpt-6-luna", "fixture": True}), flush=True)
print("DASH_LOG_WATCH_OWNED_JOURNAL_REPLAY_OK")
