#!/usr/bin/env python3
"""Configure KDE Connect to discover every peer through Tailscale.

--start also launches kdeconnectd when it is installed and not running.
--incoming DIR sets the share plugin's receive folder for every paired device (created if absent).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import socket
import subprocess
import sys
from pathlib import Path

CONFIG = Path.home() / ".config/kdeconnect/config"


def tailnet_ipv4() -> list[str]:
    result = subprocess.run(
        ["tailscale", "status", "--json"],
        check=True,
        capture_output=True,
        text=True,
    )
    status = json.loads(result.stdout)
    addresses: set[str] = set()
    for peer in status.get("Peer", {}).values():
        for address in peer.get("TailscaleIPs", []):
            if ":" not in address:
                addresses.add(address)
                break
    return sorted(addresses)


def configure() -> int:
    addresses = tailnet_ipv4()
    CONFIG.parent.mkdir(parents=True, exist_ok=True)
    values: dict[str, str] = {}
    if CONFIG.exists():
        for line in CONFIG.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";", "[")) or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key] = value
    values.setdefault("name", socket.gethostname())
    values["customDevices"] = ",".join(addresses)
    CONFIG.write_text("".join(f"{key}={values[key]}\n" for key in sorted(values)))
    os.chmod(CONFIG, 0o600)
    print(f"KDE Connect discovery configured for {len(addresses)} tailnet peers")
    return len(addresses)


def root_keys(path: Path) -> dict[str, str]:
    """QSettings root keys (no INI group), as KDE Connect writes them."""
    values: dict[str, str] = {}
    if path.exists():
        for line in path.read_text().splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith(("#", ";", "[")) or "=" not in stripped:
                continue
            key, value = stripped.split("=", 1)
            values[key] = value
    return values


def set_incoming(directory: Path) -> int:
    """Point every paired device's share plugin at one receive folder; returns the device count."""
    directory = directory.expanduser()
    directory.mkdir(parents=True, exist_ok=True)
    devices = [path for path in sorted(CONFIG.parent.iterdir())
               if path.is_dir() and re.fullmatch(r"[0-9a-f_]{16,64}", path.name)] if CONFIG.parent.is_dir() else []
    for device in devices:
        config = device / "kdeconnect_share/config"
        config.parent.mkdir(parents=True, exist_ok=True)
        values = root_keys(config)
        values["incoming_path"] = str(directory)
        config.write_text("".join(f"{key}={values[key]}\n" for key in sorted(values)))
        os.chmod(config, 0o600)
    print(f"KDE Connect incoming folder set for {len(devices)} paired devices")
    return len(devices)


def start_daemon() -> None:
    if subprocess.run(["pgrep", "-x", "kdeconnectd"], capture_output=True).returncode == 0:
        return
    daemon = shutil.which("kdeconnectd")
    if daemon is None and Path("/usr/lib/kdeconnectd").is_file():
        daemon = "/usr/lib/kdeconnectd"
    if daemon is None:
        return
    subprocess.Popen(
        [daemon],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def main() -> int:
    try:
        configure()
    except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError) as error:
        print(f"unable to configure KDE Connect discovery: {error}", file=sys.stderr)
        return 1
    if "--incoming" in sys.argv:
        index = sys.argv.index("--incoming") + 1
        if index >= len(sys.argv):
            print("--incoming needs a directory", file=sys.stderr)
            return 2
        set_incoming(Path(sys.argv[index]))
    if "--start" in sys.argv:
        start_daemon()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
