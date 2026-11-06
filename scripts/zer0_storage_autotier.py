#!/usr/bin/env python3
"""Automatic byte-and-inode reserve policy for the zer0 hot tier and the root disk.

/workspace is checked for a 30 GiB byte reserve and a 5% inode reserve. Only
allowlisted bulk directory names are moved, and worktrees stay put: moving one
behind Git's back can invalidate gitdir links.

/ is a 132 GB volume. A 40 GB floor cannot be held once /usr, /opt, containerd,
and home bulk are on it. The root policy acts when free space drops below
20 GB: it deletes crash dumps and two regenerable caches, then moves IDLE bulk
(ROOT_TIER_GLOBS, largest first) to /mnt/zer0models/home-offload/kvn/
offload-YYYY-MM-DD/<path under ~> and leaves a symlink at the original path.
The mover copies, verifies checksums, file count and bytes, and only then
removes the source; nothing is deleted outright. Idle means nothing inside was
modified (mtime or ctime) for ROOT_IDLE_DAYS, or ROOT_GIT_IDLE_DAYS for a git
checkout. A whole idle checkout may move: the symlink keeps its path. Symlinks,
paths held open or used as a cwd/exe by any process, and ROOT_PROTECT_GLOBS are
skipped. If the reserve still cannot be met, the owner gets a desktop
notification naming the top home space users and the run exits 75.
"""
from __future__ import annotations

import argparse
from datetime import date
import fnmatch
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import sys
import time
import tomllib

ROOT = Path("/workspace/zer0")
HOME = Path("/home/kvn")
ROOT_OFFLOAD = Path("/mnt/zer0models/home-offload/kvn")
RESERVE_GIB = 30
ROOT_RESERVE_GIB = 20
RESERVE_INODE_RATIO = 0.05
MIN_GIB = 0.5
ALLOWED_NAMES = {"shots", "artifacts", "outputs", "evidence", ".hf_cache", "checkpoints", "models", "datasets"}
EXCLUDED_PARTS = {".git", ".worktrees", "node_modules", ".venv", "venv", "dist", "build"}
# Live path contracts. Prefix match covers oh-my-pi-handsfree, omp-next, aodl-audit.
PROTECTED_TMP_PREFIXES = ("openjev", "z0evals", "oh-my-pi", "omp-", "aodl")
ROOT_CACHE_DIRS = (HOME / ".nv" / "ComputeCache", HOME / ".npm" / "_cacache")
# Root tiering sources, globbed relative to HOME. Each match is one candidate.
ROOT_TIER_GLOBS = (
    "tmp/*",
    "zer0/outputs/*",
    "zer0/oss/*",
    "zer0/quackles-work/*",
    "Downloads/*",
    ".local/share/uv",
    ".local/share/zerOS",
)
# Never moved, matched against the path relative to HOME. Keeps the ~/tmp prefixes above.
ROOT_PROTECT_GLOBS = tuple(f"tmp/{prefix}*" for prefix in PROTECTED_TMP_PREFIXES)
ROOT_IDLE_DAYS = 3
ROOT_GIT_IDLE_DAYS = 7
ROOT_MIN_MIB = 64
TOP_USERS = 5
MOVER = Path(__file__).with_name("zer0_storage_tier.py")
# Hard floor: below this share of / free, the owner is alerted (critical) and
# STATE_DIR/root-low.json exists so launchers can refuse heavy work
# (`zer0_storage_autotier.py --check` exits 75 while it holds).
ROOT_FLOOR_PCT = 10.0
# Per-agent scratch TTL. 0 disables. Idle scratch (nothing changed for the TTL)
# is moved by the verified mover into SCRATCH_QUARANTINE/scratch-ttl-<date>/
# behind a compat symlink and recorded in that dir's MANIFEST.jsonl. Never rm.
SCRATCH_TTL_DAYS = 0.0
SCRATCH_GLOBS: tuple[str, ...] = ("tmp/*",)
SCRATCH_KEEP_GLOBS: tuple[str, ...] = ()
SCRATCH_MIN_MIB = 16
SCRATCH_QUARANTINE = Path("/mnt/zer0models/quarantine")
STATE_DIR = HOME / ".local" / "state" / "zer0-storage-autotier"
ALERT_REPEAT_SECONDS = 6 * 3600


def _home_relative_globs(items: object, key: str) -> tuple[str, ...]:
    items = tuple(items or ())  # type: ignore[arg-type]
    if any(not isinstance(item, str) or Path(item).is_absolute() or ".." in Path(item).parts for item in items):
        raise ValueError(f"{key} must be home-relative paths")
    return items


# Host policy is versioned in .files; its absence preserves legacy defaults.
POLICY_PATH = Path(os.environ.get("ZER0_STORAGE_POLICY", str(HOME / ".config/zer0/storage.toml")))
if POLICY_PATH.exists():
    with POLICY_PATH.open("rb") as stream:
        policy = tomllib.load(stream)
    ROOT_RESERVE_GIB = int(policy.get("root_reserve_gib", ROOT_RESERVE_GIB))
    ROOT_FLOOR_PCT = float(policy.get("root_floor_pct", ROOT_FLOOR_PCT))
    SCRATCH_TTL_DAYS = float(policy.get("scratch_ttl_days", SCRATCH_TTL_DAYS))
    SCRATCH_GLOBS = _home_relative_globs(policy.get("scratch_globs", SCRATCH_GLOBS), "scratch_globs")
    SCRATCH_KEEP_GLOBS = _home_relative_globs(policy.get("scratch_keep_globs", ()), "scratch_keep_globs")
    additions = _home_relative_globs(policy.get("idle_cache_globs", ()), "idle_cache_globs")
    ROOT_TIER_GLOBS += additions
    # Managed caches are preserved by the verified mover, not deleted first.
    ROOT_CACHE_DIRS = tuple(path for path in ROOT_CACHE_DIRS
                            if path.relative_to(HOME).as_posix() not in additions)


# Regenerable-junk prune. Runs before the move phase when / is under its
# reserve, and once per day regardless. Deletes only things a tool rebuilds.
PRUNE_STAMP = HOME / ".local" / "state" / "zer0-storage-autotier" / "last-prune"
PRUNE_FORBIDDEN = (Path("/mnt/zer0models"),)  # resolved paths under these are never pruned
PRUNE_PROJECT_ROOTS = (HOME, Path("/workspace"))  # hidden top-level dirs of HOME are tool state, skipped
PRUNE_IDLE_DAYS = 7
PKG = ("package.json",)
PY = ("pyproject.toml", "setup.py", "requirements.txt")
BUILD = ("package.json", "pyproject.toml", "Cargo.toml")
# Dir name -> manifest that must sit beside it (None: always regenerable).
PRUNE_DIRS: dict[str, tuple[str, ...] | None] = {
    "node_modules": PKG, ".next": PKG, ".turbo": PKG,
    "dist": BUILD, "build": BUILD, "target": ("Cargo.toml",),
    ".venv": PY, "venv": PY,
    "__pycache__": None, ".pytest_cache": None, ".mypy_cache": None,
}
VERSION_DIRS = (HOME / ".local" / "share" / "claude" / "versions", HOME / ".local" / "share" / "cursor-agent" / "versions")
KEEP_VERSIONS = 2
CORE_MIN_AGE = 3600
TOOL_PATH = os.pathsep.join([os.environ.get("PATH", ""), str(HOME / ".local" / "bin"), "/usr/bin"])


def allocated_bytes(path: Path) -> int:
    result = subprocess.run(["du", "-sx", "-B1", str(path)], text=True, stdout=subprocess.PIPE, check=True)
    return int(result.stdout.split()[0])


def discover() -> list[tuple[int, Path]]:
    found: list[tuple[int, Path]] = []
    for current, dirs, _files in os.walk(ROOT):
        parent = Path(current)
        dirs[:] = [d for d in dirs if d not in EXCLUDED_PARTS and not (parent / d).is_symlink()]
        for name in list(dirs):
            path = parent / name
            if name not in ALLOWED_NAMES:
                continue
            size = allocated_bytes(path)
            if size >= int(MIN_GIB * 1024**3):
                found.append((size, path))
            dirs.remove(name)  # never choose a nested child as a second migration
    return sorted(found, reverse=True)


def capacity(path: str = "/workspace", reserve_gib: float | None = None) -> dict[str, int | float | bool]:
    reserve = RESERVE_GIB if reserve_gib is None else reserve_gib
    stat = os.statvfs(path)
    free_bytes = stat.f_bavail * stat.f_frsize
    total_inodes = stat.f_files
    free_inodes = stat.f_favail
    inode_ratio = free_inodes / total_inodes if total_inodes else 1.0
    return {
        "free_bytes": free_bytes,
        "free_inodes": free_inodes,
        "total_inodes": total_inodes,
        "free_inode_ratio": inode_ratio,
        "bytes_ok": free_bytes >= reserve * 1024**3,
        "inodes_ok": inode_ratio >= RESERVE_INODE_RATIO,
    }


def idle_days_for(path: Path) -> int:
    return ROOT_GIT_IDLE_DAYS if (path / ".git").exists() else ROOT_IDLE_DAYS


def is_idle(path: Path, days: float | None = None) -> bool:
    """True when neither path nor anything under it changed within the window."""
    cutoff = time.time() - (idle_days_for(path) if days is None else days) * 86400

    def recent(entry: Path) -> bool:
        try:
            st = entry.lstat()
        except OSError:
            return False
        return max(st.st_mtime, st.st_ctime) >= cutoff

    if recent(path):
        return False
    if path.is_symlink() or not path.is_dir():
        return True
    for current, dirs, files in os.walk(path):  # does not follow symlinked dirs
        parent = Path(current)
        if any(recent(parent / name) for name in [*dirs, *files]):
            return False
    return True


def paths_in_use(proc: Path = Path("/proc")) -> set[str]:
    """Every path a process holds open, runs from, or uses as its cwd."""
    used: set[str] = set()
    for pid in proc.iterdir():
        if not pid.name.isdigit():
            continue
        links = [pid / "cwd", pid / "exe"]
        try:
            links.extend((pid / "fd").iterdir())
        except OSError:
            pass
        for link in links:
            try:
                used.add(os.readlink(link).removesuffix(" (deleted)"))
            except OSError:
                pass
    return used


def in_use(path: Path, used: set[str]) -> bool:
    target = str(path)
    prefix = target + os.sep
    return any(item == target or item.startswith(prefix) for item in used)


def _root_protected(path: Path) -> bool:
    try:
        relative = path.relative_to(HOME).as_posix()
    except ValueError:
        return True
    return any(fnmatch.fnmatch(relative, pattern) for pattern in ROOT_PROTECT_GLOBS)


def on_home_device(path: Path) -> bool:
    """True when path really lives on HOME's filesystem (/ on groot).

    A glob can reach another filesystem through a symlinked parent (for example
    ~/zer0/quackles-work -> /workspace/...). Moving such a path frees nothing on /
    and only duplicates bytes on the capacity drive.
    """
    try:
        return os.stat(path).st_dev == os.stat(HOME).st_dev
    except OSError:
        return False


def discover_root_candidates(used: set[str] | None = None) -> list[tuple[int, Path]]:
    """Idle, unused, unprotected bulk under ROOT_TIER_GLOBS, largest first."""
    used = paths_in_use() if used is None else used
    minimum = ROOT_MIN_MIB * 1024**2
    found: list[tuple[int, Path]] = []
    seen: set[Path] = set()
    for pattern in ROOT_TIER_GLOBS:
        for path in sorted(HOME.glob(pattern)):
            if path in seen or path.is_symlink() or not (path.is_dir() or path.is_file()):
                continue
            seen.add(path)
            if not on_home_device(path):
                print(f"root skip other-filesystem {path}", flush=True)
                continue
            if _root_protected(path):
                print(f"root skip protected {path}", flush=True)
                continue
            if in_use(path, used):
                print(f"root skip in-use {path}", flush=True)
                continue
            if not is_idle(path):
                continue
            size = allocated_bytes(path)
            if size >= minimum:
                found.append((size, path))
    return sorted(found, reverse=True)


def top_space_users(home: Path | None = None, limit: int = TOP_USERS) -> list[tuple[int, Path]]:
    """Largest second-level directories under home, for the owner's notification."""
    root = home or HOME
    result = subprocess.run(
        ["du", "-x", "-B1", "--max-depth=2", str(root)],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    rows: list[tuple[int, Path]] = []
    for line in result.stdout.splitlines():
        size, _, raw = line.partition("\t")
        path = Path(raw)
        if size.isdigit() and len(path.relative_to(root).parts) == 2:
            rows.append((int(size), path))
    return sorted(rows, reverse=True)[:limit]


PHONE_NOTIFY = HOME / ".local" / "bin" / "z0-phone-notify"


def notify(title: str, body: str, critical: bool = False) -> None:
    """Desktop notification plus the owner's phone, at most once per ALERT_REPEAT_SECONDS per title class.

    The desktop notifier is masked on headless sessions, so the phone path
    (z0-phone-notify, circadian-gated unless critical) is the one that reaches
    the owner. Both fail open.
    """
    stamp = STATE_DIR / ("alert-critical" if critical else "alert-low")
    try:
        if time.time() - stamp.stat().st_mtime < ALERT_REPEAT_SECONDS:
            print(f"alert suppressed (sent within {ALERT_REPEAT_SECONDS}s): {title}", flush=True)
            return
    except OSError:
        pass
    try:
        subprocess.run(
            ["notify-send", "-u", "critical", "-a", "zer0-storage-autotier", title, body],
            check=False,
            timeout=15,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        print(f"notify-send failed: {exc}", flush=True)
    if PHONE_NOTIFY.exists():
        env = {**os.environ, "CIRCADIAN_CLASS": "critical" if critical else "report"}
        try:
            subprocess.run([str(PHONE_NOTIFY), "root-disk", title, body], check=False, timeout=60,
                           env=env, stdin=subprocess.DEVNULL, capture_output=True)
        except (OSError, subprocess.TimeoutExpired) as exc:
            print(f"phone notify failed: {exc}", flush=True)
    try:
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        stamp.touch()
    except OSError:
        pass


def root_free_pct(path: str = "/") -> tuple[float, int]:
    stat = os.statvfs(path)
    free = stat.f_bavail * stat.f_frsize
    total = stat.f_blocks * stat.f_frsize
    return (100.0 * free / total if total else 100.0), free


def enforce_root_floor(apply: bool) -> int:
    """Keep STATE_DIR/root-low.json in step with the hard floor; alert when breached."""
    pct, free = root_free_pct()
    flag = STATE_DIR / "root-low.json"
    low = pct < ROOT_FLOOR_PCT
    print(f"root floor free_pct={pct:.1f} floor_pct={ROOT_FLOOR_PCT} low={low}", flush=True)
    if not apply:
        return 75 if low else 0
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    if not low:
        flag.unlink(missing_ok=True)
        return 0
    flag.write_text(json.dumps({"ts": time.time(), "free_bytes": free, "free_pct": round(pct, 2),
                                "floor_pct": ROOT_FLOOR_PCT}) + "\n")
    top = top_space_users()
    listing = "\n".join(f"{size / 1024**3:.1f} GiB  {path}" for size, path in top)
    notify(f"Root disk CRITICAL: {pct:.1f}% free (< {ROOT_FLOOR_PCT:g}%); heavy work should refuse", listing, critical=True)
    return 75


def check_root_floor() -> int:
    """Read-only admission check for launchers: 0 = ok, 75 = refuse heavy work."""
    pct, free = root_free_pct()
    low = pct < ROOT_FLOOR_PCT
    print(json.dumps({"free_bytes": free, "free_pct": round(pct, 2), "floor_pct": ROOT_FLOOR_PCT, "ok": not low}))
    return 75 if low else 0


def _scratch_kept(path: Path) -> bool:
    relative = path.relative_to(HOME).as_posix()
    return _root_protected(path) or any(fnmatch.fnmatch(relative, pattern) for pattern in SCRATCH_KEEP_GLOBS)


def ttl_scratch(apply: bool) -> int:
    """Quarantine per-agent scratch idle for SCRATCH_TTL_DAYS (verified move + symlink, never rm)."""
    if SCRATCH_TTL_DAYS <= 0:
        return 0
    used = paths_in_use_deep()
    minimum = SCRATCH_MIN_MIB * 1024**2
    stamp = f"{date.today():%Y-%m-%d}"
    quarantine = SCRATCH_QUARANTINE / f"scratch-ttl-{stamp}"
    destination_root = quarantine / HOME.relative_to(HOME.anchor)
    code = 0
    for pattern in SCRATCH_GLOBS:
        for path in sorted(HOME.glob(pattern)):
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                continue
            if _scratch_kept(path) or not on_home_device(path) or (path / ".git").exists():
                continue
            if in_use(path, used) or not is_idle(path, days=SCRATCH_TTL_DAYS):
                continue
            size = allocated_bytes(path)
            if size < minimum:
                continue
            destination = destination_root / path.relative_to(HOME)
            if destination.exists() or destination.is_symlink():
                print(f"scratch skip {path}: quarantine slot taken {destination}", flush=True)
                continue
            mtime = path.lstat().st_mtime
            print(f"scratch {'quarantine' if apply else 'would quarantine'} {path} bytes={size} -> {destination}", flush=True)
            if not apply:
                continue
            if _run_mover(True, [str(path)], source_root=HOME, destination_root=destination_root) != 0:
                print(f"scratch skip {path}: mover refused or failed; source left in place", flush=True)
                code = 1
                continue
            quarantine.mkdir(parents=True, exist_ok=True)
            with (quarantine / "MANIFEST.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps({"ts": time.time(), "src": str(path), "dst": str(destination), "bytes": size,
                                     "mtime": mtime, "why": f"scratch idle >= {SCRATCH_TTL_DAYS:g}d",
                                     "mode": "verified-move+symlink"}) + "\n")
    return code


def offload_destination() -> Path:
    return ROOT_OFFLOAD / f"offload-{date.today():%Y-%m-%d}"


def reclaim_root_junk(apply: bool) -> int:
    """Delete crash dumps and regenerable caches that sit directly on /."""
    freed = 0
    for core in HOME.glob("core.*"):
        suffix = core.name.removeprefix("core.")
        if not suffix.isdigit() or core.is_symlink() or not core.is_file():
            continue
        size = core.stat().st_size
        print(f"root junk core {core} bytes={size} apply={apply}", flush=True)
        if apply:
            core.unlink()
        freed += size
    for cache in ROOT_CACHE_DIRS:
        if cache.is_symlink() or not cache.is_dir():
            continue
        size = allocated_bytes(cache)
        print(f"root junk cache {cache} bytes={size} apply={apply}", flush=True)
        if apply:
            shutil.rmtree(cache)
        freed += size
    return freed


def _forbidden(path: Path) -> bool:
    real = Path(os.path.realpath(path))
    return any(real == root or root in real.parents for root in PRUNE_FORBIDDEN)


def remove_path(path: Path, kind: str, apply: bool) -> int:
    """Delete one regenerable path, logging its size. Returns bytes freed (or that would be)."""
    if _forbidden(path):
        print(f"prune skip forbidden {kind} {path}", flush=True)
        return 0
    if not path.exists() and not path.is_symlink():
        return 0
    size = allocated_bytes(path)
    print(f"prune {'delete' if apply else 'would delete'} {kind} {path} bytes={size}", flush=True)
    if not apply:
        return size
    try:
        if path.is_dir() and not path.is_symlink():
            for current, dirs, _files in os.walk(path):  # cargo/go trees are read-only
                os.chmod(current, os.stat(current).st_mode | 0o200)
            shutil.rmtree(path)
        else:
            path.unlink()
    except OSError as exc:
        print(f"prune failed {kind} {path}: {exc}", flush=True)
        return 0
    return size


def paths_in_use_deep(proc: Path = Path("/proc")) -> set[str]:
    """paths_in_use plus mapped files and absolute cmdline args (venv pythons, node bins)."""
    used = paths_in_use(proc)
    for pid in proc.iterdir():
        if not pid.name.isdigit():
            continue
        try:
            used.update(arg for arg in (pid / "cmdline").read_bytes().decode(errors="replace").split("\0") if arg.startswith("/"))
            for line in (pid / "maps").read_text(errors="replace").splitlines():
                field = line.split(maxsplit=5)
                if len(field) == 6 and field[5].startswith("/"):
                    used.add(field[5].removesuffix(" (deleted)"))
        except OSError:
            pass
    return used


def referenced_text() -> str:
    """systemd unit files and the crontab: a build dir named there is a live dependency."""
    chunks = []
    for base in (HOME / ".config" / "systemd" / "user", Path("/etc/systemd/system")):
        for path in base.rglob("*") if base.is_dir() else ():
            try:
                if path.is_file():
                    chunks.append(path.read_text(errors="replace"))
            except OSError:
                pass
    try:
        chunks.append(subprocess.run(["crontab", "-l"], text=True, capture_output=True, check=False).stdout)
    except OSError:
        pass
    return "\n".join(chunks)


def _git_root(path: Path, scan_root: Path) -> Path | None:
    for parent in path.parents:
        if (parent / ".git").exists():
            return parent
        if parent == scan_root:
            return None
    return None


def _project_idle(root: Path, cutoff: float) -> bool:
    for current, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in PRUNE_DIRS and d != ".git"]
        for name in files:
            try:
                st = os.lstat(os.path.join(current, name))
            except OSError:
                continue
            if max(st.st_mtime, st.st_ctime) >= cutoff:
                return False
    return True


def _tracked(root: Path) -> list[str]:
    result = subprocess.run(["git", "-C", str(root), "ls-files", "-z"], capture_output=True, check=False)
    if result.returncode != 0:
        return [""]  # unreadable index: treat the whole checkout as tracked
    return [str(root / name) for name in result.stdout.decode(errors="replace").split("\0") if name]


def find_prune_targets(used: set[str]) -> list[Path]:
    """Build/dependency dirs inside idle, unused git projects that no unit names and git does not track."""
    cutoff = time.time() - PRUNE_IDLE_DAYS * 86400
    referenced = referenced_text()
    found: list[tuple[Path, Path]] = []
    for scan_root in PRUNE_PROJECT_ROOTS:
        if not scan_root.is_dir() or _forbidden(scan_root):
            continue
        for current, dirs, _files in os.walk(scan_root):
            parent = Path(current)
            keep = []
            for name in dirs:
                path = parent / name
                if name == ".git" or path.is_symlink() or (parent == HOME and name.startswith(".")):
                    continue
                if _forbidden(path) or (scan_root == HOME and _root_protected(path)):
                    continue
                if name in PRUNE_DIRS:
                    root = _git_root(path, scan_root)
                    if root is not None:
                        found.append((root, path))
                    continue
                keep.append(name)
            dirs[:] = keep
    targets: list[Path] = []
    projects: dict[Path, tuple[bool, list[str]]] = {}
    for root, path in found:
        if root not in projects:
            ok = not in_use(root, used) and _project_idle(root, cutoff)
            projects[root] = (ok, _tracked(root) if ok else [])
        ok, tracked = projects[root]
        if not ok:
            continue
        manifests = PRUNE_DIRS[path.name]
        if manifests and not any((path.parent / m).is_file() for m in manifests):
            continue
        if str(path) in referenced or "" in tracked or in_use(path, set(tracked)):
            continue
        targets.append(path)
    return targets


def prune_versions(apply: bool, used: set[str], dirs: tuple[Path, ...] | None = None) -> int:
    freed = 0
    links = {os.path.realpath(p) for p in (HOME / ".local" / "bin").glob("*") if p.is_symlink()}
    for base in VERSION_DIRS if dirs is None else dirs:
        if not base.is_dir():
            continue
        entries = sorted((p for p in base.iterdir() if not p.is_symlink()), key=lambda p: p.lstat().st_mtime, reverse=True)
        for path in entries[KEEP_VERSIONS:]:
            if in_use(path, used) or in_use(path, links):
                print(f"prune keep running cli-version {path}", flush=True)
                continue
            freed += remove_path(path, "cli-version", apply)
    return freed


def _is_core_dump(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            head = fh.read(18)
    except OSError:
        return False
    return len(head) == 18 and head[:4] == b"\x7fELF" and int.from_bytes(head[16:18], "little" if head[5] == 1 else "big") == 4


def prune_core_dumps(apply: bool) -> int:
    freed = 0
    cutoff = time.time() - CORE_MIN_AGE
    for path in [*HOME.glob("core"), *HOME.glob("core.*")]:
        if path.is_symlink() or not path.is_file() or path.stat().st_mtime > cutoff or not _is_core_dump(path):
            continue
        freed += remove_path(path, "core-dump", apply)
    return freed


def _version_key(path: Path) -> tuple[int, ...]:
    return tuple(int(n) for n in re.findall(r"\d+", path.name))


def _run_cache_tool(label: str, command: list[str], cache: Path, apply: bool) -> int:
    exe = shutil.which(command[0], path=TOOL_PATH)
    if exe is None or not cache.exists():
        return 0
    if _forbidden(cache):
        print(f"prune skip forbidden tool-cache {label} {cache}", flush=True)
        return 0
    before = allocated_bytes(cache)
    if not apply:
        print(f"prune would run {' '.join(command)} on {cache} bytes<={before}", flush=True)
        return 0
    subprocess.run([exe, *command[1:]], check=False, capture_output=True, timeout=1800)
    freed = before - (allocated_bytes(cache) if cache.exists() else 0)
    print(f"prune ran {' '.join(command)} on {cache} freed={freed}", flush=True)
    return freed


def prune_tool_caches(apply: bool) -> int:
    cache = HOME / ".cache"
    freed = _run_cache_tool("uv", ["uv", "cache", "prune"], Path(os.environ.get("UV_CACHE_DIR", cache / "uv")), apply)
    freed += _run_cache_tool("pip", ["pip", "cache", "purge"], cache / "pip", apply)
    freed += _run_cache_tool("go", ["go", "clean", "-cache"], Path(os.environ.get("GOCACHE", cache / "go-build")), apply)
    for path in (
        HOME / ".npm" / "_cacache",  # what `npm cache clean --force` removes
        HOME / ".gradle" / "caches",
        HOME / ".cargo" / "registry" / "cache",
        HOME / ".cargo" / "registry" / "src",
        HOME / ".bun" / "install" / "cache",
    ):
        freed += remove_path(path, "tool-cache", apply)
    groups: dict[tuple[Path, str], list[Path]] = {}
    for base in (cache / "ms-playwright",):
        for path in base.glob("*") if base.is_dir() else ():
            groups.setdefault((base, re.sub(r"-\d+$", "", path.name)), []).append(path)
    for base in (cache / "puppeteer",):
        for path in base.glob("*/*") if base.is_dir() else ():
            groups.setdefault((path.parent, ""), []).append(path)
    for paths in groups.values():
        for path in sorted(paths, key=_version_key)[:-1]:
            freed += remove_path(path, "browser-cache", apply)
    return freed


def prune_flatpak(apply: bool) -> int:
    exe = shutil.which("flatpak", path=TOOL_PATH)
    store = HOME / ".local" / "share" / "flatpak"
    if exe is None or not store.is_dir():
        return 0
    if not apply:
        print("prune would run flatpak uninstall --user --unused -y", flush=True)
        return 0
    before = allocated_bytes(store)
    subprocess.run([exe, "uninstall", "--user", "--unused", "-y"], check=False, capture_output=True, timeout=1800)
    freed = before - allocated_bytes(store)
    print(f"prune ran flatpak uninstall --user --unused freed={freed}", flush=True)
    return freed


def prune_regenerable(apply: bool) -> int:
    used = paths_in_use_deep()
    freed = prune_versions(apply, used)
    for path in find_prune_targets(used):
        freed += remove_path(path, "project-cache", apply)
    freed += prune_tool_caches(apply) + prune_core_dumps(apply) + prune_flatpak(apply)
    print(f"prune total bytes={freed} apply={apply}", flush=True)
    return freed


def prune_due(root_low: bool) -> bool:
    try:
        last = PRUNE_STAMP.read_text().strip()
    except OSError:
        last = ""
    return root_low or last != f"{date.today():%Y-%m-%d}"


def mark_pruned() -> None:
    PRUNE_STAMP.parent.mkdir(parents=True, exist_ok=True)
    PRUNE_STAMP.write_text(f"{date.today():%Y-%m-%d}\n")


def maybe_prune(apply: bool) -> None:
    root_low = not capacity("/", reserve_gib=ROOT_RESERVE_GIB)["bytes_ok"]
    if not prune_due(root_low):
        return
    prune_regenerable(apply)
    if apply:
        mark_pruned()


def _select_until(free: int, reserve: int, candidates: list[tuple[int, Path]]) -> tuple[list[str], int]:
    selected: list[str] = []
    projected = free
    for size, path in candidates:
        selected.append(str(path))
        projected += size
        if projected >= reserve:
            break
    return selected, projected


def _run_mover(apply: bool, selected: list[str], source_root: Path | None = None, destination_root: Path | None = None) -> int:
    command = [sys.executable, str(MOVER)]
    if apply:
        command.append("--apply")
    if source_root is not None:
        command.extend(["--source-root", str(source_root)])
    if destination_root is not None:
        command.extend(["--destination-root", str(destination_root)])
    command.extend(selected)
    return subprocess.run(command, check=False).returncode


def tier_workspace(apply: bool) -> int:
    reserve = RESERVE_GIB * 1024**3
    state = capacity("/workspace")
    free = int(state["free_bytes"])
    print(f"workspace capacity={state}", flush=True)
    if state["bytes_ok"] and state["inodes_ok"]:
        print(f"workspace byte+inode reserve satisfied: free={free} reserve={reserve}")
        return 0
    candidates = discover()
    if not candidates:
        print("CRITICAL: reserve breached with no safe bulk candidates; dispatcher must remain frozen; worktrees require reviewed migration")
        return 75
    selected, projected = _select_until(free, reserve, candidates)
    print(f"workspace free={free}; selected={selected}; projected={projected}", flush=True)
    return _run_mover(apply, selected, source_root=ROOT)


def tier_root(apply: bool) -> int:
    reserve = ROOT_RESERVE_GIB * 1024**3
    state = capacity("/", reserve_gib=ROOT_RESERVE_GIB)
    free = int(state["free_bytes"])
    print(f"root capacity={state}", flush=True)
    if state["bytes_ok"] and state["inodes_ok"]:
        print(f"root byte reserve satisfied: free={free} reserve={reserve}")
        return 0
    reclaim_root_junk(apply)
    state = capacity("/", reserve_gib=ROOT_RESERVE_GIB)
    free = int(state["free_bytes"])
    if state["bytes_ok"] and state["inodes_ok"]:
        print(f"root byte reserve restored by junk reclaim: free={free} reserve={reserve}")
        return 0
    destination_root = offload_destination()
    candidates = discover_root_candidates()
    print(f"root free={free}; reserve={reserve}; idle candidates={len(candidates)}", flush=True)
    projected = free
    for size, path in candidates:
        if projected >= reserve:
            break
        destination = destination_root / path.relative_to(HOME)
        if destination.exists() or destination.is_symlink():
            print(f"root skip {path}: destination already exists {destination}", flush=True)
            continue
        verb = "move" if apply else "would move"
        print(f"root {verb} {path} bytes={size} -> {destination}", flush=True)
        if _run_mover(apply, [str(path)], source_root=HOME, destination_root=destination_root) != 0:
            print(f"root skip {path}: mover refused or failed; source left in place", flush=True)
            continue
        projected = int(capacity("/", reserve_gib=ROOT_RESERVE_GIB)["free_bytes"]) if apply else projected + size
    print(f"root projected free={projected} reserve={reserve} apply={apply}", flush=True)
    if projected < reserve:
        top = top_space_users()
        listing = "\n".join(f"{size / 1024**3:.1f} GiB  {path}" for size, path in top)
        print(f"CRITICAL: root reserve still short after tiering every safe idle candidate; top space users:\n{listing}")
        if apply:  # a dry run is a diagnostic; only the real run alerts the owner
            notify(f"Root disk low: {projected / 1024**3:.1f} GiB free (< {ROOT_RESERVE_GIB} GiB)", listing)
        return 75
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true")
    mode.add_argument("--dry-run", action="store_true", help="the default; report without changing anything")
    mode.add_argument("--check", action="store_true", help="read-only root floor admission check; exits 75 below the floor")
    args = parser.parse_args()
    if args.check:
        return check_root_floor()
    codes = [tier_workspace(args.apply)]
    maybe_prune(args.apply)  # before the move phase, so moves only cover what pruning could not
    codes.append(tier_root(args.apply))
    ttl_scratch(args.apply)
    codes.append(enforce_root_floor(args.apply))
    if 75 in codes:
        return 75
    return next((code for code in codes if code), 0)


if __name__ == "__main__":
    raise SystemExit(main())
