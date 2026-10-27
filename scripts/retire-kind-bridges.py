#!/usr/bin/env python3
"""Apply after kind deletion only. Default: check gates without changing the host."""
import argparse
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import urllib.request

HOME = Path.home()
KUBE = ["kubectl", "--kubeconfig", str(HOME / ".kube/k3s.yaml"), "--context", "default"]


def run(*args):
    return subprocess.check_output(args, text=True, timeout=30)


def gates():
    # Failure to contact Docker is not evidence that kind has been deleted.
    names = run("docker", "ps", "-a", "--format", "{{.Names}} {{.Label \"io.x-k8s.kind.cluster\"}}")
    if any("hermes-lab-control-plane" in line or line.endswith(" hermes-lab") for line in names.splitlines()):
        raise SystemExit("Refusing: kind hermes-lab still exists. Apply after kind deletion only.")
    deployment = json.loads(run(*KUBE, "-n", "hermes-lab", "get", "deployment", "z0intelligence-executor", "-o", "json"))
    status = deployment.get("status", {})
    if status.get("observedGeneration", 0) < deployment["metadata"]["generation"] or status.get("availableReplicas", 0) != 1:
        raise SystemExit("Refusing: current k3s executor Deployment is not available.")
    with urllib.request.urlopen("http://127.0.0.1:11503/readyz", timeout=5) as response:
        if response.status != 200:
            raise SystemExit("Refusing: k3s loopback executor is not ready.")


def replace_private(path, content, backup):
    if path.read_text() == content:
        return
    # Preserve secret-bearing configuration privately; never log its contents.
    destination = backup / path.name
    shutil.copyfile(path, destination)
    destination.chmod(0o600)
    fd, temporary = tempfile.mkstemp(dir=path.parent, prefix=".kind-retire-")
    try:
        with os.fdopen(fd, "w") as stream:
            stream.write(content)
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    gates()
    env = HOME / ".config/z0intelligence/service.env"
    override = HOME / ".config/systemd/user/z0intelligence.service.d/dogfood.conf"
    bridge = HOME / ".config/systemd/user/whisperflow-kind-bridge.service"
    env_text = env.read_text()
    lines = env_text.splitlines(keepends=True)
    if any(line.startswith("Z0INT_BIND_2=") and line.strip() != "Z0INT_BIND_2=172.19.0.1" for line in lines):
        raise SystemExit("Refusing: Z0INT_BIND_2 changed; review current host configuration.")
    new_env = "".join(line for line in lines if line.strip() != "Z0INT_BIND_2=172.19.0.1")
    override_text = override.read_text()
    new_override = override_text.replace(" --bind 172.19.0.1", "")
    if "172.19.0.1" in new_override:
        raise SystemExit("Refusing: unexpected remaining Docker bridge reference in authority override.")
    if not args.apply:
        print("Gates passed. --apply will retire whisperflow-kind-bridge and the authority Docker bridge bind; loopback stays.")
        return
    backup = HOME / ".local/state/kind-retirement" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup.mkdir(parents=True, mode=0o700)
    if bridge.exists() or bridge.is_symlink():
        subprocess.run(["systemctl", "--user", "disable", "whisperflow-kind-bridge.service"], check=True)
        stopped = subprocess.run(["systemctl", "--user", "stop", "whisperflow-kind-bridge.service"], capture_output=True)
        state = run("systemctl", "--user", "show", "whisperflow-kind-bridge.service", "-p", "ActiveState", "--value").strip()
        if state not in ("inactive", "failed"):
            raise SystemExit("Whisperflow bridge did not stop; refusing to remove its unit.")
        if stopped.returncode:
            # Its old ExecStopPost writes readiness into deleted kind. Check actual
            # stopped state rather than treating that obsolete API call as liveness.
            print("Bridge is stopped; its obsolete kind readiness hook returned an error.")
        shutil.copyfile(bridge, backup / bridge.name)
        (backup / bridge.name).chmod(0o600)
        bridge.unlink()
    replace_private(env, new_env, backup)
    replace_private(override, new_override, backup)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "restart", "z0intelligence.service"], check=True)
    with urllib.request.urlopen("http://127.0.0.1:11501/v1/providers", timeout=5) as response:
        if response.status != 200: raise SystemExit("Authority health failed after retirement; private backups retained.")
    print("Retired kind-only bridges; authority loopback healthy. Private rollback files retained under ~/.local/state/kind-retirement/.")


if __name__ == "__main__":
    main()
