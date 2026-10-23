#!/usr/bin/env python3
"""Read-only desired-vs-observed planner for the .files fleet manifest."""

from __future__ import annotations

import argparse
import os
import re
import shutil
import socket
import subprocess
import json
from pathlib import Path
import sys
from typing import Any
import tomllib


def load_toml(path: Path) -> dict[str, Any]:
    return tomllib.loads(path.read_text())


def resolve_host(fleet: dict[str, Any], hostname: str) -> tuple[str, dict[str, Any]]:
    matches = []
    for host_id, cfg in (fleet.get("hosts") or {}).items():
        names = cfg.get("match_hostnames") or []
        if hostname == host_id or hostname in names:
            matches.append((host_id, cfg))
    if len(matches) != 1:
        raise ValueError(f"hostname {hostname!r} matched {len(matches)} fleet hosts")
    return matches[0]


def _package_name(entry: Any, platform: str) -> str:
    if isinstance(entry, str):
        return entry
    if isinstance(entry, dict):
        value = entry.get(platform)
        if isinstance(value, str):
            return value
        if isinstance(value, dict) and isinstance(value.get("name"), str):
            return value["name"]
    raise ValueError(f"cannot resolve package override for {platform}: {entry!r}")


def desired_packages(packages: dict[str, Any], groups: list[str], platform: str = "arch") -> set[str]:
    overrides = packages.get("overrides") or {}
    wanted: set[str] = set()
    for group in groups:
        section = packages.get(group)
        if not isinstance(section, dict):
            raise ValueError(f"unknown package group {group!r}")
        for canonical in section.get("packages") or []:
            override = overrides.get(canonical)
            wanted.add(_package_name(override, platform) if override is not None else canonical)
    return wanted


def _unit_names(lines: list[str]) -> set[str]:
    out = set()
    for line in lines:
        fields = line.split()
        if fields:
            out.add(fields[0])
    return out


def build_plan(fleet: dict[str, Any], packages: dict[str, Any], observed: dict[str, Any]) -> dict[str, Any]:
    hostname = observed["host"]["hostname"]
    host_id, host = resolve_host(fleet, hostname)
    obs = observed.get("observations") or {}

    installed = set((obs.get("pacman_explicit") or {}).get("data") or [])
    installed |= set((obs.get("pacman_foreign") or {}).get("data") or [])
    groups = list(host.get("package_groups") or [])
    wanted = desired_packages(packages, groups)

    enabled_system = _unit_names((obs.get("system_services_enabled") or {}).get("data") or [])
    enabled_user = _unit_names((obs.get("user_services_enabled") or {}).get("data") or [])
    enabled_system_timers = _unit_names((obs.get("system_timers_enabled") or {}).get("data") or [])
    enabled_system_sockets = _unit_names((obs.get("system_sockets_enabled") or {}).get("data") or [])
    enabled_user_timers = _unit_names((obs.get("user_timers_enabled") or {}).get("data") or [])

    desired_system = set(host.get("system_services") or [])
    desired_user = set(host.get("user_services") or [])
    desired_system_timers = set(host.get("system_timers") or [])
    desired_system_sockets = set(host.get("system_sockets") or [])
    desired_user_timers = set(host.get("user_timers") or [])

    return {
        "schema_version": 1,
        "host_id": host_id,
        "hostname": hostname,
        "status": "DRIFT" if (
            wanted - installed
            or desired_system - enabled_system
            or desired_user - enabled_user
            or desired_system_timers - enabled_system_timers
            or desired_system_sockets - enabled_system_sockets
            or desired_user_timers - enabled_user_timers
        ) else "MATCH",
        "packages": {
            "groups": groups,
            "missing": sorted(wanted - installed),
            "observed_unmanaged_count": len(installed - wanted),
        },
        "system_services": {
            "missing_enabled": sorted(desired_system - enabled_system),
            "observed_unmanaged_count": len(enabled_system - desired_system),
        },
        "user_services": {
            "missing_enabled": sorted(desired_user - enabled_user),
            "observed_unmanaged_count": len(enabled_user - desired_user),
        },
        "system_timers": {
            "missing_enabled": sorted(desired_system_timers - enabled_system_timers),
            "observed_unmanaged_count": len(enabled_system_timers - desired_system_timers),
        },
        "system_sockets": {
            "missing_enabled": sorted(desired_system_sockets - enabled_system_sockets),
            "observed_unmanaged_count": len(enabled_system_sockets - desired_system_sockets),
        },
        "user_timers": {
            "missing_enabled": sorted(desired_user_timers - enabled_user_timers),
            "observed_unmanaged_count": len(enabled_user_timers - desired_user_timers),
        },
        "notes": [
            "Observed unmanaged items are informational, not removal candidates.",
            "No mutation is performed by plan.",
        ],
    }



# Read-only projection of z0's registry-owned native binding health. The registry
# owns recipes and the doctor format; this planner never applies a binding.
Z0_HARNESSES = frozenset(("hermes", "claude", "codex", "omp"))
Z0_STATUSES = frozenset(("MATCH", "DRIFT", "UNKNOWN", "ERROR"))
_Z0_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}\Z")
_Z0_COMPONENT = re.compile(r"[a-z][a-z0-9-]{0,63}\Z")
_Z0_MAX_OUTPUT = 512 * 1024
_Z0_MAX_RECORDS = 128


def _z0_selection(section: dict[str, Any]) -> list[str] | None:
    """Absent is unknown; an explicit empty list means none."""
    if "components" not in section:
        return None
    value = section["components"]
    if (not isinstance(value, list)
            or any(not isinstance(cid, str) or not _Z0_COMPONENT.fullmatch(cid)
                   for cid in value)
            or len(value) != len(set(value))):
        raise ValueError("invalid z0 components selection")
    return list(value)


def validate_z0_intent(intent: Any) -> None:
    """Validate .files shape only; z0 validates IDs against its own registry."""
    if not isinstance(intent, dict) or set(intent) - {"components", "harnesses"}:
        raise ValueError("invalid z0 host intent")
    _z0_selection(intent)
    harnesses = intent.get("harnesses", {})
    if not isinstance(harnesses, dict) or set(harnesses) - Z0_HARNESSES:
        raise ValueError("invalid z0 harness IDs")
    for hid, section in harnesses.items():
        allowed = {"components", "profiles"} if hid == "hermes" else {"components"}
        if not isinstance(section, dict) or set(section) - allowed:
            raise ValueError("invalid z0 harness intent")
        _z0_selection(section)
        profiles = section.get("profiles", {})
        if not isinstance(profiles, dict):
            raise ValueError("invalid z0 native profiles")
        for name, selection in profiles.items():
            if (not isinstance(name, str) or not _Z0_TOKEN.fullmatch(name)
                    or not isinstance(selection, dict) or set(selection) - {"components"}):
                raise ValueError("invalid z0 native profile intent")
            _z0_selection(selection)


def z0_components_for(
    fleet: dict[str, Any], hostname: str, harness: str, profile: str = "global"
) -> list[str] | None:
    """Mirror the z0 Intent precedence, without copying registry definitions."""
    if harness not in Z0_HARNESSES:
        raise ValueError("unknown z0 harness")
    _, host = resolve_host(fleet, hostname)
    intent = host.get("z0_components")
    if intent is None:
        return None
    validate_z0_intent(intent)
    harness_spec = intent.get("harnesses", {}).get(harness, {})
    profile_spec = harness_spec.get("profiles", {}).get(profile, {})
    for selection in (profile_spec, harness_spec, intent):
        selected = _z0_selection(selection)
        if selected is not None:
            return selected
    return None


def _z0_unavailable(host_id: str | None, reason: str, status: str = "UNKNOWN") -> dict[str, Any]:
    return {
        "status": status, "available": False, "healthy": False,
        "host_id": host_id, "configs": [], "findings": [], "reason": reason,
    }


def _z0_token(value: Any) -> str | None:
    # Only structured identifiers make it into the projection. Paths, command
    # arguments, header values, environment and arbitrary error text never do.
    return value if isinstance(value, str) and _Z0_TOKEN.fullmatch(value) else None


def _z0_ids(value: Any) -> list[str] | None:
    if value is None:
        return None
    if (not isinstance(value, list) or len(value) > _Z0_MAX_RECORDS
            or any(not isinstance(cid, str) or not _Z0_COMPONENT.fullmatch(cid)
                   for cid in value)):
        raise ValueError("invalid doctor component IDs")
    return list(value)


def _z0_findings(raw: Any) -> list[dict[str, str]]:
    if raw is None:
        return []
    if not isinstance(raw, list) or len(raw) > _Z0_MAX_RECORDS:
        raise ValueError("invalid doctor findings")
    out: list[dict[str, str]] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ValueError("invalid doctor finding record")
        # In particular, never forward text, path, env, args, URL or config.
        safe = {key: token for key in ("kind", "code", "component", "harness", "profile")
                if (token := _z0_token(item.get(key))) is not None}
        out.append(safe or {"kind": "unclassified"})
    return out


def _z0_configs(raw: Any) -> list[dict[str, Any]]:
    if not isinstance(raw, list) or not 0 < len(raw) <= _Z0_MAX_RECORDS:
        raise ValueError("doctor supplied no bounded configs")
    out: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("harness") not in Z0_HARNESSES:
            raise ValueError("invalid doctor config")
        status = item.get("status")
        if status is not None and status not in Z0_STATUSES:
            status = "UNKNOWN"
        # A missing or null desired selection stays unknown, even if installed.
        desired = _z0_ids(item.get("desired"))
        bound = _z0_ids(item.get("bound", item.get("configured")))
        out.append({
            "harness": item["harness"],
            "profile": _z0_token(item.get("profile")) or "unidentified",
            "status": status,
            "desired": desired,
            "configured": bound,
            "findings": _z0_findings(item.get("findings")),
        })
    return out


def z0_binding_health(
    fleet: dict[str, Any], fleet_path: Path, observed_hostname: str,
    *, local_hostname: str | None = None, executable: str | None = None,
    runner: Any = None,
) -> dict[str, Any]:
    """Probe only the local, unambiguously resolved host via bounded z0 doctor.

    No remote access, no applying, no native config writes, no raw stdout/stderr
    in health results. This does not inspect a remote observed snapshot.
    """
    try:
        host_id, host = resolve_host(fleet, observed_hostname)
        intent = host.get("z0_components")
        if intent is None:
            return _z0_unavailable(host_id, "selection-missing")
        validate_z0_intent(intent)
        harnesses = intent.get("harnesses", {})
        selected = (_z0_selection(intent) is not None
                    or any(_z0_selection(h) is not None
                           or any(_z0_selection(p) is not None
                                  for p in h.get("profiles", {}).values())
                           for h in harnesses.values()))
        if not selected:
            return _z0_unavailable(host_id, "selection-missing")
        actual_id, _ = resolve_host(fleet, local_hostname or socket.gethostname())
        if actual_id != host_id:
            return _z0_unavailable(host_id, "remote-host-not-probed")
    except ValueError:
        return _z0_unavailable(None, "unresolved-host-or-intent", "ERROR")

    if not fleet_path.is_file():
        return _z0_unavailable(host_id, "fleet-manifest-unavailable", "ERROR")
    binary = executable or os.environ.get("Z0_BIN", "z0")
    resolved = shutil.which(binary)
    if not resolved:
        return _z0_unavailable(host_id, "z0-executable-unavailable")
    argv = [resolved, "doctor", "--bindings", "--json", "--host-profile", str(fleet_path.resolve())]
    try:
        proc = (runner or subprocess.run)(
            argv, capture_output=True, text=True, stdin=subprocess.DEVNULL,
            timeout=20, check=False,
        )
    except subprocess.TimeoutExpired:
        return _z0_unavailable(host_id, "doctor-timeout", "ERROR")
    except OSError:
        return _z0_unavailable(host_id, "doctor-execution-failed", "ERROR")
    if proc.returncode not in (0, 1):
        return _z0_unavailable(host_id, "doctor-exit-failure", "ERROR")
    if not isinstance(proc.stdout, str) or len(proc.stdout) > _Z0_MAX_OUTPUT:
        return _z0_unavailable(host_id, "doctor-output-unavailable", "ERROR")
    try:
        report = json.loads(proc.stdout)
    except (ValueError, TypeError):
        return _z0_unavailable(host_id, "doctor-malformed-json", "ERROR")
    if not isinstance(report, dict) or report.get("status") not in Z0_STATUSES:
        return _z0_unavailable(host_id, "doctor-unknown-status")
    reported_status = report["status"]
    if proc.returncode == 1 and reported_status != "DRIFT":
        return _z0_unavailable(host_id, "doctor-exit-status-conflict", "ERROR")
    report_host = report.get("host", report.get("hostname"))
    if isinstance(report_host, dict):
        report_host = report_host.get("logical_host") or report_host.get("hostname")
    if not isinstance(report_host, str):
        return _z0_unavailable(host_id, "doctor-host-unknown")
    try:
        report_host_id, _ = resolve_host(fleet, report_host)
    except ValueError:
        return _z0_unavailable(host_id, "doctor-host-unresolved")
    if report_host_id != host_id:
        return _z0_unavailable(host_id, "doctor-host-mismatch", "ERROR")
    try:
        configs = _z0_configs(report.get("configs"))
        findings = _z0_findings(report.get("findings"))
    except ValueError:
        return _z0_unavailable(host_id, "doctor-malformed-schema", "ERROR")

    # A MATCH cannot swallow unknown profiles or contradictory native records.
    severity = {"MATCH": 0, "DRIFT": 1, "UNKNOWN": 2, "ERROR": 3}
    status = reported_status
    for item in configs:
        if item["desired"] is None:
            status = max((status, "UNKNOWN"), key=severity.get)
        if item["status"] is not None:
            status = max((status, item["status"]), key=severity.get)
        for finding in item["findings"]:
            if finding.get("kind") in {"missing-desired-component", "binding-mismatch",
                                       "config-changed-during-observation"}:
                status = max((status, "DRIFT"), key=severity.get)
    for finding in findings:
        if finding.get("kind") in {"missing-desired-component", "binding-mismatch",
                                   "config-changed-during-observation"}:
            status = max((status, "DRIFT"), key=severity.get)
    return {
        "status": status, "available": status in {"MATCH", "DRIFT"},
        "healthy": status == "MATCH", "host_id": host_id,
        "configs": configs, "findings": findings,
        "reason": {
            "MATCH": "bindings-match", "DRIFT": "bindings-differ",
            "UNKNOWN": "doctor-reported-unknown", "ERROR": "doctor-reported-error",
        }[status],
    }


def default_observed(hostname: str) -> Path:
    import os
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state / "dotfiles" / "iac" / hostname / "observed.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iac plan")
    parser.add_argument("--observed", type=Path)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--z0-bindings", action="store_true", help="read-only local z0 doctor binding health")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    repo = Path(__file__).resolve().parents[2]
    fleet = load_toml(repo / "fleet.toml")
    packages = load_toml(repo / "packages" / "packages.toml")

    observed_path = args.observed
    if observed_path is None:
        import socket
        observed_path = default_observed(socket.gethostname())
    observed = json.loads(observed_path.read_text())

    result = build_plan(fleet, packages, observed)
    if args.z0_bindings:
        result["z0_bindings"] = z0_binding_health(fleet, repo / "fleet.toml", observed["host"]["hostname"])
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} host={result['host_id']} hostname={result['hostname']}")
        for section in ("packages", "system_services", "user_services", "system_timers", "system_sockets", "user_timers"):
            data = result[section]
            missing = data.get("missing") or data.get("missing_enabled") or []
            print(f"{section}: missing={len(missing)} unmanaged_observed={data['observed_unmanaged_count']}")
            for item in missing:
                print(f"  MISSING {item}")
    if args.z0_bindings:
        z0 = result["z0_bindings"]
        if not args.json:
            print(f"z0_bindings: {z0['status']} available={z0['available']} healthy={z0['healthy']} "
                  f"configs={len(z0['configs'])} findings={len(z0['findings'])} reason={z0['reason']}")
        if z0["status"] in {"UNKNOWN", "ERROR"}:
            return 2
        if z0["status"] == "DRIFT":
            return 1
    return 1 if result["status"] == "DRIFT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
