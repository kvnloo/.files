#!/usr/bin/env python3
"""Regular-file-only executable model of the destructive apply state machine.

This harness is intentionally incapable of opening block devices. It exercises the exact
sfdisk delete/resize syntax, fstab contract, checkpoints, and rollback boundary.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import stat
import subprocess
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rescue_expand_fstab as fstab_contract

CONFIRM = "EXPAND 23446Z P1 4196352-281020415 DELETE P2 KEEP P3 281020416"
FAILPOINTS = {"none", "before-delete", "after-delete", "after-resize", "before-grow", "during-grow", "after-grow", "fstab-install", "final-verification"}


def table(image: Path) -> dict:
    return json.loads(subprocess.check_output(["sfdisk", "--json", str(image)], text=True))["partitiontable"]


def parts(image: Path) -> list[tuple[int, int, str]]:
    return [(p["start"], p["size"], p.get("uuid", "")) for p in table(image)["partitions"]]


def run(image: Path, fstab: Path, receipt: Path, confirm: str, failpoint: str) -> int:
    mode = image.stat().st_mode
    if not stat.S_ISREG(mode) or image.is_symlink():
        raise ValueError("mock apply requires a non-symlink regular sparse file")
    if confirm != CONFIRM:
        raise ValueError("typed confirmation mismatch; nothing changed")
    if failpoint not in FAILPOINTS:
        raise ValueError("unknown failure injection")
    receipt.mkdir(parents=True, exist_ok=True)
    log: list[str] = []
    checkpoint = receipt / "checkpoint"
    checkpoint.write_text("preflight\n")
    before_dump = subprocess.check_output(["sfdisk", "--dump", str(image)], text=True)
    (receipt / "partition-table.before").write_text(before_dump)
    original_parts = parts(image)
    already = len(original_parts) == 3 and original_parts[0][:2] == (4196352, 276824064)
    if already:
        log.append("already-grown")
        (receipt / "commands.json").write_text(json.dumps(log))
        return 0
    before_fstab = fstab.read_bytes()
    staged = fstab_contract.transform(before_fstab)
    (receipt / "fstab.staged").write_bytes(staged)
    fstab_contract.check_final(before_fstab, staged)

    if len(original_parts) != 4:
        raise ValueError("mock original partition count drift")
    immutable = (original_parts[2], original_parts[3])
    table_changed = False
    grow_started = False

    def inject(point: str) -> None:
        if failpoint == point:
            log.append("FAIL:" + point)
            raise RuntimeError("injected " + point)

    try:
        inject("before-delete")
        log.append("sfdisk-delete-p2")
        subprocess.run(["sfdisk", "--delete", str(image), "2"], check=True, stdout=subprocess.DEVNULL)
        table_changed = True
        checkpoint.write_text("table_changed\n")
        inject("after-delete")
        log.append("sfdisk-resize-p1")
        subprocess.run(
            ["sfdisk", "--no-reread", "--force", "-N", "1", str(image)],
            input="start=4196352, size=276824064, type=linux, uuid=5fed8d1d-f6a6-44d3-9608-0408425a9383\n",
            text=True, check=True, stdout=subprocess.DEVNULL,
        )
        inject("after-resize")
        after = parts(image)
        if len(after) != 3 or (after[1], after[2]) != immutable:
            raise RuntimeError("p3/p4 invariant changed")
        inject("before-grow")
        grow_started = True
        checkpoint.write_text("grow_started\n")
        log.append("xfs-growfs-mock")
        inject("during-grow")
        checkpoint.write_text("grown\n")
        inject("after-grow")
        inject("fstab-install")
        log.append("fstab-atomic-install")
        staged_path = receipt / "fstab.staged"
        fstab_contract.atomic_install(staged_path, fstab)
        checkpoint.write_text("fstab_updated\n")
        if failpoint == "final-verification":
            fstab.write_bytes(fstab.read_bytes() + b"# injected drift\n")
        fstab_contract.check_final(before_fstab, fstab.read_bytes())
        checkpoint.write_text("verified\n")
        return 0
    except Exception:
        if table_changed and not grow_started:
            log.append("rollback-partition-table")
            subprocess.run(["sfdisk", str(image)], input=before_dump, text=True, check=True, stdout=subprocess.DEVNULL)
            checkpoint.write_text("rolled_back_pre_grow\n")
        elif grow_started:
            log.append("NO_ROLLBACK_AFTER_GROW_STARTED")
        raise
    finally:
        (receipt / "commands.json").write_text(json.dumps(log, indent=2) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--image", required=True, type=Path)
    parser.add_argument("--fstab", required=True, type=Path)
    parser.add_argument("--receipt", required=True, type=Path)
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--failpoint", default="none", choices=sorted(FAILPOINTS))
    args = parser.parse_args()
    try:
        return run(args.image, args.fstab, args.receipt, args.confirm, args.failpoint)
    except Exception as exc:
        print(f"MOCK REFUSED/FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
