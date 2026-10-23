#!/usr/bin/env python3
"""Fail if the verified laws accept a fallback/capacity-bypass mutation.

Scratch copies only. The reference must check before a failed mutant can count.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1] / "bend/fleet_admission"
OLD = "    case False{}:\n      FRefuse{RNoRoom{}}"
BROKEN = "    case False{}:\n      FAdmit{}"


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
        code, text = verify(bend, scratch)
        if code or "ALL PROOFS CHECK" not in text or "SOME PROOFS FAIL" in text:
            raise AssertionError("reference proof failed: " + text[-2000:])
        original = (scratch / "MODEL.bend").read_text()
        if original.count(OLD) != 1:
            raise AssertionError("fallback mutation anchor changed; update mutation review")
        (scratch / "MODEL.bend").write_text(original.replace(OLD, BROKEN))
        code, text = verify(bend, scratch)
        if code == 0 and "ALL PROOFS CHECK" in text and "SOME PROOFS FAIL" not in text:
            raise AssertionError("law-breaking local fallback mutation was accepted")
        if "SOME PROOFS FAIL" not in text and code == 0:
            raise AssertionError("mutant lacked an explicit failure verdict: " + text[-2000:])
        print("fleet admission: no-room -> Admit mutation rejected")


if __name__ == "__main__":
    main()
