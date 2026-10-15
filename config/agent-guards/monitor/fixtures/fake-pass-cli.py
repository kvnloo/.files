#!/usr/bin/env python3
"""Fixture binary. Never invokes a real credential tool."""
import json
import os
from pathlib import Path
import sys

expected = ["agent", "monitor", "broker", "--output", "json", "--limit"]
if sys.argv[1:7] != expected or not os.environ.get("PROTON_PASS_SESSION_DIR", "").endswith("fixture-session"):
    sys.exit(3)
name = os.environ.get("GUARD_MONITOR_FIXTURE", "approved")
if name == "failure":
    print("CANARY_SECRET_SUBPROCESS", file=sys.stderr)
    sys.exit(4)
if name == "malformed":
    print("CANARY_SECRET_SUBPROCESS")
elif name == "unknown-schema":
    print(json.dumps({"unexpected": "CANARY_SECRET_SUBPROCESS"}))
else:
    print(Path(__file__).with_name(name + ".json").read_text())
