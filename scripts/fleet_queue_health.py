"""Reconcile Kueue admission with MBP health using optimistic API writes."""
import json

QUEUES = ("lanes", "bench-lanes")
OWNER = "z0.dev/fleet-health-queue-hold"
OWNED = "mbp:None:v1"


def node_blocked(node):
    """Node readiness gate shared by admission, source staging and overflow."""
    conditions = {c["type"]: c["status"] for c in node.get("status", {}).get("conditions", [])}
    return (node.get("spec", {}).get("unschedulable", False)
            or conditions.get("Ready") != "True"
            or any(conditions.get(c) != "False" for c in
                   ("DiskPressure", "MemoryPressure", "PIDPressure"))
            or any(t.get("effect") in ("NoSchedule", "NoExecute")
                   for t in node.get("spec", {}).get("taints", [])))


def recovery_ready(kc):
    """Fresh Kubernetes gate for fleet-owned uncordon, ignoring only its cordon taint."""
    node = json.loads(kc("get", "node", "mbp", "-o", "json").stdout)
    conditions = {c["type"]: c["status"] for c in node.get("status", {}).get("conditions", [])}
    return (
        node.get("metadata", {}).get("annotations", {}).get("z0.dev/cordoned-by") == "fleet-health"
        and conditions.get("Ready") == "True"
        and all(conditions.get(c) == "False" for c in
                ("DiskPressure", "MemoryPressure", "PIDPressure"))
        and not any(t.get("effect") in ("NoSchedule", "NoExecute")
                    and not (t.get("key") == "node.kubernetes.io/unschedulable"
                             and t.get("effect") == "NoSchedule")
                    for t in node.get("spec", {}).get("taints", []))
    )


def reconcile(kc, unhealthy=False):
    """Raise on transport/conflict errors; never claim a hold was applied on failure."""
    errors = []
    try:
        node = json.loads(kc("get", "node", "mbp", "-o", "json").stdout)
    except Exception as exc:
        # If node reads fail but queue writes still work, close admission anyway.
        node = {}
        errors.append(f"mbp node health unavailable: {exc}")
    blocked = unhealthy or node_blocked(node)
    result = {}
    for name in QUEUES:
        try:
            queue = json.loads(kc("get", "clusterqueue", name, "-o", "json").stdout)
            meta = queue["metadata"]
            annotations = meta.get("annotations") or {}
            spec = queue.get("spec", {})
            policy = spec.get("stopPolicy", "None")
            owned = annotations.get(OWNER) == OWNED
            patch = [{"op": "test", "path": "/metadata/resourceVersion", "value": meta["resourceVersion"]}]
            if blocked and policy == "None":
                updated = {**annotations, OWNER: OWNED}
                patch.extend([
                    {"op": "add", "path": "/metadata/annotations", "value": updated},
                    {"op": "add", "path": "/spec/stopPolicy", "value": "Hold"},
                ])
            elif not blocked and owned and policy == "Hold":
                patch.extend([
                    {"op": "add", "path": "/spec/stopPolicy", "value": "None"},
                    {"op": "remove", "path": "/metadata/annotations/" + OWNER.replace("/", "~1")},
                ])
            elif owned and policy != "Hold":
                # An operator changed policy: abandon ownership, including HoldAndDrain.
                patch.append({"op": "remove", "path": "/metadata/annotations/" + OWNER.replace("/", "~1")})
            if len(patch) > 1:
                kc("patch", "clusterqueue", name, "--type=json", "-p", json.dumps(patch))
            result[name] = "Hold" if blocked and policy == "None" else "None" if not blocked and owned and policy == "Hold" else policy
        except Exception as exc:
            errors.append(f"{name}: {exc}")
    if errors:
        raise RuntimeError("Kueue health reconciliation failed: " + "; ".join(errors))
    return result


# Lane memory follows what the host already uses outside Kueue. The static budget in
# config/k3s/kueue/queues.yaml assumed an idle host (it subtracts the frozen idle OS
# baseline and Shmem); the dash-e2e army and the kind/docker cluster run beside Kueue,
# so a 9 GiB job that fit the static quota starved kubelet (2026-11-05). Subtract the
# resident memory of non-Kueue workloads; Kueue's own pods never shrink their quota.
STATIC_MEMORY = 10441814016
IDLE_BASELINE = 2837270528 + 1204051968  # frozen idle OS + Shmem, already in STATIC_MEMORY
KUEUE_NAMESPACES = ("fleet-mbp", "lanes")
MIN_CHANGE = 256 * 1024 ** 2


def lane_memory_quota(summary, host_probe):
    """Host use comes from fleet-health's own probe (MemTotal - MemAvailable): kubelet's node figure on
    mbp omits user.slice and docker (1.88 GiB reported vs 9.6 GiB used, 2026-11-05). Kueue pods come
    from kubelet's per-pod stats, which are exact."""
    used = (int(host_probe["mem_total_mb"]) - int(host_probe["mem_available_mb"])) * 1024 ** 2
    kueue_ws = sum((p.get("memory") or {}).get("workingSetBytes") or 0 for p in summary.get("pods", [])
                   if p["podRef"]["namespace"] in KUEUE_NAMESPACES)
    outside = max(0, used - kueue_ws - IDLE_BASELINE)
    return max(0, STATIC_MEMORY - outside)


def reconcile_lane_memory(kc, host_probe):
    """Set lanes' node-mbp memory nominalQuota; raise and change nothing if stats are unreadable."""
    summary = json.loads(kc("get", "--raw", "/api/v1/nodes/mbp/proxy/stats/summary").stdout)
    want = lane_memory_quota(summary, host_probe)
    queue = json.loads(kc("get", "clusterqueue", "lanes", "-o", "json").stdout)
    for g, group in enumerate(queue["spec"]["resourceGroups"]):
        for f, flavor in enumerate(group["flavors"]):
            if flavor["name"] != "node-mbp":
                continue
            for r, res in enumerate(flavor["resources"]):
                if res["name"] != "memory":
                    continue
                have = int(res["nominalQuota"]) if str(res["nominalQuota"]).isdigit() else None
                if have is not None and abs(want - have) < MIN_CHANGE:
                    return {"memory_quota": have, "changed": False}
                kc("patch", "clusterqueue", "lanes", "--type=json", "-p", json.dumps([
                    {"op": "test", "path": "/metadata/resourceVersion", "value": queue["metadata"]["resourceVersion"]},
                    {"op": "replace", "path": f"/spec/resourceGroups/{g}/flavors/{f}/resources/{r}/nominalQuota",
                     "value": str(want)}]))
                return {"memory_quota": want, "changed": True, "was": have}
    raise RuntimeError("lanes has no node-mbp memory quota")
