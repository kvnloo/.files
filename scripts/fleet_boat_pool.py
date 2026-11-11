"""Boat as a k3s autoscaling pool, on the bare official `boat` CLI.

One Kueue Job = one Boat sandbox. ClusterQueue `boat` (config/k3s/kueue/boat.yaml)
meters the extended resource z0.dev/boat; each admitted pod is a tiny relay on
groot that runs `boat run` (create, run, delete). No pending work = no sandboxes.

Budget: the quota is the plan-included VM time from `boat --json limits`
(creditBalanceSeconds), never dollars. It is 0 whenever a start could bill:
wallet balance > 0, keepGoing on, or a nonzero next-start price. `fleet health`
(every 2 min) resyncs it, so queued work stops being admitted once hours run out.
"""
import json
import os
import shlex
import subprocess
import sys
import time
import uuid

NAMESPACE = "fleet-boat"
QUEUE = "boat"
NODE = "groot"
RESOURCE = "z0.dev/boat"
MAX_SLOTS = 4             # concurrent sandboxes; provider allows 100, our relays stay small
SLOT_SECONDS = 3600       # included VM time reserved per admitted sandbox
BOAT = os.path.expanduser("~/.local/bin/boat")
# `boat run --push` shells out to ssh-keygen/ssh: the image needs an OpenSSH client,
# a passwd entry for the uid (host /etc/passwd, read-only) and a writable $HOME/.ssh.
IMAGE = "docker.io/alpine/git:v2.49.1"


def slots(limits):
    """Concurrent sandboxes the included VM time can pay for; 0 on any billing path."""
    if (not limits.get("canStart") or (limits.get("wallet") or {}).get("balanceDollars") != 0
            or (limits.get("keepGoing") or {}).get("enabled") is not False
            or limits.get("nextStartDollars") != 0):
        return 0
    seconds = limits.get("creditBalanceSeconds")
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool) or seconds <= 0:
        return 0
    return max(0, min(MAX_SLOTS, int(seconds // SLOT_SECONDS)))


def kubectl(*args, stdin=None):
    env = {**os.environ, "KUBECONFIG": os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/k3s.yaml"))}
    return subprocess.run(["kubectl", *args], input=stdin, capture_output=True, text=True,
                          timeout=60, check=True, env=env).stdout


def sync(limits, run=kubectl):
    """Advertise relay capacity on groot and set the queue quota from the budget."""
    capacity = json.loads(run("get", "node", NODE, "-o", "jsonpath={.status.capacity}") or "{}")
    if capacity.get(RESOURCE) != str(MAX_SLOTS):
        op = "replace" if RESOURCE in capacity else "add"
        run("patch", "node", NODE, "--subresource=status", "--type=json", "-p", json.dumps(
            [{"op": op, "path": "/status/capacity/" + RESOURCE.replace("/", "~1"), "value": str(MAX_SLOTS)}]))
    quota = str(slots(limits))
    run("patch", "clusterqueue", QUEUE, "--type=json", "-p", json.dumps(
        [{"op": "replace", "path": "/spec/resourceGroups/0/flavors/0/resources/0/nominalQuota",
          "value": quota}]))
    return int(quota)


def job(cmd, src=None, timeout=1800, machine="small"):
    """Kueue Job whose pod relays one bare `boat run` and exits with its code."""
    name = "boat-" + uuid.uuid4().hex[:12]
    argv = [BOAT, "--no-update", "run", "--type", machine, "--timeout", str(timeout)]
    if src:
        argv += ["--push", src]
    argv += ["--", "bash", "-lc", shlex.join(cmd)]
    home = os.path.expanduser("~")
    # The CLI's login lives in ~/.config/ascii/boat (it may refresh it); state holds its create lock.
    mounts = [(BOAT, True), (home + "/.config/ascii", False), (home + "/.local/state/boat", False),
              ("/etc/passwd", True)]
    if src:
        mounts.append((src, True))
    volumes = [{"name": "home", "emptyDir": {}}] + [
        {"name": f"m{i}", "hostPath": {"path": path}} for i, (path, _) in enumerate(mounts)]
    return name, {
        "apiVersion": "batch/v1", "kind": "Job",
        "metadata": {"name": name, "namespace": NAMESPACE,
                     "labels": {"kueue.x-k8s.io/queue-name": QUEUE, "app": "boat-pool"}},
        "spec": {
            "backoffLimit": 0, "ttlSecondsAfterFinished": 86400,
            "activeDeadlineSeconds": timeout + 900, "suspend": True,
            "template": {"metadata": {"labels": {"app": "boat-pool"}}, "spec": {
                "restartPolicy": "Never", "nodeSelector": {"kubernetes.io/hostname": NODE},
                "securityContext": {"runAsNonRoot": True, "runAsUser": os.getuid(),
                                    "runAsGroup": os.getgid(),
                                    "seccompProfile": {"type": "RuntimeDefault"}},
                "containers": [{
                    "name": "relay", "image": IMAGE, "command": argv,
                    "env": [{"name": "HOME", "value": home}, {"name": "BOAT_NO_UPDATE", "value": "1"}],
                    "resources": {"requests": {RESOURCE: "1", "cpu": "50m", "memory": "64Mi"},
                                  "limits": {RESOURCE: "1", "memory": "256Mi"}},
                    "securityContext": {"allowPrivilegeEscalation": False,
                                        "capabilities": {"drop": ["ALL"]}},
                    "volumeMounts": [{"name": "home", "mountPath": home}] + [
                        {"name": f"m{i}", "mountPath": path, "readOnly": ro}
                        for i, (path, ro) in enumerate(mounts)]}],
                "volumes": volumes}}}}


def submit(manifest, run=kubectl):
    run("create", "-f", "-", stdin=json.dumps(manifest))


def wait(name, run=kubectl, poll=5):
    """Block until the Job finishes, print the relay's output, return `boat run`'s exit code."""
    while True:
        status = json.loads(run("-n", NAMESPACE, "get", "job", name, "-o", "json"))["status"]
        done = {c["type"] for c in status.get("conditions", []) if c.get("status") == "True"}
        if done & {"Complete", "Failed"}:
            break
        time.sleep(poll)
    sys.stdout.write(run("-n", NAMESPACE, "logs", "job/" + name))
    pods = json.loads(run("-n", NAMESPACE, "get", "pods", "-l", "job-name=" + name, "-o", "json"))["items"]
    for pod in pods:
        for container in pod.get("status", {}).get("containerStatuses", []):
            terminated = container.get("state", {}).get("terminated")
            if terminated:
                return terminated.get("exitCode", 1)
    return 0 if "Complete" in done else 1
