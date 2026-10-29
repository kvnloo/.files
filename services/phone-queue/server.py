#!/usr/bin/env python3
"""phone-queue front door: HTTP API + SQLite state + reconciler that turns jobs into
Kueue-admitted Kubernetes Jobs (one z0.dev/phone slot per phone; Kueue queues the rest).

API (docs/fleet/phone-queue.md):
  POST /v1/jobs                 submit (idempotent per submitter+idempotency_key) -> 202 {id, state}
  GET  /v1/jobs/{id}            job + result
  GET  /v1/jobs?submitter=&state=&limit=
  POST /v1/jobs/{id}/cancel
  GET  /v1/devices              serial, online, gate, lock holder, foreground, battery, queue depth
  GET  /healthz

Auth (docs/fleet/phone-queue.md#auth): writes (submit, cancel) need `Authorization: Bearer
<token>`; tokens are issued by services/phone-queue/issue-tokens into Secret phone-queue-auth
(sha256 of each token -> principal). Cancel needs the job's principal AND submitter, or an
admin token. Unauthenticated reads (Dash's read-only queue view) get devices and job metadata
but never job results (screen text, replies, transcripts paths) and never free-form errors:
an unauthenticated `error` is only an infrastructure/gate message from PUBLIC_ERROR or the
error_code.
"""
import hashlib
import http.server
import json
import os
import re
import signal
import socketserver
import sqlite3
import sys
import threading
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import common  # noqa: E402

BINDS = [b for b in os.environ.get("PHONEQ_BINDS", "127.0.0.1,100.113.138.100").split(",") if b]
IMAGE = os.environ.get("PHONEQ_IMAGE", "python:3.13.13-slim-trixie")
CODE_CM = os.environ.get("PHONEQ_CODE_CONFIGMAP", "phone-queue-code")
TICK_S = 2.0
GATE_TTL_S = 15
BLOCKED_RETRY_S = 30
MAX_ATTEMPTS = 50
KINDS = ("chat", "goal")
HARNESSES = ("fx", "script")
STATES = ("queued", "admitted", "running", "succeeded", "failed", "cancelled", "blocked")

DB_LOCK = threading.RLock()


def db():
    common.STATE.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(common.STATE / "phoneq.db", check_same_thread=False, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("""CREATE TABLE IF NOT EXISTS jobs (
        id TEXT PRIMARY KEY, submitter TEXT NOT NULL, idem TEXT, kind TEXT NOT NULL, device TEXT NOT NULL,
        app TEXT, prompt TEXT, goal TEXT, model TEXT NOT NULL, harness TEXT NOT NULL, max_steps INTEGER,
        oracle TEXT, priority INTEGER DEFAULT 0, reset TEXT, state TEXT NOT NULL, assigned TEXT,
        k8s_job TEXT, attempts INTEGER DEFAULT 0, created_at TEXT NOT NULL, admitted_at TEXT,
        started_at TEXT, finished_at TEXT, result TEXT, error TEXT, info TEXT, next_try REAL DEFAULT 0,
        UNIQUE(submitter, idem))""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)")}
    if "principal" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN principal TEXT")
    if "gate_blocks" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN gate_blocks INTEGER DEFAULT 0")
    if "body_hash" not in cols:
        conn.execute("ALTER TABLE jobs ADD COLUMN body_hash TEXT")
    return conn


CONN = None


def q(sql, args=()):
    with DB_LOCK:
        return CONN.execute(sql, args).fetchall()


LIVE = " AND state NOT IN ('succeeded','failed','cancelled')"


def qlive(sql, args=()):
    """UPDATE ... WHERE id=? that never overwrites a terminal row (a cancel that lands between
    the reconciler's snapshot and its write wins). Returns the number of rows changed."""
    with DB_LOCK:
        return CONN.execute(sql + LIVE, args).rowcount


# ------------------------------------------------------------------ auth
_tokens = {"mtime": None, "map": {}}


def tokens():
    path = common.AUTH_DIR / "tokens.json"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return {}
    if mtime != _tokens["mtime"]:
        _tokens.update(mtime=mtime, map=common.read_json(path, {}) or {})
    return _tokens["map"]


def who(headers):
    """{'principal', 'admin'} for a valid bearer token, else None."""
    auth = headers.get("authorization") or ""
    if not auth.lower().startswith("bearer "):
        return None
    digest = hashlib.sha256(auth[7:].strip().encode()).hexdigest()
    ent = tokens().get(digest)
    return {"principal": ent.get("principal"), "admin": bool(ent.get("admin"))} if isinstance(ent, dict) else None


PUBLIC_RESULT = ("steps", "oracle_pass", "ms", "cold_ms", "error_code", "device", "attempt")


def row_to_job(r, full=True):
    out = {k: r[k] for k in ("id", "kind", "device", "state", "submitter", "model", "harness", "app",
                             "created_at", "started_at", "finished_at")}
    out["assigned_device"] = r["assigned"]
    out["admitted_at"] = r["admitted_at"]
    out["priority"] = r["priority"]
    out["attempts"] = r["attempts"]
    out["k8s_job"] = r["k8s_job"]
    if r["idem"]:
        out["idempotency_key"] = r["idem"]
    if r["result"]:
        res = json.loads(r["result"])
        # Without a token: outcome only, never what was on the screen or in the reply.
        out["result"] = res if full else {k: res[k] for k in PUBLIC_RESULT if k in res}
    if not full:
        out["result_redacted"] = True
    if r["error"]:
        out["error"] = r["error"] if full else public_error(r)
    if r["info"]:
        out["info"] = r["info"] if full else public_info(r["info"])
    return out


# Errors the service itself writes (gates, locks, pacing, infra, models): safe to show anyone.
# Anything else (fx agent output, pod log tails, exception text near screen data) needs a token.
PUBLIC_ERROR = re.compile(
    r"^(gate closed — |gate s2[25]( \(under lock\))?: |infra: |model_unavailable: |"
    r"ChatGPT shared quota pause|ChatGPT send budget|DeepSeek quota pause|"
    r"/(home/kvn/)?tmp/s2[25]-ui\.lock busy|owner busy: |cancelled by |terminated by signal )")


def public_error(r):
    err = r["error"] or ""
    first = err.splitlines()[0][:300] if err else ""
    if PUBLIC_ERROR.match(first):
        return first
    code = None
    if r["result"]:
        try:
            code = json.loads(r["result"]).get("error_code")
        except ValueError:
            code = None
    return f"{code or r['state']} (details need a token)"


def public_info(info):
    return info if re.match(r"^(k8s Job created|adopted existing k8s Job|kueue: |admitted|running)", info) \
        else "(details need a token)"


# ------------------------------------------------------------------ validation
class Bad(Exception):
    pass


def validate(body):
    if not isinstance(body, dict):
        raise Bad("body must be a JSON object")
    kind = body.get("kind")
    if kind not in KINDS:
        raise Bad("kind must be chat or goal")
    device = body.get("device", "any")
    if device not in ("s22", "s25", "any"):
        raise Bad("device must be s22, s25 or any")
    sub = body.get("submitter")
    if not isinstance(sub, str) or not re.fullmatch(r"[\w.@:/+-]{1,80}", sub):
        raise Bad("submitter is required ([\\w.@:/+-], <= 80 chars)")
    harness = body.get("harness") or ("script" if kind == "chat" else "fx")
    if harness not in HARNESSES:
        raise Bad("harness must be fx or script")
    if kind == "goal" and harness != "fx":
        raise Bad("goal jobs run on harness fx")
    app = body.get("app")
    if kind == "chat":
        app = app or "chatgpt"
        prompt = body.get("prompt")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 20000:
            raise Bad("chat needs prompt (1..20000 chars)")
        if harness == "script" and app not in ("chatgpt", "deepseek"):
            raise Bad("harness script drives chatgpt or deepseek; use harness fx for other apps")
        if app == "deepseek" and device == "s25":
            raise Bad("the DeepSeek driver is S22-only")
    else:
        goal = body.get("goal")
        if not isinstance(goal, str) or not goal.strip() or len(goal) > 8000:
            raise Bad("goal needs goal (1..8000 chars)")
        attach = body.get("prompt")  # optional text the agent types by reference (from_job_prompt)
        if attach is not None and (not isinstance(attach, str) or not attach or len(attach) > 20000):
            raise Bad("goal prompt (attachment) must be a string (1..20000 chars)")
    if app is not None and app not in common.APPS and not re.fullmatch(r"[A-Za-z][\w]*(\.[\w]+)+", app):
        raise Bad("app must be chatgpt, deepseek or an Android package name")
    model = body.get("model") or common.DEFAULT_MODEL
    if not re.fullmatch(r"(openai-codex|groot-router|local|ollama|gateway)/[\w.:/-]{1,120}", model):
        raise Bad("model must be openai-codex/<slug>, groot-router/<id>, local/<name>, ollama/<name> or gateway/<id>")
    max_steps = body.get("max_steps", 30)
    if not isinstance(max_steps, int) or not 1 <= max_steps <= 200:
        raise Bad("max_steps must be an integer 1..200")
    oracle = body.get("oracle")
    if oracle is not None:
        if not isinstance(oracle, dict) or oracle.get("type", "tree_text") != "tree_text":
            raise Bad("oracle.type must be tree_text")
        unknown = set(oracle) - {"type", "must_contain", "must_not_contain", "final_must_contain", "package"}
        if unknown:
            raise Bad(f"unknown oracle keys: {sorted(unknown)}")
        for k in ("must_contain", "must_not_contain", "final_must_contain"):
            v = oracle.get(k, [])
            if not isinstance(v, list) or not all(isinstance(s, str) and s for s in v):
                raise Bad(f"oracle.{k} must be a list of non-empty strings")
    idem = body.get("idempotency_key")
    if idem is not None and (not isinstance(idem, str) or not 1 <= len(idem) <= 200):
        raise Bad("idempotency_key must be a string (1..200)")
    priority = body.get("priority", 0)
    if not isinstance(priority, int):
        raise Bad("priority must be an integer")
    reset = body.get("reset", "home" if kind == "goal" else "none")
    if reset not in ("home", "none"):
        raise Bad("reset must be home or none")
    return {"kind": kind, "device": device, "app": app, "prompt": body.get("prompt"), "goal": body.get("goal"),
            "model": model, "harness": harness, "max_steps": max_steps, "oracle": oracle, "submitter": sub,
            "idem": idem, "priority": priority, "reset": reset}


def body_hash(j):
    """What makes two submits 'the same job' for idempotency (everything but the key itself)."""
    return hashlib.sha256(json.dumps({k: v for k, v in j.items() if k != "idem"}, sort_keys=True).encode()).hexdigest()


def submit(body, principal):
    j = validate(body)
    with DB_LOCK:
        bh = body_hash(j)
        if j["idem"]:
            hit = q("SELECT * FROM jobs WHERE submitter=? AND idem=?", (j["submitter"], j["idem"]))
            if hit:
                if hit[0]["body_hash"] and hit[0]["body_hash"] != bh:
                    return 409, {"error": "idempotency_key already used with a different job body",
                                 "id": hit[0]["id"], "state": hit[0]["state"]}
                return 200, {"id": hit[0]["id"], "state": hit[0]["state"], "idempotent_replay": True}
        jid = uuid.uuid4().hex[:12]
        spec = {k: v for k, v in j.items() if k != "idem"}
        # job.json first: the runner reads it, and the reconciler may pick the row up at once.
        common.write_json(common.job_dir(jid) / "job.json", {"id": jid, **spec, "idempotency_key": j["idem"]})
        q("""INSERT INTO jobs (id, submitter, idem, kind, device, app, prompt, goal, model, harness, max_steps,
             oracle, priority, reset, state, created_at, principal, body_hash)
             VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?, 'queued', ?, ?, ?)""",
          (jid, j["submitter"], j["idem"], j["kind"], j["device"], j["app"], j["prompt"], j["goal"], j["model"],
           j["harness"], j["max_steps"], json.dumps(j["oracle"]) if j["oracle"] else None, j["priority"],
           j["reset"], common.now_iso(), principal, bh))
    WAKE.set()
    return 202, {"id": jid, "state": "queued"}


# ------------------------------------------------------------------ devices / gates
_gate_cache = {}
_dev_cache = {}


def gate(dev):
    hit = _gate_cache.get(dev)
    if hit and time.time() - hit[0] < GATE_TTL_S:
        return hit[1]
    try:
        reason = common.phone_worker().gate(dev)
    except Exception as e:  # noqa: BLE001 - fail closed
        reason = f"gate unavailable: {type(e).__name__}: {e}"
    _gate_cache[dev] = (time.time(), reason)
    return reason


def lock_holder(dev):
    """Who holds a UI lock for `dev`: ~/tmp/<dev>-ui.lock (Dash test workers) or
    /tmp/<dev>-ui.lock (host /proc mounted at /host/proc gives host pids)."""
    for path in (common.HOME / "tmp" / f"{dev}-ui.lock", Path(f"/tmp/{dev}-ui.lock")):
        hit = _flock_holder(path)
        if hit:
            return {**hit, "lock": str(path)}
    return None


def _flock_holder(path):
    proc = Path("/host/proc") if Path("/host/proc/locks").exists() else Path("/proc")
    try:
        st = path.stat()
        for line in (proc / "locks").read_text().splitlines():
            f = line.split()
            if len(f) < 8 or f[1] != "FLOCK" or f[3] != "WRITE":
                continue
            major, minor, inode = f[5].split(":")
            if int(inode) == st.st_ino and int(major, 16) == os.major(st.st_dev) and int(minor, 16) == os.minor(st.st_dev):
                pid = int(f[4])
                try:
                    cmd = (proc / str(pid) / "cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace").strip()
                except OSError:
                    cmd = None
                return {"pid": pid, "cmd": (cmd or "")[:200]}
    except (OSError, ValueError):
        return None
    return None


def device_info(dev):
    hit = _dev_cache.get(dev)
    if hit and time.time() - hit[0] < 20:
        info = dict(hit[1])
    else:
        info = {"id": dev, "hardware": common.HARDWARE[dev]}
        try:
            pw = common.phone_worker()
            d = pw.device(dev)
            info["serial"] = d.serial
            info["online"] = True
            p = pw.presence(dev)
            info["foreground"] = p.get("foreground")
            info["in_call"] = p.get("in_call")
            info["owner_idle_s"] = None if p.get("idle_s") is None else round(p["idle_s"])
            bat = d.shell("dumpsys battery | grep -E '^  level:'", check=False)
            m = re.search(r"level: (\d+)", bat)
            info["battery"] = int(m.group(1)) if m else None
        except Exception as e:  # noqa: BLE001
            info.update(serial=None, online=False, error=f"{type(e).__name__}: {e}")
        _dev_cache[dev] = (time.time(), info)
        info = dict(info)
    reason = gate(dev)
    info["gate"] = {"allowed": reason is None, "reason": reason}
    info["lock_holder"] = lock_holder(dev)
    rows = q("SELECT COUNT(*) n FROM jobs WHERE state NOT IN ('succeeded','failed','cancelled') AND "
             "(device=? OR assigned=?)", (dev, dev))
    info["queue_depth"] = rows[0]["n"]
    info["queue_depth_any"] = q("SELECT COUNT(*) n FROM jobs WHERE device='any' AND assigned IS NULL AND "
                                "state NOT IN ('succeeded','failed','cancelled')")[0]["n"]
    return info


# ------------------------------------------------------------------ k8s
KUBE = None


def k8s_job_manifest(r, tolerate):
    name = f"pq-{r['id']}-{r['attempts'] + 1}"
    labels = {"kueue.x-k8s.io/queue-name": "phones", "app.kubernetes.io/name": "phone-job",
              "z0.dev/phoneq-id": r["id"]}
    if (r["priority"] or 0) > 0:
        labels["kueue.x-k8s.io/priority-class"] = "phone-urgent"
    ro = lambda name, path: ({"name": name, "hostPath": {"path": path, "type": "Directory"}},  # noqa: E731
                             {"name": name, "mountPath": path, "readOnly": True})
    rw = lambda name, path: ({"name": name, "hostPath": {"path": path, "type": "Directory"}},  # noqa: E731
                             {"name": name, "mountPath": path})
    mounts = [ro("home", "/home/kvn"), ro("zer0models", "/mnt/zer0models"),
              rw("tmp", "/tmp"), rw("state", str(common.STATE)), rw("driver", str(common.DRIVER)),
              rw("hometmp", "/home/kvn/tmp")]
    vols = [v for v, _ in mounts] + [
        {"name": "code", "configMap": {"name": CODE_CM, "defaultMode": 0o555}},
        # only the shim HMAC key (per-job model tokens); never the API token hashes
        {"name": "auth", "secret": {"secretName": "phone-queue-auth", "defaultMode": 0o440,
                                    "items": [{"key": "shim-key", "path": "shim-key"}]}}]
    vms = [m for _, m in mounts] + [{"name": "code", "mountPath": "/app", "readOnly": True},
                                    {"name": "auth", "mountPath": str(common.AUTH_DIR), "readOnly": True}]
    return {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": name, "namespace": common.NAMESPACE, "labels": labels,
                     "annotations": {"z0.dev/submitter": r["submitter"], "z0.dev/device-request": r["device"]}},
        "spec": {
            "backoffLimit": 0, "ttlSecondsAfterFinished": 86400, "activeDeadlineSeconds": common.JOB_DEADLINE_S,
            "template": {
                "metadata": {"labels": {"app.kubernetes.io/name": "phone-job", "z0.dev/phoneq-id": r["id"]}},
                "spec": {
                    "restartPolicy": "Never", "hostNetwork": True, "dnsPolicy": "ClusterFirstWithHostNet",
                    "serviceAccountName": "phone-runner", "terminationGracePeriodSeconds": 30,
                    "nodeSelector": {"kubernetes.io/hostname": "groot"},
                    "tolerations": [{"key": "z0.dev/host", "operator": "Equal", "value": "interactive",
                                     "effect": "PreferNoSchedule"}] +
                                   [{"key": "z0.dev/phone", "operator": "Equal", "value": d, "effect": "NoSchedule"}
                                    for d in tolerate],
                    "securityContext": {"runAsUser": 1000, "runAsGroup": 1000, "runAsNonRoot": True,
                                        "fsGroup": 1000, "seccompProfile": {"type": "RuntimeDefault"}},
                    "containers": [{
                        "name": "run", "image": IMAGE,
                        "command": [str(common.DRIVER_PY), "-u", "/app/runner.py", r["id"]],
                        "env": [{"name": "HOME", "value": "/home/kvn"},
                                {"name": "PHONEQ_STATE", "value": str(common.STATE)},
                                {"name": "PHONEQ_K8S_JOB", "value": name},
                                {"name": "PHONEQ_ATTEMPT", "value": str(r["attempts"] + 1)},
                                {"name": "PYTHONDONTWRITEBYTECODE", "value": "1"}],
                        "resources": {"requests": {"cpu": "100m", "memory": "256Mi", common.RESOURCE: "1"},
                                      "limits": {"cpu": "1", "memory": "1Gi", common.RESOURCE: "1"}},
                        "securityContext": {"allowPrivilegeEscalation": False, "capabilities": {"drop": ["ALL"]}},
                        "volumeMounts": vms}],
                    "volumes": vols}}}}


def model_check(model):
    """Shim preflight before any phone slot is used: (None, None) if routable;
    ('failed', why) when nobody can serve the model (404 model_unavailable);
    ('blocked', why) when the shim or a model backend is down or short of memory (503);
    shim unreachable -> ('blocked', ...) too: infrastructure, never a verdict on the model."""
    try:
        with urllib.request.urlopen(common.SHIM_URL + "/phoneq/available?" +
                                    urllib.parse.urlencode({"model": model}), timeout=10):
            return None, None
    except urllib.error.HTTPError as e:
        try:
            why = json.loads(e.read()).get("error")
        except ValueError:
            why = None
        if e.code == 404:
            return "failed", why or f"model_unavailable: {model}"
        return "blocked", f"infra: model shim HTTP {e.code}: {why or ''}".strip()
    except OSError as e:
        return "blocked", f"infra: model shim unreachable: {e}"


def create_k8s_job(r):
    if r["harness"] == "fx":
        verdict, why = model_check(r["model"])
        if verdict == "failed":
            qlive("UPDATE jobs SET state='failed', finished_at=?, error=?, result=? WHERE id=?",
                  (common.now_iso(), why, json.dumps({"error_code": "model_unavailable", "steps": 0}), r["id"]))
            return
        if verdict == "blocked":
            if r["attempts"] >= MAX_ATTEMPTS:
                qlive("UPDATE jobs SET state='failed', finished_at=?, error=?, result=? WHERE id=?",
                      (common.now_iso(), why, json.dumps({"error_code": "infra_unavailable", "steps": 0}), r["id"]))
            else:
                qlive("UPDATE jobs SET state='blocked', error=?, next_try=?, attempts=attempts+1 WHERE id=?",
                      (why, time.time() + BLOCKED_RETRY_S, r["id"]))
            return
    want = [r["device"]] if r["device"] != "any" else list(common.DEVICES)
    open_devs, reasons = [], {}
    for dev in want:
        reason = gate(dev)
        if reason is None:
            open_devs.append(dev)
        else:
            reasons[dev] = reason
    if not open_devs:
        msg = "; ".join(f"{d}: {why}" for d, why in reasons.items())
        qlive("UPDATE jobs SET state='blocked', error=?, next_try=? WHERE id=?",
              (f"gate closed — {msg}", time.time() + BLOCKED_RETRY_S, r["id"]))
        return
    manifest = k8s_job_manifest(r, open_devs)
    name = manifest["metadata"]["name"]
    info = f"k8s Job created; eligible devices {','.join(open_devs)}"
    try:
        KUBE.req("POST", KUBE.jobs_path(), manifest)
    except RuntimeError as e:
        # A crash between an earlier POST and its UPDATE leaves this exact Job behind: adopt it
        # instead of failing with 409 on every tick while an unwatched Job drives the phone.
        existing = KUBE.req("GET", KUBE.jobs_path(name)) if "HTTP 409" in str(e) else None
        if not existing or existing["metadata"].get("labels", {}).get("z0.dev/phoneq-id") != r["id"]:
            raise
        info = "adopted existing k8s Job (front door restarted after creating it)"
    if not qlive("UPDATE jobs SET state='queued', k8s_job=?, attempts=attempts+1, error=NULL, info=? WHERE id=?",
                 (name, info, r["id"])):
        delete_k8s_job(name)  # cancelled while we were creating it: the cancel wins


def delete_k8s_job(name):
    KUBE.req("DELETE", KUBE.jobs_path(name), {"kind": "DeleteOptions", "apiVersion": "v1",
                                              "propagationPolicy": "Background"})


def pods_by_job():
    out = KUBE.req("GET", f"/api/v1/namespaces/{common.NAMESPACE}/pods",
                   params={"labelSelector": "app.kubernetes.io/name=phone-job"}) or {}
    res = {}
    for p in out.get("items", []):
        res[p["metadata"].get("labels", {}).get("job-name")] = p
    return res


def finish_from_result(r, job_obj, pod):
    jdir = common.job_dir(r["id"])
    res = common.read_json(jdir / f"result-{r['attempts']}.json")
    if res is None:
        tail = ""
        if pod:
            try:
                req = urllib.request.Request(
                    f"{KUBE.base}/api/v1/namespaces/{common.NAMESPACE}/pods/{pod['metadata']['name']}/log?tailLines=15",
                    headers={"Authorization": "Bearer " + (KUBE.SA / "token").read_text().strip()})
                with urllib.request.urlopen(req, context=KUBE.ctx, timeout=10) as resp:
                    tail = "; log: " + resp.read().decode(errors="replace")[-1500:]
            except Exception:  # noqa: BLE001
                pass
        status = (pod or {}).get("status", {})
        cs = (status.get("containerStatuses") or [{}])[0].get("state", {})
        why = json.dumps(cs.get("terminated") or cs.get("waiting") or {})[:400]
        qlive("UPDATE jobs SET state='failed', finished_at=?, error=? WHERE id=?",
              (common.now_iso(), f"runner wrote no result; pod state {why}{tail}", r["id"]))
        return
    state = res.get("state", "failed")
    if state == "blocked":
        # A closed gate (S25 off / owner busy / call) never fails a job: it waits until the gate
        # opens or the submitter cancels. Every other block (UI lock, pacing, infra) counts.
        gated = (res.get("error") or "").startswith("gate ")
        counted = r["attempts"] - (r["gate_blocks"] or 0) - (1 if gated else 0)
        retry = gated or counted < MAX_ATTEMPTS
        qlive("UPDATE jobs SET state=?, k8s_job=NULL, error=?, next_try=?, assigned=NULL, gate_blocks=gate_blocks+?, "
              "finished_at=CASE WHEN ?='failed' THEN ? ELSE finished_at END WHERE id=?",
              ("blocked" if retry else "failed", res.get("error"), time.time() + BLOCKED_RETRY_S, 1 if gated else 0,
               "blocked" if retry else "failed", common.now_iso(), r["id"]))
        return
    if state not in ("succeeded", "failed", "cancelled"):
        state = "failed"
    public = {k: res.get(k) for k in ("final_output", "steps", "oracle_pass", "transcript_path", "tokens_in",
                                      "tokens_out", "ms", "cold_ms") if res.get(k) is not None}
    public.update({k: res[k] for k in ("device", "serial", "oracle", "chat", "fx", "lock_wait_ms", "pace_wait_ms",
                                       "error_code", "transcript_dir",
                                       "foreground_before", "foreground_after_job", "restored",
                                       "foreground_restored_to", "attempt") if k in res})
    qlive("UPDATE jobs SET state=?, started_at=?, finished_at=?, result=?, error=?, assigned=? WHERE id=?",
          (state, res.get("started_at"), res.get("finished_at"), json.dumps(public), res.get("error"),
           res.get("device") or r["assigned"], r["id"]))


def reconcile_once():
    rows = q("SELECT * FROM jobs WHERE state NOT IN ('succeeded','failed','cancelled') "
             "ORDER BY priority DESC, created_at")
    if not rows:
        return
    workloads = KUBE.workloads()
    pods = pods_by_job()
    for r in rows:
        try:
            if not r["k8s_job"]:
                if r["state"] == "blocked" and time.time() < (r["next_try"] or 0):
                    continue
                if r["state"] == "blocked":
                    _gate_cache.clear()  # re-evaluate gates fresh on each blocked retry
                create_k8s_job(r)
                continue
            job_obj = KUBE.req("GET", KUBE.jobs_path(r["k8s_job"]))
            if job_obj is None:
                qlive("UPDATE jobs SET state='failed', error='k8s Job disappeared', finished_at=? WHERE id=?",
                      (common.now_iso(), r["id"]))
                continue
            conds = {c["type"]: c for c in job_obj.get("status", {}).get("conditions", []) if c.get("status") == "True"}
            pod = pods.get(r["k8s_job"])
            if "Complete" in conds or "Failed" in conds:
                finish_from_result(r, job_obj, pod)
                continue
            wl = KUBE.workload_for_job(r["k8s_job"], workloads)
            adm = common.workload_condition(wl, "Admitted")
            dev = common.workload_flavor(wl)
            if adm and adm.get("status") == "True":
                phase = (pod or {}).get("status", {}).get("phase")
                # Succeeded/Failed pods stay "running" until the Job condition lands.
                state = "running" if phase in ("Running", "Succeeded", "Failed") else "admitted"
                qlive("UPDATE jobs SET state=?, assigned=?, admitted_at=COALESCE(admitted_at, ?), "
                      "started_at=CASE WHEN ?='running' THEN COALESCE(started_at, ?) ELSE started_at END, info=? "
                      "WHERE id=?",
                  (state, dev, adm.get("lastTransitionTime"), state, common.now_iso(),
                   f"admitted by Kueue on flavor phone-{dev}", r["id"]))
            else:
                qr = common.workload_condition(wl, "QuotaReserved")
                msg = (qr or {}).get("message") or ("waiting for Kueue workload" if wl is None else "pending")
                qlive("UPDATE jobs SET state='queued', info=? WHERE id=?", (f"kueue: {msg}"[:500], r["id"]))
        except Exception as e:  # noqa: BLE001 - one bad job never stalls the loop
            qlive("UPDATE jobs SET info=? WHERE id=?", (f"reconcile error: {type(e).__name__}: {e}"[:500], r["id"]))


WAKE = threading.Event()


def reconciler():
    while True:
        try:
            reconcile_once()
        except Exception:  # noqa: BLE001
            traceback.print_exc()
        WAKE.wait(TICK_S)
        WAKE.clear()


def cancel(jid, caller, body):
    submitter = (body or {}).get("submitter") if isinstance(body, dict) else None
    with DB_LOCK:
        rows = q("SELECT * FROM jobs WHERE id=?", (jid,))
        if not rows:
            return 404, {"error": "no such job"}
        r = rows[0]
        if not caller["admin"] and (r["principal"] != caller["principal"] or submitter != r["submitter"]):
            return 403, {"error": "only the job's own submitter (same token principal, body {\"submitter\": ...}) "
                                  "or an admin token can cancel it", "id": jid}
        if r["state"] in common.TERMINAL:
            return 409, {"error": f"job already {r['state']}", "id": jid, "state": r["state"]}
        if r["k8s_job"]:
            try:
                delete_k8s_job(r["k8s_job"])
            except Exception as e:  # noqa: BLE001
                return 502, {"error": f"could not delete k8s Job: {e}"}
        q("UPDATE jobs SET state='cancelled', finished_at=?, error='cancelled by request' WHERE id=?",
          (common.now_iso(), jid))
    return 200, {"id": jid, "state": "cancelled"}


def health():
    out = {"ok": True, "port": common.API_PORT}
    try:
        q("SELECT 1")
        out["db"] = "ok"
    except Exception as e:  # noqa: BLE001
        out.update(ok=False, db=str(e))
    try:
        KUBE.req("GET", KUBE.jobs_path(), params={"limit": "1"})
        node = KUBE.req("GET", "/api/v1/nodes/groot") or {}
        out["k8s"] = "ok"
        out["node_phone_capacity"] = node.get("status", {}).get("capacity", {}).get(common.RESOURCE)
        if not out["node_phone_capacity"]:
            out["ok"] = False
            out["k8s"] = "node groot does not advertise z0.dev/phone (run services/phone-queue/advertise-phones)"
    except Exception as e:  # noqa: BLE001
        out.update(ok=False, k8s=str(e)[:300])
    try:
        with urllib.request.urlopen(common.SHIM_URL + "/healthz", timeout=3) as resp:
            out["model_shim"] = json.load(resp)
    except Exception as e:  # noqa: BLE001
        out["model_shim"] = f"unreachable: {e}"
    return out


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = "phone-queue/1"

    def log_message(self, fmt, *args):
        sys.stderr.write("%s %s\n" % (self.address_string(), fmt % args))

    def _send(self, status, obj):
        body = (json.dumps(obj, indent=1) + "\n").encode()
        self.send_response(status)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        url = urllib.parse.urlparse(self.path)
        qs = urllib.parse.parse_qs(url.query)
        try:
            if url.path == "/healthz":
                h = health()
                return self._send(200 if h["ok"] else 503, h)
            if url.path == "/v1/devices":
                return self._send(200, {"devices": [device_info(d) for d in common.DEVICES]})
            full = who(self.headers) is not None
            if url.path == "/v1/jobs":
                sql, args = "SELECT * FROM jobs WHERE 1=1", []
                for key, col in (("submitter", "submitter"), ("state", "state"), ("device", "device")):
                    if qs.get(key):
                        sql += f" AND {col}=?"
                        args.append(qs[key][0])
                limit = min(int((qs.get("limit") or ["50"])[0]), 500)
                rows = q(sql + " ORDER BY created_at DESC LIMIT ?", (*args, limit))
                return self._send(200, {"jobs": [row_to_job(r, full) for r in rows]})
            m = re.fullmatch(r"/v1/jobs/([a-f0-9]{12})", url.path)
            if m:
                rows = q("SELECT * FROM jobs WHERE id=?", (m.group(1),))
                return self._send(200, row_to_job(rows[0], full)) if rows else self._send(404, {"error": "no such job"})
            return self._send(404, {"error": "not found"})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        url = urllib.parse.urlparse(self.path)
        try:
            n = int(self.headers.get("content-length") or 0)
            if n > 200_000:
                return self._send(413, {"error": "body too large"})
            raw = self.rfile.read(n) if n else b""
            caller = who(self.headers)
            if caller is None:
                if not tokens():
                    return self._send(503, {"error": "auth not configured (Secret phone-queue-auth missing); "
                                                     "writes are refused"})
                return self._send(401, {"error": "Authorization: Bearer <token> required "
                                                 "(phoneq reads ~/.config/phoneq/token or $PHONEQ_TOKEN)"})
            try:
                body = json.loads(raw or b"null")
            except ValueError:
                return self._send(400, {"error": "invalid JSON"})
            if url.path == "/v1/jobs":
                status, out = submit(body, caller["principal"])
                return self._send(status, out)
            m = re.fullmatch(r"/v1/jobs/([a-f0-9]{12})/cancel", url.path)
            if m:
                return self._send(*cancel(m.group(1), caller, body))
            return self._send(404, {"error": "not found"})
        except Bad as e:
            return self._send(400, {"error": str(e)})
        except Exception as e:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})


class Server(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def main():
    global CONN, KUBE
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))  # PID 1: exit at once on rollout
    CONN = db()
    KUBE = common.Kube()
    threading.Thread(target=reconciler, daemon=True).start()
    servers = []
    for host in BINDS:
        try:
            srv = Server((host, common.API_PORT), Handler)
        except OSError as e:
            print(f"phone-queue: cannot bind {host}:{common.API_PORT}: {e}", file=sys.stderr, flush=True)
            continue
        servers.append(srv)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        print(f"phone-queue API on http://{host}:{common.API_PORT}", flush=True)
    if not servers:
        sys.exit("phone-queue: no listener")
    while True:
        time.sleep(3600)


if __name__ == "__main__":
    main()
