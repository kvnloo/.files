#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path

root = Path(os.environ.get("XDG_RUNTIME_DIR", "/tmp")) / "reforge-groot"
lanes = ("system", "flatpak", "firmware", "rust", "python", "node")

def read(name: str, default: str) -> str:
    try:
        return (root / name).read_text(errors="replace").strip() or default
    except OSError:
        return default

try:
    lines = (root / "update.log").read_text(errors="replace").splitlines()[-120:]
except OSError:
    lines = []

print(json.dumps({
    "overall": read("overall.status", "idle"),
    "lanes": {lane: read(f"{lane}.status", "idle") for lane in lanes},
    "log": "\n".join(lines),
}, separators=(",", ":")))
