#!/usr/bin/env python3
"""Merge the local Netdata stdio bridge into the existing OMP user MCP config.

Run as the OMP user, not root:
    python3 scripts/setup-netdata-mcp.py

Requires Python 3 for setup, and Netdata's packaged nd-mcp bridge plus a running
local Netdata agent for use. Does not start services, claim an agent, install
packages, or read/copy credentials. Without a Cloud claim and bearer key, only
Netdata's unauthenticated metric/alert capabilities are available; sensitive
live functions and logs remain restricted by Netdata.

Official bridge and transport documentation:
https://github.com/netdata/netdata/blob/master/src/web/mcp/README.md
"""

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile


def main() -> int:
    if os.geteuid() == 0:
        raise RuntimeError("Run as the OMP user, not root; no sudo is needed.")

    repo_root = Path(__file__).resolve().parent.parent
    fragment = json.loads((repo_root / "config/omp/netdata-mcp.json").read_text())
    server = fragment["mcpServers"]["netdata"]
    config_path = Path.home() / ".omp/agent/mcp.json"
    if config_path.is_symlink():
        raise RuntimeError(f"Refusing to replace symlink {config_path}; merge the tracked fragment at its source.")

    original = config_path.read_bytes() if config_path.exists() else None
    config = json.loads(original) if original is not None else {}
    if not isinstance(config, dict):
        raise RuntimeError(f"Expected a JSON object in {config_path}; nothing changed.")
    servers = config.setdefault("mcpServers", {})
    if not isinstance(servers, dict):
        raise RuntimeError(f"Expected an mcpServers object in {config_path}; nothing changed.")
    if "netdata" in servers and servers["netdata"] != server:
        raise RuntimeError("An unrelated netdata MCP entry already exists; refusing to overwrite it.")

    if "netdata" not in servers:
        servers["netdata"] = server
        config_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".mcp.json.", dir=config_path.parent)
        try:
            with os.fdopen(fd, "w") as stream:
                json.dump(config, stream, indent=2)
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            if config_path.is_symlink() or (
                config_path.read_bytes() if config_path.exists() else None
            ) != original:
                raise RuntimeError("OMP MCP configuration changed during setup; nothing replaced.")
            os.replace(temporary, config_path)
        finally:
            Path(temporary).unlink(missing_ok=True)
        print(f"Added local Netdata MCP entry to {config_path} (mode 0600).")
    else:
        print(f"Local Netdata MCP entry is already present in {config_path}; unchanged.")

    if shutil.which(server["command"]) is None:
        print("Pending dependency: install Netdata including nd-mcp, then start the local Netdata agent.")
    print("Transport: official nd-mcp stdio bridge -> ws://127.0.0.1:19999/mcp")
    print("Restart OMP to discover the server. No Cloud claim or bearer credential was configured.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, RuntimeError) as error:
        print(f"Netdata MCP setup failed: {error}", file=sys.stderr)
        sys.exit(1)
