#!/usr/bin/env python3
"""Move idle kvn-owned top-level /tmp entries off RAM-backed tmpfs (F22).

Agents keep writing ad-hoc scratch to hardcoded /tmp/<name> paths; tmpfs then
holds GBs of RAM until the 10-day systemd age. This moves (never deletes) each
top-level entry that is owned by us, untouched for IDLE_H hours, not open/mapped/
cwd of any process, to disk-backed agent-tmp, leaving a compatibility symlink.
Receipt: one JSON line per move in RECEIPTS.
"""
import json, os, shutil, sys, time

TMP = "/tmp"
DEST = os.path.expanduser("~/.cache/agent-tmp/tmp-evicted")
RECEIPTS = os.path.join(DEST, "receipts.jsonl")
IDLE_H = float(os.environ.get("TMP_EVICT_IDLE_H", "6"))
MIN_BYTES = 1 << 20
SKIP = (".X11-unix", ".ICE-unix", ".font-unix", ".XIM-unix", ".Test-unix",
        "systemd-private-", "tmux-", "files-live-deploy.lock", "claude-",
        "tsx-", "node-compile-cache", "hyprland", "tern")
DRY = "--dry-run" in sys.argv


def tree(p):
    """(apparent bytes, newest of mtime/ctime) without following symlinks."""
    st = os.lstat(p)
    size, newest = st.st_size, max(st.st_mtime, st.st_ctime)
    if os.path.isdir(p) and not os.path.islink(p):
        for root, dirs, files in os.walk(p, followlinks=False):
            for n in dirs + files:
                try:
                    s = os.lstat(os.path.join(root, n))
                except OSError:
                    continue
                newest = max(newest, s.st_mtime, s.st_ctime)
                if not os.path.isdir(os.path.join(root, n)):
                    size += s.st_size
    return size, newest


def in_use():
    """Every /tmp path some process has open, mapped or as cwd/exe."""
    used = set()
    for pid in filter(str.isdigit, os.listdir("/proc")):
        base = f"/proc/{pid}"
        try:
            for l in ("cwd", "exe", "root"):
                used.add(os.readlink(f"{base}/{l}"))
            for fd in os.listdir(f"{base}/fd"):
                try:
                    used.add(os.readlink(f"{base}/fd/{fd}"))
                except OSError:
                    pass
            with open(f"{base}/maps") as f:
                for line in f:
                    parts = line.split(None, 5)
                    if len(parts) == 6 and parts[5].startswith("/tmp/"):
                        used.add(parts[5].strip().removesuffix(" (deleted)"))
        except OSError:
            continue
    return {u for u in used if u.startswith("/tmp/")}


def main():
    uid, now = os.getuid(), time.time()
    used = in_use()
    os.makedirs(DEST, mode=0o700, exist_ok=True)
    moved = 0
    for name in sorted(os.listdir(TMP)):
        p = os.path.join(TMP, name)
        try:
            st = os.lstat(p)
        except OSError:
            continue
        if st.st_uid != uid or os.path.islink(p) or name.startswith(SKIP):
            continue
        if not (os.path.isdir(p) or os.path.isfile(p)):
            continue  # sockets, fifos
        if any(u == p or u.startswith(p + "/") for u in used):
            continue
        try:
            size, newest = tree(p)
        except OSError:
            continue
        if size < MIN_BYTES or now - newest < IDLE_H * 3600:
            continue
        dst = os.path.join(DEST, time.strftime("%Y%m%d"), name)
        rec = {"at": time.strftime("%F %T"), "src": p, "dst": dst, "bytes": size,
               "idle_h": round((now - newest) / 3600, 1)}
        if DRY:
            print(json.dumps(rec)); continue
        os.makedirs(os.path.dirname(dst), exist_ok=True)
        if os.path.lexists(dst):
            continue
        shutil.move(p, dst)  # cross-fs: copy then delete source
        os.symlink(dst, p)
        with open(RECEIPTS, "a") as f:
            f.write(json.dumps(rec) + "\n")
        moved += size
    print(f"tmp-evict: moved {moved} bytes (idle>{IDLE_H}h)")


if __name__ == "__main__":
    main()
