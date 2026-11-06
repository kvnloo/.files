#!/usr/bin/env python3
"""Exhaustive Bend/Python parity for host layout: 3 * 2 * 2 * 5 * 3 * 2 = 360 decide cases + 4 status.

Executes the real MODEL.decide through Bend. No installer, systemd or filesystem effects.
"""
from __future__ import annotations

import itertools
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from bend_verifier import verifier_environment  # noqa: E402
from host_admission import Hosts, Live, Mount, Parent, code, decide, status  # noqa: E402

DOMAIN = ROOT / "bend/host_layout"
STATUS = {"clean": "0", "drift": "1", "unknown": "2"}


def b(value):
    return "True{}" if value else "False{}"


def live(kind):
    return "M.LChanged{}" if kind is Live.CHANGED else f"M.LAccepted{{M.{kind.value}{{}}}}"


def main():
    cases = list(itertools.product(Hosts, (False, True), Parent, Live, Mount, (False, True)))
    exprs, expected = [], []
    for hosts, manifest, parent, kind, mount, fresh in cases:
        exprs.append(f"Nat.show(M.code(M.decide(M.{hosts.value}{{}}, {b(manifest)}, M.{parent.value}{{}}, "
                     f"{live(kind)}, M.{mount.value}{{}}, {b(fresh)})))")
        expected.append(str(code(decide(hosts, manifest, parent, kind, mount, fresh))))
    for unknown, drift in itertools.product((False, True), repeat=2):
        exprs.append(f"Nat.show(M.status_code(M.status({b(unknown)}, {b(drift)})))")
        expected.append(STATUS[status(unknown, drift)])
    with verifier_environment(DOMAIN) as (bend, env), tempfile.TemporaryDirectory() as folder:
        working = Path(folder)
        shutil.copy2(DOMAIN / "MODEL.bend", working / "MODEL.bend")
        (working / "cases.bend").write_text(
            "import Base\nimport ./MODEL.bend as M\n\n"
            + "def main() -> IO(Unit):\n  IO.print(\n    "
            + " ++\n    ".join(exprs) + ")\n")
        result = subprocess.run([bend, "cases.bend"], cwd=working, env=env,
                                capture_output=True, text=True, timeout=600)
    if result.returncode:
        raise RuntimeError("Bend parity execution failed: " + (result.stderr + result.stdout)[-2000:])
    actual, want = result.stdout.strip(), "".join(expected)
    if actual != want:
        raise AssertionError(f"Bend/Python host layout parity mismatch for {len(exprs)} cases:\n"
                             f"actual:   {actual[:900]}\nexpected: {want[:900]}")
    print(f"host layout: {len(exprs)} exhaustive Bend/Python cases match")


if __name__ == "__main__":
    main()
