#!/usr/bin/env python3
"""Exhaustive finite-domain Bend/Python parity: 3 * 2 * 2 * 2 * 4 = 96.

Executes the real MODEL.decide through Bend, not a synthetic unrelated model.
No SSH, device, kubectl or build processes. Missing Bend fails closed.
"""
from __future__ import annotations

import itertools
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from fleet_admission import Request, Target, Transfer, decide, verdict_code

DOMAIN = ROOT / "bend/fleet_admission"
TARGETS = {Target.MISSING: "FMissing", Target.GROOT: "FGroot", Target.REMOTE: "FRemote"}
TRANSFERS = {Transfer.PENDING: "TPending", Transfer.COMPLETE: "TComplete",
             Transfer.NOT_REQUIRED: "TNotRequired", Transfer.FAILED: "TFailed"}


def b(value):
    return "True{}" if value else "False{}"


def main():
    bend = os.environ.get("BEND")
    if not bend or not Path(bend).is_file():
        raise RuntimeError("BEND must name the pinned, downloaded verifier binary")
    cases = list(itertools.product(Target, (False, True), (False, True),
                                   (False, True), Transfer))
    exprs = []
    expected = []
    for target, qualified, available, room, transfer in cases:
        exprs.append(
            f"M.code(M.decide(M.{TARGETS[target]}{{}}, {b(qualified)}, "
            f"{b(available)}, {b(room)}, M.{TRANSFERS[transfer]}{{}}))")
        expected.append(f"{verdict_code(decide(Request(target, qualified, available, room, transfer)))}n")
    with tempfile.TemporaryDirectory() as folder:
        working = Path(folder)
        shutil.copy2(DOMAIN / "MODEL.bend", working / "MODEL.bend")
        (working / "cases.bend").write_text(
            "import Base\nimport ./MODEL.bend as M\n\n"
            + "def main() -> List<&2, Nat>:\n  ["
            + ",\n   ".join(exprs) + "]\n")
        env = dict(os.environ)
        env.pop("BENDTT", None)
        result = subprocess.run([bend, "cases.bend"], cwd=working, env=env,
                                capture_output=True, text=True, timeout=180)
    if result.returncode:
        raise RuntimeError("Bend parity execution failed: " + (result.stderr + result.stdout)[-2000:])
    actual = next((line.strip() for line in result.stdout.splitlines()
                   if line.lstrip().startswith("[")), None)
    want = "[" + ", ".join(expected) + "]"
    if actual != want:
        raise AssertionError(f"Bend/Python admission parity mismatch for {len(cases)} cases:\n"
                             f"actual: {str(actual)[:900]}\nexpected: {want[:900]}")
    print(f"fleet admission: {len(cases)} exhaustive Bend/Python cases match")


if __name__ == "__main__":
    main()
