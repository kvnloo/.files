#!/usr/bin/env python3
"""Safely tier bulky zer0 directories from NVMe to the capacity drive.

Copies with rsync, verifies with a checksum dry-run plus file count and byte
totals, atomically renames the source, installs a canonical symlink, verifies
it, then removes the backup. Sources may be directories or regular files.
Every transition is appended to a JSONL ledger. Existing symlinks are no-ops.
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

DEFAULT_DEST = Path("/mnt/zer0models/zer0-tier")
DEFAULT_SOURCE_ROOT = Path("/workspace/zer0")
LEDGER = Path("/workspace/zer0/portfolios/chief-of-staff/ledger/storage-tier.jsonl")
LOCK = Path("/tmp/zer0-storage-tier.lock")


def emit(event: str, **fields: object) -> None:
    record = {"ts": time.time(), "event": event, **fields}
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    with LEDGER.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(record, sort_keys=True) + "\n")
    print(json.dumps(record, sort_keys=True), flush=True)


def active_references(source: Path) -> list[dict[str, object]]:
    refs: list[dict[str, object]] = []
    prefix = str(source) + os.sep
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit():
            continue
        try:
            cwd = os.readlink(proc / "cwd")
            if cwd == str(source) or cwd.startswith(prefix):
                refs.append({"pid": int(proc.name), "kind": "cwd", "path": cwd})
        except OSError:
            pass
        try:
            fds = list((proc / "fd").iterdir())
        except OSError:
            continue
        for fd in fds:
            try:
                target = os.readlink(fd)
            except OSError:
                continue
            if target == str(source) or target.startswith(prefix):
                refs.append({"pid": int(proc.name), "kind": "fd", "path": target})
                break
    return refs


def tree_stats(path: Path) -> tuple[int, int]:
    """(file count, total bytes) of a regular file or a directory tree."""
    if not path.is_dir():
        return 1, path.lstat().st_size
    count = total = 0
    for root, _dirs, files in os.walk(path):
        for name in files:
            try:
                total += (Path(root) / name).lstat().st_size
                count += 1
            except OSError:
                pass
    return count, total


def nested_destination_links(source: Path, destination: Path) -> list[dict[str, str]]:
    """Reject parent moves that would turn a tiered child into a self-link."""
    hazards: list[dict[str, str]] = []
    destination_prefix = str(destination.resolve()) + os.sep
    for root, dirs, files in os.walk(source, followlinks=False):
        for name in [*dirs, *files]:
            candidate = Path(root) / name
            if not candidate.is_symlink():
                continue
            try:
                resolved = str(candidate.resolve())
            except OSError:
                continue
            if resolved == str(destination.resolve()) or resolved.startswith(destination_prefix):
                hazards.append({"link": str(candidate), "target": resolved})
        dirs[:] = [d for d in dirs if not (Path(root) / d).is_symlink()]
    return hazards


def _rsync_operands(source: Path, destination: Path) -> list[str]:
    if source.is_dir():
        return ["--delete", f"{source}/", f"{destination}/"]
    return [str(source), str(destination)]


def rsync_copy(source: Path, destination: Path) -> None:
    (destination if source.is_dir() else destination.parent).mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["rsync", "-aHAX", "--numeric-ids", "--info=stats2,progress2", *_rsync_operands(source, destination)],
        check=True,
    )


def verify_checksum(source: Path, destination: Path) -> None:
    result = subprocess.run(
        ["rsync", "-aHAXnc", "--numeric-ids", "--out-format=%i %n", *_rsync_operands(source, destination)],
        text=True,
        stdout=subprocess.PIPE,
        check=True,
    )
    changes = [line for line in result.stdout.splitlines() if line.strip()]
    if changes:
        raise RuntimeError(f"checksum verification found {len(changes)} differences; first={changes[:5]}")


def migrate(source: Path, destination_root: Path, dry_run: bool, source_root: Path | None = None) -> None:
    source = source.resolve() if source.is_symlink() else source.absolute()
    canonical = str(source)
    if not source.exists():
        emit("skip_missing", source=canonical)
        return
    if source.is_symlink():
        emit("skip_symlink", source=canonical, target=str(source.resolve()))
        return
    is_dir = source.is_dir()
    if not is_dir and not source.is_file():
        raise RuntimeError(f"source is not a directory or regular file: {source}")
    root = (source_root or DEFAULT_SOURCE_ROOT).absolute()
    try:
        relative = source.relative_to(root)
    except ValueError as exc:
        raise RuntimeError(f"source must be under {root}: {source}") from exc
    destination = destination_root / relative
    hazards = nested_destination_links(source, destination)
    if hazards:
        emit("blocked_nested_tier_link", source=canonical, destination=str(destination), hazards=hazards)
        raise RuntimeError(f"nested tier links prevent parent migration: {source}")
    refs = active_references(source)
    count, size = tree_stats(source)
    if refs:
        emit("blocked_active", source=canonical, destination=str(destination), bytes=size, references=refs)
        raise RuntimeError(f"active process references prevent migration: {source}")
    if dry_run:
        emit("dry_run_ready", source=canonical, destination=str(destination), bytes=size)
        return
    if is_dir and destination.exists() and not destination.is_dir():
        raise RuntimeError(f"destination exists and is not a directory: {destination}")
    if not is_dir and destination.exists():
        raise RuntimeError(f"destination file already exists: {destination}")
    emit("copy_start", source=canonical, destination=str(destination), bytes=size)
    rsync_copy(source, destination)
    emit("verify_start", source=canonical, destination=str(destination), bytes=size)
    verify_checksum(source, destination)
    destination_count, destination_size = tree_stats(destination)
    if (destination_count, destination_size) != (count, size):
        raise RuntimeError(
            f"file count/byte total mismatch source={count}/{size} destination={destination_count}/{destination_size}"
        )
    backup = source.with_name(source.name + f".tier-backup-{os.getpid()}")
    if backup.exists():
        raise RuntimeError(f"backup collision: {backup}")
    source.rename(backup)
    try:
        source.symlink_to(destination, target_is_directory=is_dir)
        if source.resolve() != destination.resolve() or source.is_dir() != is_dir or not source.exists():
            raise RuntimeError("canonical symlink verification failed")
    except Exception:
        if source.is_symlink():
            source.unlink()
        backup.rename(source)
        raise
    if is_dir:
        shutil.rmtree(backup)
    else:
        backup.unlink()
    emit("migrated", source=canonical, destination=str(destination), bytes=size, files=count)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+")
    parser.add_argument("--destination-root", default=str(DEFAULT_DEST))
    parser.add_argument("--source-root", default=str(DEFAULT_SOURCE_ROOT))
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    LOCK.parent.mkdir(parents=True, exist_ok=True)
    with LOCK.open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            emit("skip_busy", lock=str(LOCK))
            return 0
        source_root = Path(args.source_root)
        for raw in args.paths:
            migrate(Path(raw), Path(args.destination_root), dry_run=not args.apply, source_root=source_root)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
