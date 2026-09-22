#!/usr/bin/env python3
"""Validate nested E2E output lifecycle, sabotage, rollback, and cleanup evidence."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

LEGACY_NAME = "hyprland.legacy.conf"


def _load(path: Path, default=None):
    if not path.exists():
        return default
    text = path.read_text()
    if not text.strip():
        return default
    if path.suffix == ".json":
        return json.loads(text)
    return text


def _lifecycle_ok(payload: dict | None, name: str) -> tuple[bool, str]:
    if not isinstance(payload, dict):
        return False, f"{name} lifecycle missing"
    if payload.get("name") != name:
        return False, f"{name} name mismatch: {payload.get('name')}"
    for key in ("added", "removed", "recovered"):
        if payload.get(key) is not True:
            return False, f"{name} {key} is not true"
    if payload.get("semantics_verified") is not True:
        return False, f"{name} runtime semantics are not verified"
    if name == "E2E-INNER" and payload.get("window_rule_verified") is not True:
        return False, f"{name} window rule is not verified"
    if payload.get("control_path") != "native-eval":
        return False, f"{name} control path is not native-eval"
    return True, ""


def compare(evidence: Path) -> dict:
    failures: list[str] = []
    controller = _load(evidence / "controller-lifecycle.json", {})
    phone = _load(evidence / "phone-lifecycle.json", {})
    controller_data = controller if isinstance(controller, dict) else {}
    phone_data = phone if isinstance(phone, dict) else {}
    sabotage = _load(evidence / "sabotage.json", {})
    rollback = _load(evidence / "rollback.json", {})
    result = _load(evidence / "result.json", {})
    selection = str(_load(evidence / "live-selection.txt", "") or "")
    systeminfo = str(_load(evidence / "lua-systeminfo.txt", "") or "")
    errors = str(_load(evidence / "lua-configerrors.txt", "") or "")

    ok, reason = _lifecycle_ok(controller_data, "E2E-INNER")
    if not ok:
        failures.append(reason)
    ok, reason = _lifecycle_ok(phone_data, "PHONE")
    if not ok:
        failures.append(reason)

    sabotage_ok = True
    if not isinstance(sabotage, dict):
        sabotage_ok = False
        failures.append("sabotage evidence missing")
    else:
        for kind in ("monitor", "window", "bind", "source"):
            row = sabotage.get(kind) or {}
            if row.get("visible") is not True or row.get("recovered") is not True:
                sabotage_ok = False
                failures.append(f"sabotage {kind} not visible+recovered")

    rollback_proven = bool(isinstance(rollback, dict) and rollback.get("proven") is True)
    target = str((rollback or {}).get("target", ""))
    if not rollback_proven:
        failures.append("rollback not proven")
    if LEGACY_NAME not in target and LEGACY_NAME not in selection:
        failures.append("rollback target is not hyprland.legacy.conf")

    cleanup = bool(isinstance(result, dict) and result.get("cleanup_complete") is True)
    if not cleanup:
        failures.append("cleanup_complete is not true")

    lua_login = LEGACY_NAME not in selection
    if lua_login:
        failures.append("login selection is not hyprland.legacy.conf")

    if "configProvider: lua" not in systeminfo:
        failures.append("nested lua configProvider missing")
    if errors.strip():
        failures.append("nested lua configerrors are non-empty")

    isolation_ok = True
    snapshots = []
    for axis in ("before", "during", "after"):
        payload = _load(evidence / f"host-isolation-{axis}.json")
        if not isinstance(payload, dict):
            isolation_ok = False
            failures.append(f"host isolation {axis} missing")
            continue
        mapping = payload.get("physical_monitor_workspaces") or {}
        snapshots.append(
            {name: (row or {}).get("workspace") for name, row in mapping.items()}
        )
    if isolation_ok and snapshots and not all(item == snapshots[0] for item in snapshots):
        isolation_ok = False
        failures.append("host physical workspace mapping mutated")

    report = {
        "ok": not failures,
        "failures": failures,
        "controller": {
            "added": bool(controller_data.get("added")),
            "removed": bool(controller_data.get("removed")),
            "recovered": bool(controller_data.get("recovered")),
            "semantics_verified": bool(controller_data.get("semantics_verified")),
            "window_rule_verified": bool(controller_data.get("window_rule_verified")),
            "control_path": str(controller_data.get("control_path", "")),
        },
        "phone": {
            "added": bool(phone_data.get("added")),
            "removed": bool(phone_data.get("removed")),
            "recovered": bool(phone_data.get("recovered")),
            "semantics_verified": bool(phone_data.get("semantics_verified")),
            "control_path": str(phone_data.get("control_path", "")),
        },
        "sabotage": {"all_recovered": sabotage_ok},
        "rollback": {"proven": rollback_proven, "target": target},
        "cleanup_complete": cleanup,
        "lua_active_for_login": lua_login,
        "host_isolation": {"untouched": isolation_ok},
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--evidence", type=Path, required=True)
    parser.add_argument("--write", type=Path)
    args = parser.parse_args()
    report = compare(args.evidence)
    dest = args.write or (args.evidence / "lifecycle-report.json")
    dest.write_text(json.dumps(report, indent=2) + "\n")
    if not report["ok"]:
        print("lifecycle proof failed: " + "; ".join(report["failures"]), flush=True)
        return 1
    print("nested E2E lifecycle, sabotage, rollback, and cleanup: ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
