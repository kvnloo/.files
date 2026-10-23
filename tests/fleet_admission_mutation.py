#!/usr/bin/env python3
"""Reject explicit groot fallback and capacity-bypass mutants under unchanged laws.

Scratch copies only. The real Bend/Lean processes run, but no fleet/device effects occur.
A valid reference verdict is mandatory before a mutant failure can count.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from fleet_admission_toolchain import verifier_environment

ROOT = Path(__file__).resolve().parents[1] / "bend/fleet_admission"
MUTATIONS = [
    ("groot fallback",
     "    case FGroot{}:\n      FRefuse{RGrootForbidden{}}",
     "    case FGroot{}:\n      FAdmit{}"),
    ("capacity bypass",
     "    case False{}:\n      FRefuse{RNoRoom{}}",
     "    case False{}:\n      FAdmit{}"),
    ("failed transfer bypass",
     "    case TFailed{}:\n      FRefuse{RSourceFailed{}}",
     "    case TFailed{}:\n      FAdmit{}"),
]


def verify(bend, cwd, env):
    proc = subprocess.run([bend, "PROOF.bend", "--verdict"], cwd=cwd,
                          capture_output=True, text=True, env=env, timeout=300)
    print(proc.stdout, end="")
    print(proc.stderr, end="", file=sys.stderr)
    return proc


def main():
    with verifier_environment() as (bend, env), tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder)
        for filename in ("MODEL.bend", "LAWS.bend", "PROOF.bend"):
            shutil.copy2(ROOT / filename, scratch / filename)
        reference = verify(bend, scratch, env)
        output = reference.stdout + reference.stderr
        if (reference.returncode or reference.stdout.strip() != "ALL PROOFS CHECK"
                or "SOME PROOFS FAIL" in output.splitlines()):
            raise AssertionError("reference proof failed: " + output[-2000:])
        source = (scratch / "MODEL.bend").read_text()
        for label, old, broken in MUTATIONS:
            if source.count(old) != 1:
                raise AssertionError(f"{label}: mutation anchor changed; review model diff")
            (scratch / "MODEL.bend").write_text(source.replace(old, broken))
            mutant = verify(bend, scratch, env)
            output = mutant.stdout + mutant.stderr
            # The official checker emits failed-proof verdicts on stderr.
            # A compiler/toolchain crash is not evidence of a rejected law.
            if (mutant.returncode == 0 or "SOME PROOFS FAIL" not in output.splitlines()
                    or "ALL PROOFS CHECK" in output.splitlines()):
                raise AssertionError(f"{label}: no explicit failed-proof verdict: " + output[-2000:])
            print(f"fleet admission: {label} mutation rejected")
        (scratch / "MODEL.bend").write_text(source)
    print("source_semantics_attested=false; runtime_observed=false; proof_is_permission=false")


if __name__ == "__main__":
    main()
