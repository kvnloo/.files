"""Shared pieces of the phone queue: paths, devices, the reused host tools, and a
tiny in-cluster Kubernetes client (stdlib only, so it runs under any Python 3.11+).

Everything here REUSES existing host code instead of copying it:
  - gates and device discovery: ~/.local/bin/phone-worker (which uses fleet-adb)
  - ChatGPT/DeepSeek drivers, pacing and quota pauses: the chatgpt-driver directory
  - redaction: ~/.local/bin/phone-screen-safe
"""
import importlib.machinery
import importlib.util
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

HOME = Path(os.environ.get("HOME", "/home/kvn"))
STATE = Path(os.environ.get("PHONEQ_STATE", "/mnt/zer0models/phone-queue/state"))
JOBS = STATE / "jobs"
NAMESPACE = os.environ.get("PHONEQ_NAMESPACE", "phones")
API_PORT = int(os.environ.get("PHONEQ_PORT", "8792"))
SHIM_URL = os.environ.get("PHONEQ_SHIM_URL", "http://127.0.0.1:8795")
DEFAULT_MODEL = "openai-codex/gpt-6-luna"
DEVICES = ("s22", "s25")
HARDWARE = {"s22": "RFCTA1RZAQY", "s25": "R5CY93G2WNH"}
FLAVOR_DEVICE = {"phone-s22": "s22", "phone-s25": "s25"}
RESOURCE = "z0.dev/phone"

PHONE_WORKER = HOME / ".local/bin/phone-worker"
PHONE_SCREEN_SAFE = HOME / ".local/bin/phone-screen-safe"
FX = HOME / ".local/bin/fx"
DRIVER = Path(os.environ.get("PHONEQ_DRIVER", "/mnt/zer0models/workspace/zer0/data/operations/chatgpt-driver"))
DRIVER_PY = DRIVER / ".venv/bin/python"
APP_DIR = Path(__file__).resolve().parent

APPS = {"chatgpt": "com.openai.chatgpt", "deepseek": "com.deepseek.chat"}
TERMINAL = ("succeeded", "failed", "cancelled")
ID_RE = re.compile(r"^[a-f0-9]{12}$")


def now_iso(ts=None):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ts if ts is not None else time.time()))


def load_source(name, path):
    """Import a host script (no .py suffix) as a module, exactly as phone-worker loads fleet-adb."""
    path = Path(os.path.realpath(path))
    if str(path.parent) not in sys.path:
        sys.path.insert(0, str(path.parent))
    loader = importlib.machinery.SourceFileLoader(name, str(path))
    spec = importlib.util.spec_from_loader(name, loader)
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    sys.modules[name] = module
    return module


_pw = None


def phone_worker():
    """The owner's gate policy lives in phone-worker (S25 switch, call state, owner idle)."""
    global _pw
    if _pw is None:
        _pw = load_source("phone_worker", PHONE_WORKER)
    return _pw


def job_dir(job_id):
    if not ID_RE.match(job_id or ""):
        raise ValueError("bad job id")
    return JOBS / job_id


def write_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    os.replace(tmp, path)


def read_json(path, default=None):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError):
        return default


class Kube:
    """Minimal in-cluster API client using the pod's service account."""

    SA = Path("/var/run/secrets/kubernetes.io/serviceaccount")

    def __init__(self):
        host = os.environ.get("KUBERNETES_SERVICE_HOST")
        port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
        if not host:
            raise RuntimeError("not running in a pod (KUBERNETES_SERVICE_HOST unset)")
        self.base = f"https://{host}:{port}"
        self.ctx = ssl.create_default_context(cafile=str(self.SA / "ca.crt"))

    def req(self, method, path, body=None, params=None, ctype="application/json", timeout=15):
        url = self.base + path + ("?" + urllib.parse.urlencode(params) if params else "")
        data = json.dumps(body).encode() if body is not None else None
        token = (self.SA / "token").read_text().strip()  # projected tokens rotate; reread
        headers = {"Authorization": f"Bearer {token}", "Accept": "application/json"}
        if data is not None:
            headers["Content-Type"] = ctype
        request = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(request, context=self.ctx, timeout=timeout) as resp:
                return json.loads(resp.read() or b"{}")
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:500]
            if e.code == 404:
                return None
            raise RuntimeError(f"k8s {method} {path}: HTTP {e.code}: {detail}") from None

    def jobs_path(self, name=""):
        return f"/apis/batch/v1/namespaces/{NAMESPACE}/jobs" + (f"/{name}" if name else "")

    def workloads(self):
        out = self.req("GET", f"/apis/kueue.x-k8s.io/v1beta2/namespaces/{NAMESPACE}/workloads") or {}
        return out.get("items", [])

    def workload_for_job(self, job_name, items=None):
        for w in items if items is not None else self.workloads():
            for ref in w.get("metadata", {}).get("ownerReferences", []):
                if ref.get("kind") == "Job" and ref.get("name") == job_name:
                    return w
        return None


def workload_flavor(workload):
    """Device a Kueue admission assigned: podSetAssignments[].flavors[z0.dev/phone]."""
    adm = (workload or {}).get("status", {}).get("admission") or {}
    for ps in adm.get("podSetAssignments", []):
        flavor = (ps.get("flavors") or {}).get(RESOURCE)
        if flavor in FLAVOR_DEVICE:
            return FLAVOR_DEVICE[flavor]
    return None


def workload_condition(workload, kind):
    for c in (workload or {}).get("status", {}).get("conditions", []):
        if c.get("type") == kind:
            return c
    return None
