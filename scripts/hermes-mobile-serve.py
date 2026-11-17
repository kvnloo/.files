#!/usr/bin/env python3
"""Keep the Hermes mobile app's tailnet entry point on the dashboard proxy.

The phone app reaches the dashboard at https://<host>:9119, which Tailscale
serve must forward to hermes-drive-web-proxy (127.0.0.1:9165). Debug captures
used to repoint that mapping at a throwaway proxy; when the throwaway process
died, the app lost its server until someone noticed.

  hermes-mobile-serve ensure            restore the canonical mapping if it differs
  hermes-mobile-serve status            print the mapping and whether its target listens
  hermes-mobile-serve capture [--minutes N] [--port P] -- CMD...
                                        run CMD (a capture proxy listening on P) as a
                                        transient user unit, point :9119 at it, and
                                        restore the canonical mapping when the unit
                                        stops for any reason (exit, crash, kill, or
                                        the N-minute limit).

ensure runs as ExecStartPost of hermes-drive-web-proxy.service, and as
ExecStopPost of every capture unit.
"""

from __future__ import annotations

import argparse
import json
import os
import shlex
import socket
import subprocess
import sys
import time
from pathlib import Path

HTTPS_PORT = int(os.environ.get("HERMES_MOBILE_SERVE_PORT", "9119"))
CANONICAL = os.environ.get("HERMES_MOBILE_SERVE_TARGET", "http://127.0.0.1:9165")
CAPTURE_UNIT = "hermes-mobile-capture"
STATE = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state")) / "hermes-mobile-serve"


def log(event: str, **fields) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": event, **fields}
    with (STATE / "events.jsonl").open("a") as handle:
        handle.write(json.dumps(row) + "\n")
    print(json.dumps(row))


def current_target() -> str | None:
    out = subprocess.run(["tailscale", "serve", "status", "--json"],
                         capture_output=True, text=True, timeout=20, check=True).stdout
    web = (json.loads(out or "{}") or {}).get("Web") or {}
    for hostport, config in web.items():
        if hostport.rsplit(":", 1)[-1] == str(HTTPS_PORT):
            return ((config.get("Handlers") or {}).get("/") or {}).get("Proxy")
    return None


def listening(target: str | None) -> bool:
    if not target:
        return False
    hostport = target.split("://", 1)[-1].split("/", 1)[0]
    host, _, port = hostport.rpartition(":")
    try:
        with socket.create_connection((host or "127.0.0.1", int(port)), timeout=2):
            return True
    except (OSError, ValueError):
        return False


def point_at(target: str) -> None:
    subprocess.run(["tailscale", "serve", "--bg", f"--https={HTTPS_PORT}", target],
                   capture_output=True, text=True, timeout=30, check=True)


def ensure(reason: str) -> int:
    before = current_target()
    if before == CANONICAL:
        return 0
    point_at(CANONICAL)
    after = current_target()
    log("restored" if after == CANONICAL else "restore_failed",
        reason=reason, before=before, after=after)
    return 0 if after == CANONICAL else 1


def status() -> int:
    target = current_target()
    print(json.dumps({"port": HTTPS_PORT, "target": target, "canonical": target == CANONICAL,
                      "target_listening": listening(target)}))
    return 0 if target == CANONICAL and listening(target) else 1


def capture(minutes: int, port: int, command: list[str]) -> int:
    if not command:
        sys.exit("capture needs a command after --")
    self_path = os.path.abspath(sys.argv[0])
    subprocess.run(["systemctl", "--user", "reset-failed", CAPTURE_UNIT], capture_output=True)
    subprocess.run([
        "systemd-run", "--user", "--collect", f"--unit={CAPTURE_UNIT}",
        f"--property=RuntimeMaxSec={minutes * 60}",
        f"--property=ExecStopPost=/usr/bin/python3 {self_path} ensure --reason capture-stopped",
        "--", *command,
    ], check=True)
    target = f"http://127.0.0.1:{port}"
    for _ in range(40):
        if listening(target):
            break
        time.sleep(0.25)
    else:
        subprocess.run(["systemctl", "--user", "stop", CAPTURE_UNIT], capture_output=True)
        sys.exit(f"capture command never listened on {port}; mapping left canonical")
    point_at(target)
    log("capture_started", target=target, minutes=minutes, command=shlex.join(command))
    print(f"stop early with: systemctl --user stop {CAPTURE_UNIT}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    ens = sub.add_parser("ensure")
    ens.add_argument("--reason", default="manual")
    sub.add_parser("status")
    cap = sub.add_parser("capture")
    cap.add_argument("--minutes", type=int, default=20)
    cap.add_argument("--port", type=int, default=9166)
    cap.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if args.cmd == "ensure":
        return ensure(args.reason)
    if args.cmd == "status":
        return status()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    return capture(args.minutes, args.port, command)


if __name__ == "__main__":
    raise SystemExit(main())
