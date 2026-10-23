#!/usr/bin/env python3
"""Reject explicit groot fallback and capacity-bypass mutants under unchanged laws.

Scratch copies only. No real process, SSH, device or build effects occur.
A valid reference verdict is mandatory before a mutant failure can count.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / "bend/fleet_admission"
MUTATIONS = [
    ("groot fallback",
     "    case FGroot{}:\n      FRefuse{RGrootForbidden{}}",
     "    case FGroot{}:\n      FAdmit{}"),
    ("capacity bypass",
     "    case False{}:\n      FRefuse{RNoRoom{}}",
     "    case False{}:\n      FAdmit{}"),
]


def verify(bend, cwd):
    env = dict(os.environ)
    env.pop("BENDTT", None)
    proc = subprocess.run([bend, "PROOF.bend", "--verdict"], cwd=cwd,
                          capture_output=True, text=True, env=env, timeout=180)
    return proc.returncode, proc.stdout + proc.stderr


def main():
    bend = os.environ.get("BEND")
    if not bend or not Path(bend).is_file():
        raise RuntimeError("BEND must point at the pinned verifier binary")
    with tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder)
        for filename in ("MODEL.bend", "LAWS.bend", "PROOF.bend"):
            shutil.copy2(ROOT / filename, scratch / filename)
        code, output = verify(bend, scratch)
        if code or "ALL PROOFS CHECK" not in output or "SOME PROOFS FAIL" in output:
            raise AssertionError("reference proof failed: " + output[-2000:])
        source = (scratch / "MODEL.bend").read_text()
        for label, old, broken in MUTATIONS:
            if source.count(old) != 1:
                raise AssertionError(f"{label}: mutation anchor changed; review model diff")
            (scratch / "MODEL.bend").write_text(source.replace(old, broken))
            code, output = verify(bend, scratch)
            # A toolchain crash isn't valid evidence of a rejected law.
            if "SOME PROOFS FAIL" not in output:
                raise AssertionError(f"{label}: no explicit failed-proof verdict: " + output[-2000:])
            print(f"fleet admission: {label} mutation rejected")
        (scratch / "MODEL.bend").write_text(source)


if __name__ == "__main__":
    main()
