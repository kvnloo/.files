"""Fleet bulk-spool policy shared by all host-side transports."""
import os
from pathlib import Path
import socket
import tomllib


def storage_policy():
    path = Path(__file__).resolve().parent.parent / "config/fleet/storage.toml"
    with path.open("rb") as stream:
        return tomllib.load(stream).get("hosts", {}).get(socket.gethostname(), {})


def runs_dir():
    if os.environ.get("FLEET_RUNS"):
        return Path(os.environ["FLEET_RUNS"]).expanduser()
    # Preserve explicit isolated test/user state roots.
    if os.environ.get("FLEET_STATE"):
        return Path(os.environ["FLEET_STATE"]).expanduser() / "runs"
    configured = storage_policy().get("runs")
    if configured:
        path = Path(configured)
        if not os.path.ismount("/mnt/zer0models"):
            raise RuntimeError("fleet bulk storage is not mounted: /mnt/zer0models")
        return path
    return Path.home() / ".local/state/fleet/runs"


if __name__ == "__main__":
    print(runs_dir())
