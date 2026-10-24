#!/usr/bin/env python3
"""Compare live symlink contracts with a candidate .files tree.

Read-only. A missing or type-changed target is not rollout-safe.
"""

from __future__ import annotations

import os
from pathlib import Path
import stat
from typing import Any


def _kind(path: Path) -> str:
    try:
        mode = path.lstat().st_mode
    except OSError:
        return "absent"
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "dir"
    if stat.S_ISREG(mode):
        return "file"
    return "other"


def _mode(path: Path) -> str | None:
    try:
        return oct(path.lstat().st_mode & 0o777)
    except OSError:
        return None


def compare_link(link: Path, live_root: Path, candidate_root: Path) -> dict[str, Any]:
    literal = os.readlink(link)
    try:
        resolved = link.resolve(strict=False)
    except OSError:
        resolved = Path()
    live_root = live_root.resolve()
    candidate_root = candidate_root.resolve()
    try:
        relative = resolved.relative_to(live_root).as_posix()
        in_repo = True
    except ValueError:
        relative = ""
        in_repo = False
    candidate = candidate_root / relative if in_repo else None
    live_target = resolved
    live_kind = _kind(live_target) if in_repo else "absent"
    cand_kind = _kind(candidate) if candidate is not None else "absent"
    live_exists = live_kind != "absent"
    cand_exists = cand_kind != "absent"

    if not in_repo:
        result = "UNKNOWN"
        content = "outside-repo"
        mode_status = "n/a"
    elif not cand_exists:
        result = "MISSING"
        content = "absent"
        mode_status = "n/a"
    elif live_kind != cand_kind:
        result = "TYPE_CHANGED"
        content = f"{live_kind}->{cand_kind}"
        mode_status = "n/a"
    else:
        mode_status = "same" if _mode(live_target) == _mode(candidate) else "different"
        if live_kind == "file":
            try:
                same = live_target.read_bytes() == candidate.read_bytes()
            except OSError:
                same = False
                result = "UNKNOWN"
                content = "unreadable"
            else:
                content = "identical" if same else "different"
                result = "SAFE" if same and mode_status == "same" else "CHANGED"
        elif live_kind == "symlink":
            content = "same-target" if os.readlink(live_target) == os.readlink(candidate) else "different-target"
            result = "SAFE" if content == "same-target" else "CHANGED"
        elif live_kind == "dir":
            content = "directory"
            # Directory mode bits from a fresh checkout are not a runtime contract.
            result = "SAFE"
        else:
            content = live_kind
            result = "UNKNOWN"

    return {
        "home_link": str(link),
        "live_literal": literal,
        "live_resolved": str(resolved),
        "relative": relative,
        "candidate_path": str(candidate) if candidate is not None else "",
        "live_type": live_kind,
        "candidate_type": cand_kind,
        "live_exists": live_exists,
        "candidate_exists": cand_exists,
        "content_status": content,
        "mode_status": mode_status,
        "result": result,
    }
