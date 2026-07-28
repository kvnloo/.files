#!/usr/bin/env python3
"""Configure KDE Connect to discover every peer through Tailscale."""

from __future__ import annotations

import configparser
import json
import os
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
    parser = configparser.ConfigParser(interpolation=None)
    parser.optionxform = str
    if CONFIG.exists():
        parser.read(CONFIG)
    if not parser.has_section("General"):
        parser.add_section("General")
    if not parser.has_option("General", "name"):
        parser.set("General", "name", socket.gethostname())
    parser.set("General", "customDevices", ",".join(addresses))
    with CONFIG.open("w") as handle:
        parser.write(handle, space_around_delimiters=False)
    os.chmod(CONFIG, 0o600)
    print(f"KDE Connect discovery configured for {len(addresses)} tailnet peers")
    return len(addresses)


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
    if "--start" in sys.argv:
        start_daemon()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
