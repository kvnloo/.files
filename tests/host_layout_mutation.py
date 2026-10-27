#!/usr/bin/env python3
"""Each mutant re-opens a 2026-10-25 failure path and must fail the unchanged laws.

Scratch copies only. A valid reference verdict is mandatory before a mutant failure counts.
"""
from __future__ import annotations

from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parent))
from bend_verifier import verifier_environment  # noqa: E402

ROOT = Path(__file__).resolve().parents[1] / "bend/host_layout"
MUTATIONS = [
    ("link through checkout directory",
     "    case PThroughCheckout{}:\n      HRefuse{RThroughCheckout{}}",
     "    case PThroughCheckout{}:\n      check_live(live, mount, fresh)"),
    ("overwrite operator edit",
     "    case LChanged{}:\n      HRefuse{RChanged{}}",
     "    case LChanged{}:\n      HLink{}"),
    ("fallback to another host manifest",
     "    case HNone{}:\n      HRefuse{RNoHost{}}",
     "    case HNone{}:\n      check_manifest(manifest, parent, live, mount, fresh)"),
    ("first match wins on ambiguous host",
     "    case HMany{}:\n      HRefuse{RAmbiguousHost{}}",
     "    case HMany{}:\n      check_manifest(manifest, parent, live, mount, fresh)"),
    ("stage fresh tree on unmounted bulk",
     "        case True{}:\n          HRefuse{RUnmounted{}}",
     "        case True{}:\n          HLink{}"),
    ("drift hides unknown",
     "  match unknown:\n    case True{}:\n      SUnknown{}",
     "  match unknown:\n    case True{}:\n      SDrift{}"),
    ("drift relabelled clean",
     "        case True{}:\n          SDrift{}",
     "        case True{}:\n          SClean{}"),
]


def verify(bend, cwd, env):
    return subprocess.run([bend, "PROOF.bend", "--verdict"], cwd=cwd,
                          capture_output=True, text=True, env=env, timeout=1800)


def main():
    with verifier_environment(ROOT) as (bend, env), tempfile.TemporaryDirectory() as folder:
        scratch = Path(folder)
        for filename in ("MODEL.bend", "LAWS.bend", "PROOF.bend"):
            shutil.copy2(ROOT / filename, scratch / filename)
        reference = verify(bend, scratch, env)
        output = reference.stdout + reference.stderr
        if (reference.returncode or reference.stdout.strip() != "ALL PROOFS CHECK"
                or "SOME PROOFS FAIL" in output.splitlines()):
            raise AssertionError("reference proof failed: " + output[-2000:])
        print("host layout: reference ALL PROOFS CHECK")
        source = (scratch / "MODEL.bend").read_text()
        for label, old, broken in MUTATIONS:
            if source.count(old) != 1:
                raise AssertionError(f"{label}: mutation anchor changed; review model diff")
            (scratch / "MODEL.bend").write_text(source.replace(old, broken))
            mutant = verify(bend, scratch, env)
            output = mutant.stdout + mutant.stderr
            # A compiler/toolchain crash is not evidence of a rejected law.
            if (mutant.returncode == 0 or "SOME PROOFS FAIL" not in output.splitlines()
                    or "ALL PROOFS CHECK" in output.splitlines()):
                raise AssertionError(f"{label}: no explicit failed-proof verdict: " + output[-2000:])
            print(f"host layout: {label} mutation rejected")
        (scratch / "MODEL.bend").write_text(source)
    print("source_semantics_attested=false; runtime_observed=false; proof_is_permission=false")


if __name__ == "__main__":
    main()
