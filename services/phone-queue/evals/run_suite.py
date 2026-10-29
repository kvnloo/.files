#!/usr/bin/env python3
"""android-u2-driver-models-v0 runner: dogfoods the phone queue.

It submits one `goal` job per (model x task x rep) to the phone-queue API, waits for each one,
and appends one row per job to rows.jsonl. It never touches the phone UI itself; the queue
service owns the UI lock, gating, uiautomator2 and the driver harness. The only phone access
here is an optional READ-ONLY settings snapshot (`adb shell settings list ...`) before and after
each job, to catch a wrong act that changed a setting (reported, never reverted).

  run_suite.py plan   [--models a,b] [--tasks x,y] [--reps 3]
  run_suite.py run    --out DIR [--api URL] [--models ...] [--tasks ...] [--reps 3] [--no-drift]
  run_suite.py probe  [--api URL]                 # availability of the queue, devices and models

Stdlib only. Resumable: rows already in DIR/rows.jsonl are skipped, and each job carries an
idempotency_key so a resubmission does not create a second job.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
SUITE = "android-u2-driver-models-v0"
DEFAULT_API = "http://100.113.138.100:8790"
TERMINAL = {"succeeded", "failed", "cancelled", "blocked"}
UNAVAILABLE_HINTS = ("model_unavailable", "unknown model", "unsupported model", "not available", "unauthorized",
                     "401", "403", "auth", "connection refused", "no such model", "model not found", "quota")
ABSTAIN_HINTS = ("abstain", "needs_confirmation", "uncertain", "escalat")
# Keys that move on their own; a change here is not evidence of a wrong act.
VOLATILE_SETTINGS = ("screen_brightness", "next_alarm", "wifi_", "bluetooth_", "boot_count", "time_", "_timestamp",
                     "last_", "battery", "lock_screen_", "doze", "aod_", "screen_off", "sem_", "edge_", "game_",
                     "mobile_data", "data_roaming", "cellular", "network_", "netstats", "ntp", "auto_time",
                     "multi_sim", "accessibility_enabled", "zen_", "volume_", "media_", "audio_", "usb_", "adb_", "stay_on", "power_")


def api_base(arg: str | None) -> str:
    return (arg or os.environ.get("PHONEQ_URL") or DEFAULT_API).rstrip("/")


def http(method: str, url: str, body: dict | None = None, timeout: float = 30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={"content-type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"null")
        except ValueError:
            return e.code, None


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text())


def select(items: list[dict], key: str, wanted: str | None) -> list[dict]:
    if not wanted:
        return items
    keep = set(wanted.split(","))
    return [i for i in items if i[key] in keep]


def plan(models: list[dict], tasks: list[dict], reps: int) -> list[tuple[dict, dict, int]]:
    # Model-major so each model's first job pays its cold load and later ones are warm.
    return [(m, t, r) for m in models for r in range(reps) for t in tasks]


def probe_model(m: dict) -> tuple[bool, str]:
    p = m.get("probe", {})
    try:
        if p.get("type") == "openai_models":
            with urllib.request.urlopen(p["url"], timeout=5) as r:
                ids = {x["id"] for x in json.load(r)["data"]}
            return (p["id"] in ids, "listed" if p["id"] in ids else f"{p['id']} not in {p['url']}")
        if p.get("type") == "ollama_tags":
            with urllib.request.urlopen(p["url"], timeout=5) as r:
                ids = {x["name"] for x in json.load(r)["models"]}
            return (p["id"] in ids, "listed" if p["id"] in ids else f"{p['id']} not in {p['url']}")
        if p.get("type") == "env":
            return (bool(os.environ.get(p["var"])), "key present" if os.environ.get(p["var"]) else f"{p['var']} unset")
        return True, "checked by the queue at run time"
    except Exception as e:  # noqa: BLE001 - any failure means unreachable
        return False, f"probe failed: {e.__class__.__name__}: {e}"[:200]


def router_loaded(m: dict) -> bool | None:
    """True/False when the groot router reports the model loaded/unloaded; None if unknown."""
    p = m.get("probe", {})
    if p.get("type") != "openai_models":
        return None
    try:
        with urllib.request.urlopen(p["url"], timeout=5) as r:
            for x in json.load(r)["data"]:
                if x["id"] == p["id"]:
                    return (x.get("status") or {}).get("value") == "loaded"
    except Exception:  # noqa: BLE001
        return None
    return None


def settings_snapshot(serial: str) -> dict | None:
    adb = shutil.which("adb") or os.path.expanduser("~/android/sdk/platform-tools/adb")
    if not os.path.exists(adb):
        return None
    snap = {}
    for ns in ("system", "secure", "global"):
        try:
            out = subprocess.run([adb, "-s", serial, "shell", "settings", "list", ns], capture_output=True,
                                 text=True, timeout=20).stdout
        except Exception:  # noqa: BLE001
            return None
        for line in out.splitlines():
            k, _, v = line.partition("=")
            if k and not any(h in k for h in VOLATILE_SETTINGS):
                snap[f"{ns}/{k}"] = v
    return snap or None


def drift(before: dict | None, after: dict | None) -> list[str] | None:
    if before is None or after is None:
        return None
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


def transcript_choose_ms(path: str | None) -> list[float]:
    """Per-decision latencies from the job transcript when it is readable here (JSON or JSONL with
    choose_ms / decision_ms / llm_ms per step). Empty when the format or file is unknown."""
    if not path or not os.path.exists(path):
        return []
    try:
        text = Path(path).read_text()
        try:
            doc = json.loads(text)
            steps = doc.get("steps", doc) if isinstance(doc, dict) else doc
        except ValueError:
            steps = [json.loads(line) for line in text.splitlines() if line.strip().startswith("{")]
        out = []
        for s in steps if isinstance(steps, list) else []:
            for k in ("choose_ms", "decision_ms", "llm_ms", "model_ms"):
                if isinstance(s, dict) and isinstance(s.get(k), (int, float)):
                    out.append(float(s[k]))
                    break
        return out
    except Exception:  # noqa: BLE001
        return []


def classify(job: dict | None, waited_out: bool) -> str:
    if waited_out:
        return "timeout"
    if not job:
        return "error"
    st = job.get("state")
    err = json.dumps(job.get("error") or "").lower()
    if st == "blocked":
        return "blocked"
    if st == "cancelled":
        return "cancelled"
    if st == "failed" and any(h in err for h in UNAVAILABLE_HINTS):
        return "unavailable"
    if st == "failed" and "timeout" in err and not (job.get("result") or {}).get("steps"):
        return "timeout"
    if st in ("succeeded", "failed") and job.get("result") is not None:
        return "ok"  # scored: the driver ran; the oracle decides success
    if st == "failed" and any(h in err for h in ABSTAIN_HINTS):
        return "ok"
    return "error"


def make_row(suite: dict, m: dict, t: dict, rep: int, run_id: str, job: dict | None, status: str,
             drift_keys: list[str] | None, cold_expected: bool | None, wall_ms: float) -> dict:
    res = (job or {}).get("result") or {}
    final = str(res.get("final_output") or "")
    err = json.dumps((job or {}).get("error") or "").lower()
    oracle = res.get("oracle_pass")
    abstain = status == "ok" and ("ABSTAIN" in final.upper() or any(h in err for h in ABSTAIN_HINTS))
    # wrong_act: the driver did something that left the phone in the wrong place while not abstaining
    # (a false "done"), or a non-volatile setting changed during the job.
    side_effect = bool(drift_keys)
    false_done = status == "ok" and oracle is False and not abstain and (job or {}).get("state") == "succeeded"
    choose = transcript_choose_ms(res.get("transcript_path"))
    return {
        "schema": "z0evals.android-u2-driver-models.row.v1", "suite": SUITE, "run_id": run_id,
        "model": m["job_model"], "model_key": m["key"], "class": m["class"], "params_b": m.get("params_b"),
        "quant": m.get("quant"), "endpoint": m.get("endpoint"), "task": t["id"], "rep": rep, "device": t["device"],
        "multi_step": t["multi_step"], "min_steps": t["min_steps_from_home"], "job_id": (job or {}).get("id"),
        "state": (job or {}).get("state"), "status": status,
        "oracle_pass": oracle if status == "ok" else None,
        "steps": res.get("steps"), "abstain": abstain if status == "ok" else None,
        "false_done": false_done if status == "ok" else None, "side_effect_keys": drift_keys,
        "wrong_act": (false_done or side_effect) if status == "ok" else (side_effect or None),
        "choose_ms": choose, "total_ms": res.get("ms"), "cold_ms": res.get("cold_ms"),
        "cold_expected": cold_expected, "tokens_in": res.get("tokens_in"), "tokens_out": res.get("tokens_out"),
        "cost_usd": res.get("cost_usd"), "runner_wall_ms": round(wall_ms),
        "created_at": (job or {}).get("created_at"), "started_at": (job or {}).get("started_at"),
        "finished_at": (job or {}).get("finished_at"), "transcript_path": res.get("transcript_path"),
        "error": (job or {}).get("error"),
    }


def submit_and_wait(base: str, body: dict, timeout_s: float, poll_s: float = 2.0) -> tuple[dict | None, bool]:
    code, resp = http("POST", f"{base}/v1/jobs", body)
    if code not in (200, 201, 202) or not resp or "id" not in resp:
        return {"state": "failed", "error": {"submit_http": code, "body": resp}}, False
    jid, deadline = resp["id"], time.time() + timeout_s
    job = resp
    while time.time() < deadline:
        code, job = http("GET", f"{base}/v1/jobs/{jid}")
        if code == 200 and job and job.get("state") in TERMINAL:
            return job, False
        time.sleep(poll_s)
    http("POST", f"{base}/v1/jobs/{jid}/cancel", {})
    return job if isinstance(job, dict) else {"id": jid}, True


def cmd_probe(a) -> int:
    base = api_base(a.api)
    out = {"api": base}
    try:
        out["healthz"] = http("GET", f"{base}/healthz", timeout=5)
        out["devices"] = http("GET", f"{base}/v1/devices", timeout=5)[1]
    except Exception as e:  # noqa: BLE001
        out["healthz"] = f"unreachable: {e}"
    out["models"] = {m["key"]: dict(zip(("available", "why"), probe_model(m))) for m in load("models.json")["models"]}
    print(json.dumps(out, indent=1))
    return 0


def cmd_plan(a) -> int:
    suite, models = load("tasks.json"), load("models.json")["models"]
    ms = select([m for m in models if not m.get("default_off") or a.models], "key", a.models)
    ts = select(suite["tasks"], "id", a.tasks)
    p = plan(ms, ts, a.reps)
    print(json.dumps({"models": [m["key"] for m in ms], "tasks": [t["id"] for t in ts], "reps": a.reps, "jobs": len(p)}))
    return 0


def cmd_run(a) -> int:
    base, out = api_base(a.api), Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    suite, models = load("tasks.json"), load("models.json")["models"]
    ms = select([m for m in models if not m.get("default_off") or a.models], "key", a.models)
    ts = select(suite["tasks"], "id", a.tasks)
    run_id = a.run_id or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    rows_path = out / "rows.jsonl"
    done = set()
    if rows_path.exists():
        for line in rows_path.read_text().splitlines():
            r = json.loads(line)
            if r["status"] in ("ok", "unavailable"):
                done.add((r["model_key"], r["task"], r["rep"]))
    serials = suite["device_profile"]
    meta = {"suite": SUITE, "run_id": run_id, "api": base, "started": time.strftime("%FT%TZ", time.gmtime()),
            "models": [m["key"] for m in ms], "tasks": [t["id"] for t in ts], "reps": a.reps,
            "drift_check": not a.no_drift, "host": os.uname().nodename}
    (out / f"run-{run_id}.json").write_text(json.dumps(meta, indent=1))
    unavailable: dict[str, str] = {}
    for m in ms:
        ok, why = probe_model(m)
        if not ok:
            unavailable[m["key"]] = why
    first_for_model: set[str] = set()
    with rows_path.open("a") as rows:
        for m, t, rep in plan(ms, ts, a.reps):
            if (m["key"], t["id"], rep) in done:
                continue
            if m["key"] in unavailable:
                row = make_row(suite, m, t, rep, run_id, None, "unavailable", None, None, 0)
                row["error"] = {"preflight": unavailable[m["key"]]}
                rows.write(json.dumps(row) + "\n"); rows.flush()
                continue
            cold_expected = None
            if m["key"] not in first_for_model:
                loaded = router_loaded(m)
                cold_expected = (loaded is False) if loaded is not None else None
                first_for_model.add(m["key"])
            body = {"kind": "goal", "device": t["device"], "app": t["app"],
                    "goal": f"{t['goal']} {suite['safety_suffix']}", "model": m["job_model"],
                    "harness": m.get("harness", a.harness), "max_steps": t["max_steps"], "oracle": t["oracle"],
                    "submitter": a.submitter, "reset": t["reset"], "priority": a.priority,
                    "idempotency_key": f"{SUITE}:{run_id}:{m['key']}:{t['id']}:{rep}"}
            serial = serials.get(t["device"], {}).get("serial")
            before = None if a.no_drift or not serial else settings_snapshot(serial)
            t0 = time.time()
            job, waited_out = submit_and_wait(base, body, timeout_s=max(a.min_timeout, t["max_steps"] * a.step_timeout))
            wall = (time.time() - t0) * 1000
            after = None if a.no_drift or not serial else settings_snapshot(serial)
            status = classify(job, waited_out)
            row = make_row(suite, m, t, rep, run_id, job, status, drift(before, after), cold_expected, wall)
            rows.write(json.dumps(row) + "\n"); rows.flush()
            print(json.dumps({k: row[k] for k in ("model_key", "task", "rep", "status", "oracle_pass", "steps", "total_ms")}), flush=True)
            if row["side_effect_keys"]:
                print(f"WARNING: settings changed during {row['job_id']}: {row['side_effect_keys']} (not reverted; tell the owner)",
                      file=sys.stderr, flush=True)
                if not a.continue_on_side_effect:
                    return 3
            if status == "unavailable":
                unavailable[m["key"]] = json.dumps(row["error"])[:200]
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("plan", "run", "probe"):
        s = sub.add_parser(name)
        s.add_argument("--api")
        s.add_argument("--models")
        s.add_argument("--tasks")
        s.add_argument("--reps", type=int, default=3)
    r = sub.choices["run"]
    r.add_argument("--out", required=True)
    r.add_argument("--run-id")
    r.add_argument("--submitter", default="z0evals:android-u2-driver-models-v0")
    r.add_argument("--harness", default="fx", choices=("fx", "script"))
    r.add_argument("--priority", type=int, default=0)
    r.add_argument("--no-drift", action="store_true")
    r.add_argument("--continue-on-side-effect", action="store_true", help="default: stop the run when a setting changed")
    r.add_argument("--min-timeout", type=float, default=300)
    r.add_argument("--step-timeout", type=float, default=45)
    a = ap.parse_args(argv)
    return {"plan": cmd_plan, "run": cmd_run, "probe": cmd_probe}[a.cmd](a)


if __name__ == "__main__":
    sys.exit(main())
