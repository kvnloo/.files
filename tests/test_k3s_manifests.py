"""Cheap offline boundary checks; API admission/CNI/TTL need the real smoke.

Run with pytest. JSON is a native kubectl manifest format, so no YAML dependency
or private image/cluster credentials are needed for these checks.
"""
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "config/k3s/manifests"
BOUNDARY = json.loads((MANIFESTS / "boundary.json").read_text())
JOB = json.loads((MANIFESTS / "cpu-example-job.json").read_text())


def boundary(kind):
    return next(item for item in BOUNDARY["items"] if item["kind"] == kind)


def quantity(value):
    value = str(value)
    for suffix, factor in (("Gi", 1024**3), ("Mi", 1024**2), ("m", 0.001)):
        if value.endswith(suffix):
            return float(value[:-len(suffix)]) * factor
    return float(value)


def test_namespace_and_factory_identity_are_shared_not_an_authority_fork():
    namespace = boundary("Namespace")["metadata"]
    assert namespace["name"] == "oss-factory-jobs"
    for mode in ("enforce", "audit", "warn"):
        assert namespace["labels"][f"pod-security.kubernetes.io/{mode}"] == "restricted"
    for item in BOUNDARY["items"]:
        if item["kind"] != "Namespace":
            assert item["metadata"]["namespace"] == namespace["name"]
    sa = boundary("ServiceAccount")
    assert sa["metadata"]["name"] == "oss-factory-worker"
    assert sa["automountServiceAccountToken"] is False
    assert not any(item["kind"] in ("Role", "RoleBinding", "ClusterRoleBinding", "Secret") for item in BOUNDARY["items"])
    assert JOB["metadata"]["namespace"] == namespace["name"]


def test_concurrent_quota_excludes_terminal_pods_and_caps_retained_jobs():
    hard = boundary("ResourceQuota")["spec"]["hard"]
    # Kubernetes' pods resource counts nonterminal Pods; count/pods also charges
    # completed Pods and would quietly turn a concurrency guardrail into a TTL cap.
    assert quantity(hard["pods"]) == 6
    assert "count/pods" not in hard
    assert "scopes" not in boundary("ResourceQuota")["spec"]
    assert quantity(hard["count/jobs.batch"]) == 64
    assert quantity(hard["requests.cpu"]) == quantity(hard["limits.cpu"]) == 6
    assert quantity(hard["requests.memory"]) == quantity(hard["limits.memory"]) == 12 * 1024**3


def test_network_policy_grants_neither_dns_nor_api_nor_peer_access():
    spec = boundary("NetworkPolicy")["spec"]
    assert spec["podSelector"] == {}
    assert set(spec["policyTypes"]) == {"Ingress", "Egress"}
    assert not spec.get("ingress")
    assert not spec.get("egress")
    assert len([item for item in BOUNDARY["items"] if item["kind"] == "NetworkPolicy"]) == 1


def test_example_is_single_attempt_bounded_and_ttl_managed():
    spec = JOB["spec"]
    assert JOB["apiVersion"] == "batch/v1"
    assert JOB["kind"] == "Job"
    assert spec["parallelism"] == spec["completions"] == 1
    assert spec["backoffLimit"] == 0
    assert 1 <= spec["activeDeadlineSeconds"] <= 300
    assert 30 <= spec["ttlSecondsAfterFinished"] <= 3600
    assert spec["template"]["spec"]["restartPolicy"] == "Never"


def test_example_has_no_privilege_credentials_host_access_or_unbounded_scratch():
    pod = JOB["spec"]["template"]["spec"]
    assert pod["serviceAccountName"] == boundary("ServiceAccount")["metadata"]["name"]
    assert pod["automountServiceAccountToken"] is False
    for flag in ("hostNetwork", "hostPID", "hostIPC", "shareProcessNamespace"):
        assert not pod.get(flag)
    assert not pod.get("imagePullSecrets")
    security = pod["securityContext"]
    assert security["runAsNonRoot"] is True
    assert security["seccompProfile"]["type"] == "RuntimeDefault"
    volumes = {v["name"]: v for v in pod["volumes"]}
    assert len(volumes) == 1
    for volume in volumes.values():
        assert set(volume) == {"name", "emptyDir"}
        assert 0 < quantity(volume["emptyDir"]["sizeLimit"]) <= 64 * 1024**2
    assert len(pod["containers"]) == 1
    assert not pod.get("initContainers")
    for container in pod["containers"]:
        cs = container["securityContext"]
        assert not cs.get("privileged")
        assert cs["allowPrivilegeEscalation"] is False
        assert cs["readOnlyRootFilesystem"] is True
        assert cs["capabilities"] == {"drop": ["ALL"]}
        assert not container.get("envFrom")
        assert not any("valueFrom" in e for e in container.get("env", []))
        assert {e["name"] for e in container["env"]} <= {"HOME", "TMPDIR", "PYTHONDONTWRITEBYTECODE"}
        assert all(m["name"] in volumes and m["mountPath"] == "/tmp" for m in container["volumeMounts"])
        assert re.fullmatch(r"[^@\s]+@sha256:[0-9a-f]{64}", container["image"])


def test_resources_fit_limitrange_and_six_worker_quota():
    hard = boundary("ResourceQuota")["spec"]["hard"]
    ranges = boundary("LimitRange")["spec"]["limits"]
    limits = next(x for x in ranges if x["type"] == "Container")
    for container in JOB["spec"]["template"]["spec"]["containers"]:
        resources = container["resources"]
        for key in ("cpu", "memory"):
            minimum, maximum = quantity(limits["min"][key]), quantity(limits["max"][key])
            request = quantity(resources["requests"][key])
            limit = quantity(resources["limits"][key])
            assert 0 < minimum <= request <= limit <= maximum
            for kind in ("requests", "limits"):
                assert 6 * quantity(resources[kind][key]) <= quantity(hard[f"{kind}.{key}"])
            assert minimum <= quantity(limits["defaultRequest"][key]) <= quantity(limits["default"][key]) <= maximum


def test_smoke_requires_context_before_any_cluster_access(tmp_path):
    marker = tmp_path / "called"
    fake = tmp_path / "kubectl"
    fake.write_text(f"#!/bin/sh\ntouch '{marker}'\nexit 99\n")
    fake.chmod(0o700)
    for arguments in ([], ["--context", ""]):
        result = subprocess.run(["bash", str(ROOT / "scripts/smoke-k3s.sh"), "--kubectl", str(fake), *arguments], capture_output=True, text=True)
        assert result.returncode != 0
        assert "context" in result.stderr
        assert not marker.exists()


def test_repeated_smoke_connectivity_failures_never_mutate_cluster(tmp_path):
    # Exercise the real entrypoint with an unreachable API and an SSH-backed
    # kubectl wrapper. These fixtures do not establish real SSH connectivity.
    calls = tmp_path / "calls.jsonl"
    failed_transport = tmp_path / "failed-transport"
    failed_transport.write_text(
        f"#!{sys.executable}\n"
        "import json, sys\n"
        f"with open({str(calls)!r}, 'a') as log:\n"
        "    log.write(json.dumps(sys.argv[1:]) + '\\n')\n"
        "print('fixture connection refused', file=sys.stderr)\n"
        "sys.exit(255)\n"
    )
    failed_transport.chmod(0o700)
    wrapper = tmp_path / "kubectl-over-ssh"
    wrapper.write_text(
        "#!/bin/sh\n"
        'exec "$(dirname -- "$0")/failed-transport" fixture-desktop '
        'sudo -n /usr/local/bin/k3s kubectl "$@"\n'
    )
    wrapper.chmod(0o700)
    runs = set()
    for executable in (failed_transport, wrapper):
        for _ in range(2):
            result = subprocess.run(
                ["bash", str(ROOT / "scripts/smoke-k3s.sh"),
                 "--context", "offline-unreachable", "--kubectl", str(executable)],
                capture_output=True, text=True, timeout=15,
            )
            assert result.returncode == 1, result.stderr
            events = [json.loads(line) for line in result.stdout.splitlines()]
            assert [event["event"] for event in events] == ["source", "failure"]
            assert "fixture connection refused" in events[-1]["error"]
            assert events[0]["run"] == events[-1]["run"]
            assert events[0]["run"] not in runs
            runs.add(events[0]["run"])
    commands = [json.loads(line) for line in calls.read_text().splitlines()]
    assert len(commands) == len(runs)
    # No create/apply/delete, sudo prompt, or cleanup is attempted after failure.
    for command in commands:
        assert "get" in command
        operation = command.index("get")
        assert command[operation + 1:operation + 3] == [
            "namespace", "oss-factory-jobs",
        ]
        assert not set(command) & {
            "apply", "create", "delete", "patch", "replace",
            "exec", "run", "scale", "label", "annotate",
        }
