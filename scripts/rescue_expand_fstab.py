#!/usr/bin/env python3
"""Exact, byte-preserving fstab contract for the rescue expansion."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import tempfile

SWAP_SOURCE = "UUID=316f4699-5371-4798-9873-68f2b6194cb4"
SWAP_TARGET = "none"
SWAP_FSTYPE = "swap"


def fields(line: bytes) -> list[bytes] | None:
    stripped = line.lstrip()
    if not stripped or stripped.startswith(b"#"):
        return None
    body = stripped.split(b"#", 1)[0]
    values = body.split()
    return values if values else None


def is_obsolete(line: bytes) -> bool:
    values = fields(line)
    return bool(
        values
        and len(values) >= 3
        and values[0] == SWAP_SOURCE.encode()
        and values[1] == SWAP_TARGET.encode()
        and values[2] == SWAP_FSTYPE.encode()
    )


def transform(raw: bytes) -> bytes:
    lines = raw.splitlines(keepends=True)
    hits = [i for i, line in enumerate(lines) if is_obsolete(line)]
    if len(hits) != 1:
        raise ValueError(f"expected exactly one active obsolete disk-swap entry, found {len(hits)}")
    return b"".join(line for i, line in enumerate(lines) if i != hits[0])


def check_original(raw: bytes) -> None:
    transform(raw)


def check_final(before: bytes, final: bytes) -> None:
    expected = transform(before)
    if final != expected:
        raise ValueError("final fstab is not the exact staged byte-preserving transform")
    if any(is_obsolete(line) for line in final.splitlines(keepends=True)):
        raise ValueError("obsolete disk-swap entry remains")


def atomic_install(source: Path, destination: Path) -> None:
    data = source.read_bytes()
    parent = destination.parent
    st = destination.stat()
    fd, tmp_name = tempfile.mkstemp(prefix=".fstab.expand.", dir=parent)
    tmp = Path(tmp_name)
    try:
        os.fchmod(fd, st.st_mode & 0o7777)
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp, destination)
        dfd = os.open(parent, os.O_DIRECTORY)
        try:
            os.fsync(dfd)
        finally:
            os.close(dfd)
    finally:
        tmp.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("check-original"); p.add_argument("fstab", type=Path)
    p = sub.add_parser("stage"); p.add_argument("before", type=Path); p.add_argument("staged", type=Path)
    p = sub.add_parser("install"); p.add_argument("staged", type=Path); p.add_argument("destination", type=Path)
    p = sub.add_parser("check-final"); p.add_argument("before", type=Path); p.add_argument("final", type=Path)
    args = parser.parse_args()
    try:
        if args.command == "check-original":
            check_original(args.fstab.read_bytes())
        elif args.command == "stage":
            args.staged.write_bytes(transform(args.before.read_bytes()))
        elif args.command == "install":
            atomic_install(args.staged, args.destination)
        else:
            check_final(args.before.read_bytes(), args.final.read_bytes())
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
