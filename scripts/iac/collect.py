#!/usr/bin/env python3
"""Read-only live-state collector for .files machine IaC.

Phase 1 intentionally observes only. It never installs packages, mutates
services, edits /etc, changes mounts, or reads secret-bearing credential files.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import platform
import socket
import subprocess
import sys
from typing import Any

SCHEMA_VERSION = 1

# Commands here must stay observational. Keep explicit argv lists so future
# changes are reviewable and testable.
COMMANDS: dict[str, list[str]] = {
    "lsblk": [
        "lsblk", "--json", "--bytes",
        "-o", "NAME,KNAME,PATH,SIZE,TYPE,FSTYPE,FSVER,LABEL,UUID,PARTUUID,MOUNTPOINTS,MODEL,SERIAL,WWN,ROTA",
    ],
    "findmnt": ["findmnt", "--json", "-o", "SOURCE,TARGET,FSTYPE,OPTIONS"],
    "swapon": ["swapon", "--show", "--json", "--bytes"],
    "zram": ["zramctl", "--json"],
    "pacman_explicit": ["pacman", "-Qqe"],
    "pacman_foreign": ["pacman", "-Qqm"],
    "flatpak_apps": ["flatpak", "list", "--app", "--columns=application"],
    "system_services_enabled": [
        "systemctl", "list-unit-files", "--type=service", "--state=enabled",
        "--no-legend", "--no-pager", "--plain",
    ],
    "user_services_enabled": [
        "systemctl", "--user", "list-unit-files", "--type=service", "--state=enabled",
        "--no-legend", "--no-pager", "--plain",
    ],
    "system_timers": [
        "systemctl", "list-timers", "--all", "--no-legend", "--no-pager", "--plain",
    ],
    "user_timers": [
        "systemctl", "--user", "list-timers", "--all", "--no-legend", "--no-pager", "--plain",
    ],
    "lscpu": ["lscpu", "-J"],
    "nvidia": [
        "nvidia-smi",
        "--query-gpu=name,uuid,memory.total,driver_version",
        "--format=csv,noheader,nounits",
    ],
}

JSON_COMMANDS = {"lsblk", "findmnt", "swapon", "zram", "lscpu"}
LINE_COMMANDS = set(COMMANDS) - JSON_COMMANDS

# We intentionally do not read credential files or dump process environments.
FORBIDDEN_PATH_PARTS = {
    "auth.json", ".env", "credentials", "login data", "cookies",
    ".ssh", ".gnupg", "keyring",
}


def _run(argv: list[str], timeout: float = 8.0) -> dict[str, Any]:
    """Run one read-only command and return a structured result."""
    try:
        proc = subprocess.run(
            argv,
            check=False,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=os.environ.copy(),
        )
    except FileNotFoundError:
        return {"available": False, "returncode": None, "stdout": "", "stderr": "command not found"}
    except subprocess.TimeoutExpired:
        return {"available": True, "returncode": None, "stdout": "", "stderr": "timeout"}

    return {
        "available": True,
        "returncode": proc.returncode,
        "stdout": proc.stdout,
        "stderr": proc.stderr.strip()[:1000],
    }


def _json_result(result: dict[str, Any]) -> dict[str, Any]:
    out = {k: result[k] for k in ("available", "returncode", "stderr")}
    raw = result.get("stdout", "")
    if result.get("returncode") == 0 and raw.strip():
        try:
            out["data"] = json.loads(raw)
            return out
        except json.JSONDecodeError as exc:
            out["parse_error"] = str(exc)
    out["data"] = None
    return out


def _lines_result(result: dict[str, Any]) -> dict[str, Any]:
    return {
        "available": result["available"],
        "returncode": result["returncode"],
        "stderr": result["stderr"],
        "data": [line.strip() for line in result.get("stdout", "").splitlines() if line.strip()],
    }


def _read_os_release() -> dict[str, str]:
    path = Path("/etc/os-release")
    if not path.is_file():
        return {}
    out: dict[str, str] = {}
    for line in path.read_text(errors="replace").splitlines():
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key] = value.strip().strip('"')
    return out


def _managed_symlinks(repo_root: Path) -> list[dict[str, str]]:
    """Find a small, bounded set of user symlinks that resolve into this repo."""
    home = Path.home()
    roots = [
        home / ".zshrc",
        home / ".tmux.conf",
        home / ".gitconfig",
        home / ".config" / "hypr",
        home / ".config" / "nvim",
        home / ".config" / "noctalia",
    ]
    found: list[dict[str, str]] = []

    def consider(path: Path) -> None:
        try:
            if not path.is_symlink():
                return
            target = path.resolve(strict=False)
            target.relative_to(repo_root)
        except (OSError, ValueError):
            return
        found.append({"path": str(path), "target": str(target)})

    for root in roots:
        if root.is_symlink():
            consider(root)
            continue
        if root.is_dir():
            # Bounded recursion avoids turning ~/.config into a home-directory crawl.
            for base, dirs, files in os.walk(root):
                depth = len(Path(base).relative_to(root).parts)
                if depth >= 2:
                    dirs[:] = []
                for name in dirs + files:
                    consider(Path(base) / name)

    return sorted(found, key=lambda item: item["path"])


def collect(repo_root: Path) -> dict[str, Any]:
    observed: dict[str, Any] = {
        "schema_version": SCHEMA_VERSION,
        "collected_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "host": {
            "hostname": socket.gethostname(),
            "platform": platform.platform(),
            "machine": platform.machine(),
            "kernel_release": platform.release(),
            "os_release": _read_os_release(),
        },
        "managed_symlinks": _managed_symlinks(repo_root),
        "observations": {},
        "safety": {
            "mode": "read-only",
            "secret_values_collected": False,
            "forbidden_path_parts": sorted(FORBIDDEN_PATH_PARTS),
        },
    }

    for name, argv in COMMANDS.items():
        raw = _run(argv)
        observed["observations"][name] = (
            _json_result(raw) if name in JSON_COMMANDS else _lines_result(raw)
        )

    return observed


def default_output(hostname: str) -> Path:
    state_root = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local" / "state"))
    return state_root / "dotfiles" / "iac" / hostname / "observed.json"


def write_observed(data: dict[str, Any], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    temp = output.with_suffix(output.suffix + ".tmp")
    temp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")
    temp.replace(output)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="iac", description="Read-only .files machine-IaC tools")
    sub = parser.add_subparsers(dest="command", required=True)

    collect_p = sub.add_parser("collect", help="collect read-only live state")
    collect_p.add_argument("--stdout", action="store_true", help="print JSON instead of writing state file")
    collect_p.add_argument("--output", type=Path, help="explicit output path")

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    repo_root = Path(__file__).resolve().parents[2]

    if args.command == "collect":
        data = collect(repo_root)
        if args.stdout:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        output = args.output or default_output(data["host"]["hostname"])
        write_observed(data, output)
        print(output)
        return 0

    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())
