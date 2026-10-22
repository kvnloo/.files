#!/usr/bin/python3
"""Accept only the reviewed v0.0.17 stdio sample; reject all added YAML."""
import errno
import json
import os
from pathlib import Path
import socket
import sys


def reject():
    raise SystemExit("memory-tunnel: profile or enforced egress check rejected")


if sys.argv[1:] == ["--egress"]:
    # An errno-based negative control avoids treating refused/offline as enforcement.
    for family, address in (
        (socket.AF_INET, ("1.1.1.1", 443)),
        (socket.AF_INET6, ("2606:4700:4700::1111", 443)),
        (socket.AF_INET, ("127.0.0.1", 1)),
        (socket.AF_INET6, ("::1", 1)),
    ):
        with socket.socket(family, socket.SOCK_STREAM) as connection:
            connection.settimeout(2)
            try:
                connection.connect(address)
            except OSError as error:
                if error.errno not in (errno.EPERM, errno.EACCES):
                    reject()
            else:
                reject()
else:
    # Deliberately stricter than general YAML: canonical sample only, no aliases,
    # duplicate keys, tags, Harpoon, HTTP targets or extra forwarding settings.
    path = Path(sys.argv[1])
    if path.stat().st_size > 16384:
        reject()
    actual = [line.rstrip() for line in path.read_text().splitlines()
              if line.strip() and not line.lstrip().startswith("#")]
    expected = [
        "config_version: 1", "control_plane:",
        '  base_url: "https://api.openai.com"',
        "  tunnel_id: " + json.dumps(os.environ["TUNNEL_ID"]),
        '  api_key: "env:CONTROL_PLANE_API_KEY"', "health:",
        '  listen_addr: "127.0.0.1:8789"', "admin_ui:",
        "  open_browser: false", "log:", "  level: info", "  format: json",
        "mcp:", "  commands:", "    - channel: main",
        "      command: " + json.dumps(os.environ["MEMORY_MCP_EXPECTED_COMMAND"]),
    ]
    if actual != expected:
        reject()
