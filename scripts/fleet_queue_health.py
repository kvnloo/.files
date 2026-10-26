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
