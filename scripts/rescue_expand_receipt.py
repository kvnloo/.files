#!/usr/bin/env python3
"""Resolve a receipt filesystem through PKNAME and sysfs slaves to physical disks."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import stat
import subprocess

DENIED_FS = {"tmpfs", "overlay", "ramfs", "squashfs", "aufs"}


def flatten(devices: list[dict]) -> list[dict]:
    out: list[dict] = []
    for device in devices:
        out.append(device)
        out.extend(flatten(device.get("children") or []))
    return out


def physical_roots(rows: list[dict], source_mm: str, slaves: dict[str, list[str]]) -> set[str]:
    by_mm = {str(row.get("maj:min")): row for row in rows}
    by_path = {str(row.get("path")): row for row in rows}
    seen: set[str] = set()
    roots: set[str] = set()

    def walk(mm: str) -> None:
        if mm in seen:
            return
        seen.add(mm)
        row = by_mm.get(mm)
        if not row:
            raise ValueError(f"unresolved backing device MAJ:MIN {mm}")
        child_mms = slaves.get(mm, [])
        pkname = row.get("pkname")
        if child_mms:
            for child in child_mms:
                walk(child)
        elif pkname:
            parent = by_path.get(str(pkname)) or by_path.get("/dev/" + str(pkname).removeprefix("/dev/"))
            if not parent:
                raise ValueError(f"unresolved PKNAME {pkname}")
            walk(str(parent.get("maj:min")))
        elif row.get("type") == "disk":
            roots.add(mm)
        else:
            raise ValueError(f"backing chain ended at non-disk {row.get('path')}")

    walk(source_mm)
    if not roots:
        raise ValueError("no persistent physical-disk parent")
    return roots


def sysfs_slaves(rows: list[dict]) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in rows:
        mm = str(row.get("maj:min"))
        directory = Path("/sys/dev/block") / mm / "slaves"
        children: list[str] = []
        if directory.is_dir():
            for entry in directory.iterdir():
                target = entry.resolve()
                dev_file = target / "dev"
                if dev_file.is_file():
                    children.append(dev_file.read_text(encoding="ascii").strip())
        result[mm] = children
    return result


def device_mm(path: Path) -> str:
    mode = path.stat()
    if not stat.S_ISBLK(mode.st_mode):
        raise ValueError(f"not a block device: {path}")
    return f"{os.major(mode.st_rdev)}:{os.minor(mode.st_rdev)}"


def verify(source: Path, target: Path, fstype: str) -> set[str]:
    if fstype in DENIED_FS:
        raise ValueError(f"non-persistent receipt filesystem type: {fstype}")
    source = source.resolve(strict=True)
    target = target.resolve(strict=True)
    payload = json.loads(subprocess.check_output(
        ["lsblk", "--json", "-p", "-o", "PATH,TYPE,PKNAME,MAJ:MIN"], text=True
    ))
    rows = flatten(payload.get("blockdevices") or [])
    source_mm = device_mm(source)
    target_mm = device_mm(target)
    roots = physical_roots(rows, source_mm, sysfs_slaves(rows))
    if target_mm in roots:
        raise ValueError("receipt filesystem traces to the target physical disk")
    return roots


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("target", type=Path)
    parser.add_argument("fstype")
    args = parser.parse_args()
    try:
        roots = verify(args.source, args.target, args.fstype)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        parser.error(str(exc))
    print("physical receipt roots:", ",".join(sorted(roots)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
