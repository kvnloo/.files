#!/usr/bin/env python3
"""Owned journal fixtures only; never injected into production units."""
import sys

phase = sys.argv[1]
print("FIXTURE_RUNTIME healthy connected bundled", flush=True)
if phase in ("runtime", "correlation"):
    print("FIXTURE_RUNTIME TypeError: synthetic-owned-test", flush=True)
    print("FIXTURE_RUNTIME TypeError: duplicate-owned-test", flush=True)
if phase in ("bridge", "correlation"):
    print("FIXTURE_BRIDGE [bridge] failed ECONNRESET synthetic-owned-test", flush=True)
