#!/usr/bin/env python3
"""Read-only desired-vs-observed planner for the .files fleet manifest."""

from __future__ import annotations

import argparse
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

    desired_system = set(host.get("system_services") or [])
    desired_user = set(host.get("user_services") or [])

    return {
        "schema_version": 1,
        "host_id": host_id,
        "hostname": hostname,
        "status": "DRIFT" if (
            wanted - installed or desired_system - enabled_system or desired_user - enabled_user
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
        "notes": [
            "Observed unmanaged items are informational, not removal candidates.",
            "No mutation is performed by plan.",
        ],
    }


def default_observed(hostname: str) -> Path:
    import os
    state = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state / "dotfiles" / "iac" / hostname / "observed.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="iac plan")
    parser.add_argument("--observed", type=Path)
    parser.add_argument("--json", action="store_true")
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
    if args.json:
        print(json.dumps(result, indent=2, sort_keys=True))
    else:
        print(f"{result['status']} host={result['host_id']} hostname={result['hostname']}")
        for section in ("packages", "system_services", "user_services"):
            data = result[section]
            missing = data.get("missing") or data.get("missing_enabled") or []
            print(f"{section}: missing={len(missing)} unmanaged_observed={data['observed_unmanaged_count']}")
            for item in missing:
                print(f"  MISSING {item}")
    return 1 if result["status"] == "DRIFT" else 0


if __name__ == "__main__":
    raise SystemExit(main())
