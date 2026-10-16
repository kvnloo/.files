#!/usr/bin/env bash
set -euo pipefail
# Python's standard library keeps JSON generation and bounded API calls portable.
exec python3 - "$0" "$@" <<'PY'
import argparse
import copy
import hashlib
import json
import signal
from pathlib import Path
import subprocess
import sys
import time
import uuid

parser = argparse.ArgumentParser(description="Explicit-context, namespace-scoped CPU/quota/network/TTL smoke. Mutates only uniquely named test resources; apply boundary.json separately first.")
parser.add_argument("--context", required=True, help="explicit kubectl context, including 'default' for bundled K3s")
parser.add_argument("--kubectl", default="kubectl", help="kubectl executable or executable wrapper (one path, not a shell command)")
args = parser.parse_args(sys.argv[2:])
if not args.context.strip():
    parser.error("--context cannot be empty")
root = Path(sys.argv[1]).resolve().parent.parent
ns = "oss-factory-jobs"
run = "dotfiles-smoke-" + uuid.uuid4().hex[:12]
label = "dotfiles.k3s/smoke-run"
base = [args.kubectl, "--context", args.context]
owned = []
started = time.monotonic()

def interrupted(signum, frame):
    raise KeyboardInterrupt(f"received signal {signum}")

signal.signal(signal.SIGTERM, interrupted)

def event(kind, **values):
    print(json.dumps({"event": kind, "run": run, **values}, sort_keys=True), flush=True)

def kubectl(*argv, obj=None, check=True, timeout=35):
    result = subprocess.run(base + [f"--request-timeout={timeout - 5}s"] + list(argv), input=None if obj is None else json.dumps(obj),
                            text=True, capture_output=True, timeout=timeout)
    if check and result.returncode:
        raise RuntimeError(f"kubectl {' '.join(argv)}: {result.stderr.strip()} {result.stdout.strip()}")
    return result

def get(kind, name=None):
    return json.loads(kubectl("-n", ns, "get", kind, *([name] if name else []), "-o", "json").stdout)

def create(obj):
    kind, name = obj["kind"], obj["metadata"]["name"]
    # Register only after successful creation: never delete a preexisting object.
    kubectl("create", "-f", "-", obj=obj)
    owned.append((kind, name))

def delete(kind, name):
    kubectl("-n", ns, "delete", kind, name, "--ignore-not-found=true", "--wait=true", "--timeout=45s", timeout=65)
    if (kind, name) in owned:
        owned.remove((kind, name))

def wait_for(*argv, seconds=180):
    return kubectl("-n", ns, "wait", *argv, f"--timeout={seconds}s", timeout=seconds + 25)

def wait_quota_release():
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        if get("resourcequota", "worker-guardrail").get("status", {}).get("used", {}).get("pods") == "0":
            return
        time.sleep(1)
    raise RuntimeError("Pod quota has not been replenished; stop rather than touching other workers")

def pod(name, command, *, gated=False):
    spec = copy.deepcopy(example["spec"]["template"]["spec"])
    spec["activeDeadlineSeconds"] = 300
    spec["containers"][0]["command"] = command
    spec["containers"][0]["resources"] = {"requests": {"cpu": "10m", "memory": "32Mi"}, "limits": {"cpu": "100m", "memory": "64Mi"}}
    if gated:
        spec["schedulingGates"] = [{"name": "dotfiles.k3s/quota-probe"}]
    return {"apiVersion": "v1", "kind": "Pod", "metadata": {"name": name, "namespace": ns, "labels": {label: run, "dotfiles.k3s/probe": name}}, "spec": spec}

def probe_connect(client, ip):
    code = "import socket; s=socket.create_connection((" + repr(ip) + ",8080),timeout=2); s.close()"
    return kubectl("-n", ns, "exec", client, "--", "python", "-c", code, check=False)

try:
    example = json.loads((root / "config/k3s/manifests/cpu-example-job.json").read_text())
    commit = subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()
    dirty = bool(subprocess.check_output(["git", "-C", str(root), "status", "--porcelain", "--untracked-files=normal"], text=True).strip())
    hashes = {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in
              [Path(sys.argv[1]).resolve(), root / "config/k3s/manifests/boundary.json", root / "config/k3s/manifests/cpu-example-job.json"]}
    event("source", context=args.context, source_commit=commit, checkout_dirty=dirty, sha256=hashes,
          scope="infrastructure smoke; not a Factory claim, contribution test or HITL receipt")
    # Verify live prerequisites without changing shared namespace policy/quota.
    namespace = json.loads(kubectl("get", "namespace", ns, "-o", "json").stdout)
    if namespace["metadata"].get("labels", {}).get("pod-security.kubernetes.io/enforce") != "restricted":
        raise RuntimeError("namespace must enforce restricted Pod Security Admission")
    expected = json.loads((root / "config/k3s/manifests/boundary.json").read_text())
    hard = next(x for x in expected["items"] if x["kind"] == "ResourceQuota")["spec"]["hard"]
    if get("resourcequota", "worker-guardrail")["spec"]["hard"] != hard:
        raise RuntimeError("live quota differs from the shared Factory guardrail")
    limits = next(x for x in expected["items"] if x["kind"] == "LimitRange")["spec"]["limits"]
    if get("limitrange", "worker-container-limits")["spec"]["limits"] != limits:
        raise RuntimeError("live container limits differ from the shared Factory boundary")
    if get("serviceaccount", "oss-factory-worker").get("automountServiceAccountToken") is not False:
        raise RuntimeError("worker ServiceAccount must disable token automount")
    policy = get("networkpolicy", "deny-all-worker-traffic")["spec"]
    if policy.get("podSelector") != {} or set(policy.get("policyTypes", [])) != {"Ingress", "Egress"} or policy.get("ingress") or policy.get("egress"):
        raise RuntimeError("default-deny ingress and egress policy required")
    # Do not race real workers: operator must reserve this namespace during smoke.
    active = [p["metadata"]["name"] for p in get("pods")["items"] if p.get("status", {}).get("phase") not in ("Succeeded", "Failed")]
    if active:
        raise RuntimeError("namespace has active Pods; reserve a quiet maintenance window, do not evict workers: " + repr(active))
    # Scheduling gates hold six nonterminal Pods without consuming worker CPU.
    for i in range(6):
        create(pod(f"{run}-quota-{i}", ["python", "-c", "import time; time.sleep(120)"], gated=True))
    seventh = pod(f"{run}-quota-6", ["python", "-c", "pass"], gated=True)
    result = kubectl("create", "-f", "-", obj=seventh, check=False)
    if result.returncode == 0:
        owned.append(("Pod", seventh["metadata"]["name"]))
        raise RuntimeError("seventh concurrent Pod unexpectedly admitted")
    if "exceeded quota: worker-guardrail" not in result.stderr or "pods=1" not in result.stderr:
        raise RuntimeError("seventh Pod failed for a reason other than the Pod quota: " + result.stderr)
    event("quota_seventh_pod_denied", stderr=result.stderr.strip(), held_nonterminal_pods=6)
    for i in range(6):
        delete("Pod", f"{run}-quota-{i}")
    wait_quota_release()
    # Test ingress and egress independently: denying both cannot prove each one.
    server, client = run + "-server", run + "-client"
    create(pod(server, ["python", "-m", "http.server", "8080", "--bind", "0.0.0.0", "--directory", "/tmp"]))
    create(pod(client, ["python", "-c", "import time; time.sleep(240)"]))
    selector = {"podSelector": {"matchLabels": {label: run}}}
    allows = {
        "Ingress": {"from": [{"podSelector": {"matchLabels": {"dotfiles.k3s/probe": client}}}], "ports": [{"protocol": "TCP", "port": 8080}]},
        "Egress": {"to": [{"podSelector": {"matchLabels": {"dotfiles.k3s/probe": server}}}], "ports": [{"protocol": "TCP", "port": 8080}]},
    }
    policies = {}
    for direction, rule in allows.items():
        name = run + "-allow-" + direction.lower()
        policies[direction] = {"apiVersion": "networking.k8s.io/v1", "kind": "NetworkPolicy",
                              "metadata": {"name": name, "namespace": ns, "labels": {label: run}},
                              "spec": {**selector, "policyTypes": [direction], direction.lower(): [rule]}}
        create(policies[direction])
    wait_for("--for=condition=Ready", "pod/" + server, "pod/" + client, seconds=150)
    ip = get("pod", server)["status"]["podIP"]
    reachable = False
    for _ in range(15):
        result = probe_connect(client, ip)
        if result.returncode == 0:
            reachable = True
            break
        time.sleep(1)
    if not reachable:
        raise RuntimeError("positive network control failed; cannot attribute unreachable endpoint to deny policy: " + result.stderr)
    event("network_positive_control", server_ip=ip, port=8080)
    for direction, policy in policies.items():
        # Keep the opposite direction allowed throughout this negative control.
        delete("NetworkPolicy", policy["metadata"]["name"])
        time.sleep(5)
        for _ in range(3):
            result = probe_connect(client, ip)
            if result.returncode == 0:
                raise RuntimeError(direction + " traffic still passes after allow removal; denial NOT proven")
            if "TimeoutError" not in result.stderr and "timed out" not in result.stderr:
                raise RuntimeError(direction + " negative control failed for unexpected reason: " + result.stderr)
            if get("pod", server).get("status", {}).get("phase") != "Running":
                raise RuntimeError("server stopped during negative control; denial inconclusive")
            event("network_negative_control", direction=direction, stderr=result.stderr.strip(), server_ip=ip, port=8080)
        create(policy)
        # Re-establish a live positive control before testing the next direction.
        for attempt in range(15):
            if probe_connect(client, ip).returncode == 0:
                break
            if attempt == 14:
                raise RuntimeError("positive control did not recover after restoring " + direction)
            time.sleep(1)
    for policy in policies.values():
        delete("NetworkPolicy", policy["metadata"]["name"])
    delete("Pod", client)
    delete("Pod", server)
    # New name on every invocation: never apply/reuse an immutable completed Job.
    job = copy.deepcopy(example)
    job["metadata"]["name"] = run + "-cpu"
    job["metadata"].setdefault("labels", {})[label] = run
    job["metadata"]["annotations"]["dotfiles.k3s/source-commit"] = commit
    job["metadata"]["annotations"]["dotfiles.k3s/checkout-dirty"] = str(dirty).lower()
    job["spec"]["template"]["metadata"]["labels"][label] = run
    job["spec"]["template"]["spec"]["containers"][0]["env"].append({"name": "SOURCE_COMMIT", "value": commit})
    create(job)
    name = job["metadata"]["name"]
    wait_for("--for=condition=complete", "job/" + name, seconds=210)
    event("job_logs", logs=kubectl("-n", ns, "logs", "job/" + name, "--timestamps=true").stdout)
    status = get("job", name)
    ttl = status.get("spec", {}).get("ttlSecondsAfterFinished")
    if ttl != job["spec"]["ttlSecondsAfterFinished"]:
        raise RuntimeError("live Job TTL differs from the bounded cleanup requirement")
    pods = json.loads(kubectl("-n", ns, "get", "pods", "-l", "job-name=" + name, "-o", "json").stdout)
    event("job_status", job=status, pods=pods)
    for p in pods["items"]:
        container_statuses = p.get("status", {}).get("containerStatuses", [])
        if not container_statuses:
            raise RuntimeError("missing container exit/imageID evidence")
        for c in container_statuses:
            terminated = c.get("state", {}).get("terminated", {})
            if terminated.get("exitCode") != 0 or not c.get("imageID"):
                raise RuntimeError("missing successful exit/imageID evidence")
            event("container_result", node=p["spec"].get("nodeName"), pod=p["metadata"]["name"], image=c["image"], imageID=c["imageID"], terminated=terminated)
    if not pods["items"]:
        raise RuntimeError("Job Pods disappeared before evidence capture")
    wait_for("--for=delete", "job/" + name, seconds=180)
    owned.remove(("Job", name))
    # Job deletion alone is insufficient: confirm dependent Pods disappeared too.
    for p in pods["items"]:
        wait_for("--for=delete", "pod/" + p["metadata"]["name"], seconds=60)
    event("ttl_cleanup_verified", job=name, configured_ttl_seconds=ttl, elapsed_seconds=round(time.monotonic() - started, 3))
except BaseException as exc:
    event("failure", error=str(exc))
    for kind, name in list(owned):
        try:
            event("failure_resource", resource=get(kind, name))
            if kind in ("Pod", "Job"):
                event("failure_logs", resource=name, logs=kubectl("-n", ns, "logs", kind.lower() + "/" + name, check=False).stdout)
        except Exception:
            pass
    sys.exit(1)
finally:
    for kind, name in reversed(list(owned)):
        try:
            delete(kind, name)
        except Exception as exc:
            event("cleanup_failed", kind=kind, name=name, error=str(exc))
PY
