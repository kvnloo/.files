from __future__ import annotations

import importlib.util
import os
from pathlib import Path
import subprocess
import shutil
import sys
import time

import pytest


SCRIPT = Path(__file__).parents[1] / "scripts" / "zer0_storage_autotier.py"
SPEC = importlib.util.spec_from_file_location("zer0_storage_autotier", SCRIPT)
assert SPEC and SPEC.loader
autotier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(autotier)


def test_managed_policy_adds_preserved_idle_caches(tmp_path):
    policy = tmp_path / "storage.toml"
    policy.write_text('root_reserve_gib = 20\nidle_cache_globs = [".npm/_cacache", ".cargo/registry"]\n')
    code = (
        "import runpy; p=runpy.run_path(" + repr(str(SCRIPT)) + "); "
        "assert '.cargo/registry' in p['ROOT_TIER_GLOBS']; "
        "assert p['HOME']/'.npm/_cacache' not in p['ROOT_CACHE_DIRS']; "
        "assert p['ROOT_RESERVE_GIB']==20"
    )
    subprocess.run([sys.executable, "-c", code], env={**os.environ, "ZER0_STORAGE_POLICY": str(policy)}, check=True)


def test_managed_policy_rejects_escape(tmp_path):
    policy = tmp_path / "storage.toml"
    policy.write_text('idle_cache_globs = ["../user-data"]\n')
    result = subprocess.run([sys.executable, "-c", "import runpy; runpy.run_path(" + repr(str(SCRIPT)) + ")"],
                            env={**os.environ, "ZER0_STORAGE_POLICY": str(policy)}, capture_output=True, text=True)
    assert result.returncode != 0
    assert "home-relative paths" in result.stderr


@pytest.fixture(autouse=True)
def _no_real_prune(monkeypatch):
    """main() calls maybe_prune; never let a test prune the real machine."""
    monkeypatch.setattr(autotier, "maybe_prune", lambda apply: None)
    monkeypatch.setattr(autotier, "PRUNE_PROJECT_ROOTS", ())
    monkeypatch.setattr(autotier, "VERSION_DIRS", ())
    monkeypatch.setattr(autotier, "prune_tool_caches", lambda apply: 0)
    monkeypatch.setattr(autotier, "prune_flatpak", lambda apply: 0)
    monkeypatch.setattr(autotier, "PRUNE_STAMP", Path("/nonexistent/zer0-autotier-test-stamp"))


class Stat:
    f_bavail = 8
    f_frsize = 1024**3
    f_files = 100
    f_favail = 4


def test_capacity_requires_byte_and_inode_reserves(monkeypatch):
    monkeypatch.setattr(autotier.os, "statvfs", lambda _path: Stat())
    state = autotier.capacity("/fake")
    assert state["bytes_ok"] is False
    assert state["inodes_ok"] is False
    assert state["free_bytes"] == 8 * 1024**3
    assert state["free_inode_ratio"] == 0.04


def _critical(**overrides):
    state = {
        "free_bytes": 1,
        "free_inodes": 1,
        "total_inodes": 100,
        "free_inode_ratio": 0.01,
        "bytes_ok": False,
        "inodes_ok": False,
    }
    state.update(overrides)
    return state


def _healthy():
    return _critical(free_bytes=50 * 1024**3, free_inode_ratio=0.5, bytes_ok=True, inodes_ok=True)


def test_no_safe_candidate_is_visible_failure(monkeypatch, capsys):
    notes = []
    monkeypatch.setattr(autotier, "capacity", lambda *_args, **_kwargs: _critical())
    monkeypatch.setattr(autotier, "discover", lambda: [])
    monkeypatch.setattr(autotier, "discover_root_candidates", lambda: [])
    monkeypatch.setattr(autotier, "reclaim_root_junk", lambda _apply: 0)
    monkeypatch.setattr(autotier, "top_space_users", lambda: [(9, Path("/home/kvn/zer0/oss"))])
    monkeypatch.setattr(autotier, "notify", lambda title, body: notes.append((title, body)))
    monkeypatch.setattr(autotier.sys, "argv", [str(SCRIPT), "--apply"])
    assert autotier.main() == 75
    output = capsys.readouterr().out
    assert "dispatcher must remain frozen" in output
    assert "root reserve still short" in output
    assert notes and "/home/kvn/zer0/oss" in notes[0][1]


def test_workspace_ok_still_tiers_root_candidates(monkeypatch, capsys):
    calls = []

    def cap(path="/workspace", reserve_gib=None):
        if path == "/":
            # Rises once the first move lands, as the real disk would.
            free = 30 if calls else 8
            return _critical(free_bytes=free * 1024**3, bytes_ok=free >= 20, inodes_ok=True, free_inode_ratio=0.5)
        return _healthy()

    class Result:
        returncode = 0

    def run(cmd, check=False):
        calls.append(cmd)
        return Result()

    monkeypatch.setattr(autotier, "capacity", cap)
    monkeypatch.setattr(autotier, "reclaim_root_junk", lambda _apply: 0)
    monkeypatch.setattr(
        autotier,
        "discover_root_candidates",
        lambda: [(22 * 1024**3, autotier.HOME / "tmp" / "scratch")],
    )
    monkeypatch.setattr(autotier.subprocess, "run", run)
    monkeypatch.setattr(autotier.sys, "argv", [str(SCRIPT), "--apply"])
    assert autotier.main() == 0
    assert len(calls) == 1
    command = calls[0]
    assert "--apply" in command
    assert command[command.index("--source-root") + 1] == str(autotier.HOME)
    assert command[command.index("--destination-root") + 1].startswith(str(autotier.ROOT_OFFLOAD / "offload-"))
    assert str(autotier.HOME / "tmp" / "scratch") in command
    assert "root move" in capsys.readouterr().out


def test_root_protect_list_keeps_tmp_checkout_prefixes(monkeypatch, tmp_path):
    monkeypatch.setattr(autotier, "HOME", tmp_path)
    for name in ("openjev", "z0evals", "oh-my-pi-handsfree", "omp-next", "aodl", "aodl-audit"):
        assert autotier._root_protected(tmp_path / "tmp" / name)
    assert not autotier._root_protected(tmp_path / "tmp" / "scratch")
    assert not autotier._root_protected(tmp_path / "zer0" / "oss" / "oh-my-pi")
    assert autotier._root_protected(Path("/elsewhere/tmp/scratch"))


def test_reclaim_root_junk_deletes_only_named_caches(monkeypatch, tmp_path):
    home = tmp_path / "home"
    home.mkdir()
    core = home / "core.1251691"
    core.write_bytes(b"x" * 32)
    (home / "core.not-a-dump").write_bytes(b"keep")
    cache = home / ".nv" / "ComputeCache"
    cache.mkdir(parents=True)
    (cache / "blob").write_bytes(b"y" * 16)
    npm = home / ".npm" / "_cacache"
    npm.mkdir(parents=True)
    monkeypatch.setattr(autotier, "HOME", home)
    monkeypatch.setattr(autotier, "ROOT_CACHE_DIRS", (cache, npm))
    monkeypatch.setattr(autotier, "allocated_bytes", lambda path: sum(p.stat().st_size for p in path.rglob("*") if p.is_file()))
    freed = autotier.reclaim_root_junk(True)
    assert freed == 48
    assert not core.exists()
    assert (home / "core.not-a-dump").is_file()
    assert not cache.exists()
    assert not npm.exists()

# --- widened root policy -------------------------------------------------

MOVER_SPEC = importlib.util.spec_from_file_location("zer0_storage_tier", SCRIPT.with_name("zer0_storage_tier.py"))
assert MOVER_SPEC and MOVER_SPEC.loader
mover = importlib.util.module_from_spec(MOVER_SPEC)
MOVER_SPEC.loader.exec_module(mover)

DAY = 86400
GIB = 1024**3


def _age(path: Path, days: float, now: float) -> None:
    """Backdate path and everything under it (mtime; ctime cannot be faked)."""
    stamp = now - days * DAY
    for current, dirs, files in os.walk(path):
        for name in [*dirs, *files]:
            os.utime(Path(current) / name, (stamp, stamp), follow_symlinks=False)
    os.utime(path, (stamp, stamp), follow_symlinks=False)


def _tree(root: Path, relative: str, days: float, now: float, git: bool = False) -> Path:
    path = root / relative
    path.mkdir(parents=True)
    (path / "data.bin").write_bytes(b"x" * 64)
    if git:
        (path / ".git").mkdir()
        (path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")
    _age(path, days, now)
    return path


@pytest.fixture
def clock(monkeypatch):
    # ctime is always "now" in a fresh temp tree, so idleness is judged on mtime
    # plus a ctime that the test cannot backdate. Shift the clock instead.
    now = time.time() + 30 * DAY
    monkeypatch.setattr(autotier.time, "time", lambda: now)
    return now


def test_idle_detection_uses_newest_entry_and_git_window(tmp_path, clock):
    plain = _tree(tmp_path, "plain", days=5, now=clock)
    assert autotier.is_idle(plain)
    checkout = _tree(tmp_path, "checkout", days=5, now=clock, git=True)
    assert autotier.idle_days_for(checkout) == autotier.ROOT_GIT_IDLE_DAYS
    assert not autotier.is_idle(checkout)  # 5 < 7 days for a git checkout
    _age(checkout, 40, clock)
    assert autotier.is_idle(checkout)
    nested = plain / "deep" / "recent.txt"
    nested.parent.mkdir()
    nested.write_text("touched")
    _age(plain, 5, clock)
    os.utime(nested, (clock - DAY, clock - DAY))
    assert not autotier.is_idle(plain)


def test_discover_root_candidates_filters_and_orders(monkeypatch, tmp_path, clock):
    home = tmp_path / "home"
    old = _tree(home, "tmp/old", days=40, now=clock)
    _tree(home, "tmp/fresh", days=1, now=clock)
    (home / "tmp" / "already-tiered").symlink_to(old)
    _tree(home, "tmp/openjev", days=40, now=clock)  # explicit protect list
    busy = _tree(home, "tmp/busy", days=40, now=clock)
    checkout = _tree(home, "zer0/oss/repo", days=40, now=clock, git=True)
    downloads = home / "Downloads"
    downloads.mkdir()
    iso = downloads / "old.iso"
    iso.write_bytes(b"i" * 32)
    _age(iso, 40, clock)
    (downloads / "new.txt").write_text("today")
    _age(downloads / "new.txt", 0.5, clock)
    uv = _tree(home, ".local/share/uv", days=40, now=clock)
    sizes = {old: 5, checkout: 9, iso: 7, uv: 3, busy: 50}
    monkeypatch.setattr(autotier, "HOME", home)
    monkeypatch.setattr(autotier, "allocated_bytes", lambda path: sizes.get(path, 1) * GIB)
    in_use = {str(busy / "data.bin")}
    found = autotier.discover_root_candidates(used=in_use)
    assert [path for _size, path in found] == [checkout, iso, old, uv]


def test_paths_in_use_sees_open_fd_and_cwd(tmp_path):
    held = tmp_path / "held.txt"
    held.write_text("open")
    workdir = tmp_path / "workdir"
    workdir.mkdir()
    child = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(30)"], cwd=workdir)
    try:
        with held.open() as _fh:
            deadline = time.time() + 5
            while str(workdir) not in autotier.paths_in_use() and time.time() < deadline:
                time.sleep(0.05)
            in_use = autotier.paths_in_use()
            assert str(held) in in_use
            assert str(workdir) in in_use
            assert autotier.in_use(tmp_path, in_use)
            assert not autotier.in_use(tmp_path / "other", in_use)
    finally:
        os.kill(child.pid, 9)
        child.wait()


@pytest.fixture
def ledger(monkeypatch, tmp_path):
    path = tmp_path / "ledger.jsonl"
    monkeypatch.setattr(mover, "LEDGER", path)
    return path


def test_mover_verifies_count_and_bytes_before_removing_source(monkeypatch, tmp_path, ledger):
    home = tmp_path / "home"
    source = home / "tmp" / "work"
    source.mkdir(parents=True)
    (source / "a.txt").write_text("alpha")
    (source / "b.txt").write_text("beta")
    dest_root = tmp_path / "offload"

    def lossy_copy(src, dst):
        dst.mkdir(parents=True, exist_ok=True)
        (dst / "a.txt").write_text("alphabeta")  # same bytes, b.txt silently lost

    monkeypatch.setattr(mover, "rsync_copy", lossy_copy)
    monkeypatch.setattr(mover, "verify_checksum", lambda _src, _dst: None)
    with pytest.raises(RuntimeError, match="mismatch"):
        mover.migrate(source, dest_root, dry_run=False, source_root=home)
    assert source.is_dir() and not source.is_symlink()
    assert (source / "b.txt").read_text() == "beta"


def test_mover_keeps_source_if_process_starts_during_copy(monkeypatch, tmp_path, ledger):
    home = tmp_path / "home"
    source = home / "tmp" / "work"
    source.mkdir(parents=True)
    (source / "a.txt").write_text("alpha")
    calls = iter([[], ["new live process"]])
    monkeypatch.setattr(mover, "active_references", lambda _path: next(calls))
    monkeypatch.setattr(mover, "rsync_copy", lambda src, dst: shutil.copytree(src, dst))
    monkeypatch.setattr(mover, "verify_checksum", lambda _src, _dst: None)
    with pytest.raises(RuntimeError, match="appeared during migration"):
        mover.migrate(source, tmp_path / "offload", dry_run=False, source_root=home)
    assert source.is_dir() and not source.is_symlink()
    assert (source / "a.txt").read_text() == "alpha"


@pytest.mark.skipif(shutil.which("rsync") is None, reason="real mover integration requires rsync; exercised on MBP")
def test_mover_moves_dir_and_file_behind_symlinks(tmp_path, ledger):
    home = tmp_path / "home"
    work = home / "tmp" / "work"
    work.mkdir(parents=True)
    (work / "a.txt").write_text("alpha")
    iso = home / "Downloads" / "big.iso"
    iso.parent.mkdir()
    iso.write_bytes(b"i" * 4096)
    dest_root = tmp_path / "offload"
    mover.migrate(work, dest_root, dry_run=False, source_root=home)
    mover.migrate(iso, dest_root, dry_run=False, source_root=home)
    assert work.is_symlink() and work.resolve() == dest_root / "tmp" / "work"
    assert (work / "a.txt").read_text() == "alpha"
    assert iso.is_symlink() and iso.resolve() == dest_root / "Downloads" / "big.iso"
    assert iso.read_bytes() == b"i" * 4096
    assert not list(home.rglob("*.tier-backup-*"))


def test_mover_dry_run_changes_nothing(tmp_path, ledger):
    home = tmp_path / "home"
    work = home / "tmp" / "work"
    work.mkdir(parents=True)
    (work / "a.txt").write_text("alpha")
    dest_root = tmp_path / "offload"
    mover.migrate(work, dest_root, dry_run=True, source_root=home)
    assert work.is_dir() and not work.is_symlink()
    assert not dest_root.exists()
    assert "dry_run_ready" in ledger.read_text()


def _root_harness(monkeypatch, free_gib, candidates, moved_ok=True):
    calls = []
    state = {"free": free_gib * GIB}

    def cap(path="/workspace", reserve_gib=None):
        free = state["free"]
        ok = free >= autotier.ROOT_RESERVE_GIB * GIB
        return _critical(free_bytes=free, bytes_ok=ok, inodes_ok=True, free_inode_ratio=0.5)

    sizes = dict((path, size) for size, path in candidates)

    def run_mover(apply, selected, source_root=None, destination_root=None):
        calls.append((apply, list(selected), destination_root))
        if apply and moved_ok:
            state["free"] += sizes[Path(selected[0])]
        return 0 if moved_ok else 1

    notes = []
    monkeypatch.setattr(autotier, "capacity", cap)
    monkeypatch.setattr(autotier, "reclaim_root_junk", lambda _apply: 0)
    monkeypatch.setattr(autotier, "discover_root_candidates", lambda: candidates)
    monkeypatch.setattr(autotier, "_run_mover", run_mover)
    monkeypatch.setattr(autotier, "top_space_users", lambda: [(1, Path("/home/kvn/x"))])
    monkeypatch.setattr(autotier, "notify", lambda title, body: notes.append((title, body)))
    return calls, notes


def test_tier_root_stops_once_reserve_met(monkeypatch, tmp_path):
    monkeypatch.setattr(autotier, "ROOT_OFFLOAD", tmp_path / "offload")
    home = autotier.HOME
    candidates = [(10 * GIB, home / "tmp" / "a"), (4 * GIB, home / "tmp" / "b"), (3 * GIB, home / "tmp" / "c")]
    calls, notes = _root_harness(monkeypatch, 15, candidates)
    assert autotier.tier_root(apply=True) == 0
    assert [selected for _apply, selected, _dest in calls] == [[str(home / "tmp" / "a")]]
    assert not notes


def test_tier_root_dry_run_projects_without_applying(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(autotier, "ROOT_OFFLOAD", tmp_path / "offload")
    home = autotier.HOME
    candidates = [(3 * GIB, home / "tmp" / "a"), (2 * GIB, home / "tmp" / "b"), (1 * GIB, home / "tmp" / "c")]
    calls, notes = _root_harness(monkeypatch, 15, candidates)
    assert autotier.tier_root(apply=False) == 0
    assert [apply for apply, _selected, _dest in calls] == [False, False]
    assert "root would move" in capsys.readouterr().out
    assert not notes


def test_tier_root_skips_failed_move_and_existing_destination(monkeypatch, tmp_path):
    offload = tmp_path / "offload"
    monkeypatch.setattr(autotier, "ROOT_OFFLOAD", offload)
    home = autotier.HOME
    taken = home / "tmp" / "taken"
    candidates = [(30 * GIB, taken), (2 * GIB, home / "tmp" / "b")]
    calls, notes = _root_harness(monkeypatch, 15, candidates, moved_ok=False)
    (autotier.offload_destination() / "tmp" / "taken").mkdir(parents=True)
    assert autotier.tier_root(apply=True) == 75
    assert [selected for _apply, selected, _dest in calls] == [[str(home / "tmp" / "b")]]
    assert notes


def test_tier_root_short_notifies_top_space_users(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(autotier, "ROOT_OFFLOAD", tmp_path / "offload")
    calls, notes = _root_harness(monkeypatch, 15, [])
    assert autotier.tier_root(apply=True) == 75
    assert "CRITICAL" in capsys.readouterr().out
    assert len(notes) == 1 and "/home/kvn/x" in notes[0][1]


def test_top_space_users_lists_five_largest_second_level_dirs(monkeypatch, tmp_path):
    home = tmp_path / "home"
    for index in range(7):
        path = home / "top" / f"d{index}"
        path.mkdir(parents=True)
        (path / "blob").write_bytes(b"z" * (index + 1) * 65536)
    top = autotier.top_space_users(home)
    assert [path.name for _size, path in top] == ["d6", "d5", "d4", "d3", "d2"]


def test_tier_root_dry_run_short_reports_but_does_not_notify(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(autotier, "ROOT_OFFLOAD", tmp_path / "offload")
    calls, notes = _root_harness(monkeypatch, 15, [(1 * GIB, autotier.HOME / "tmp" / "a")])
    assert autotier.tier_root(apply=False) == 75
    assert "CRITICAL" in capsys.readouterr().out
    assert not notes


# --- regenerable-junk prune phase -----------------------------------------


def _git(root: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(root), *args], check=True, capture_output=True)


def _project(base: Path, name: str, now: float, source_days: float, manifest: str = "package.json") -> Path:
    root = base / name
    (root / "src").mkdir(parents=True)
    (root / manifest).write_text("{}\n")
    (root / "src" / "main.js").write_text("code\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    for junk in ("node_modules/pkg", "dist", "__pycache__"):
        (root / junk).mkdir(parents=True)
        (root / junk / "blob").write_bytes(b"j" * 128)
    _age(root, source_days, now)
    return root


@pytest.fixture
def prune_env(monkeypatch, tmp_path, clock):
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setattr(autotier, "HOME", home)
    monkeypatch.setattr(autotier, "PRUNE_PROJECT_ROOTS", (home,))
    monkeypatch.setattr(autotier, "referenced_text", lambda: "")
    monkeypatch.setattr(autotier, "allocated_bytes", lambda path: 4096)
    return home


def test_prune_targets_only_idle_unused_projects(prune_env, clock):
    home = prune_env
    idle = _project(home / "code", "idle", clock, source_days=10)
    active = _project(home / "code", "active", clock, source_days=10)
    os.utime(active / "src" / "main.js", (clock - DAY, clock - DAY))
    busy = _project(home / "code", "busy", clock, source_days=10)
    hidden = _project(home / ".local", "tool", clock, source_days=10)  # tool state, not a project
    loose = home / "loose" / "node_modules"  # no git checkout: cannot prove untracked
    loose.mkdir(parents=True)
    used = {str(busy / "src" / "main.js")}
    targets = autotier.find_prune_targets(used)
    assert sorted(targets) == sorted([idle / "node_modules", idle / "dist", idle / "__pycache__"])
    assert not any(str(t).startswith(str(hidden)) for t in targets)


def test_prune_keeps_tracked_build_and_unmanifested_dist(prune_env, clock):
    home = prune_env
    root = home / "proj"
    (root / "pkg" / "build").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\n")
    (root / "build").write_text("tracked build script\n")  # a FILE named build
    (root / "pkg" / "build" / "keep.txt").write_text("tracked\n")  # tracked dir named build
    (root / "pkg" / "pyproject.toml").write_text("[project]\n")
    _git(root, "init", "-q")
    _git(root, "add", "-A")
    (root / "dist").mkdir()
    (root / "dist" / "wheel.whl").write_bytes(b"w")
    (root / "docs" / "dist").mkdir(parents=True)  # no manifest beside it
    (root / "docs" / "dist" / "x").write_bytes(b"x")
    _age(root, 10, clock)
    targets = autotier.find_prune_targets(set())
    assert targets == [root / "dist"]


def test_prune_skips_paths_referenced_by_units(prune_env, clock, monkeypatch):
    home = prune_env
    root = _project(home, "svc", clock, source_days=10)
    monkeypatch.setattr(autotier, "referenced_text", lambda: f"ExecStart={root}/node_modules/.bin/serve\n")
    targets = autotier.find_prune_targets(set())
    assert root / "node_modules" not in targets
    assert root / "dist" in targets


def test_prune_versions_keeps_newest_two_and_running(prune_env, clock):
    versions = prune_env / "versions"
    versions.mkdir()
    paths = []
    for index, name in enumerate(["1.0.0", "1.1.0", "1.2.0", "1.3.0", "1.4.0"]):
        path = versions / name
        path.write_bytes(b"v")
        os.utime(path, (clock - (10 - index) * DAY,) * 2)
        paths.append(path)
    running = {str(paths[0])}
    freed = autotier.prune_versions(True, running, dirs=(versions,))
    assert sorted(p.name for p in versions.iterdir()) == ["1.0.0", "1.3.0", "1.4.0"]
    assert freed == 2 * 4096


def test_core_dump_needs_age_and_elf_core_magic(prune_env, clock):
    home = prune_env
    elf_core = b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + b"\x04\x00" + b"\x00" * 46
    elf_exec = b"\x7fELF\x02\x01\x01" + b"\x00" * 9 + b"\x02\x00" + b"\x00" * 46
    files = {
        "core.111": (elf_core, 2),  # old core: delete
        "core": (elf_core, 2),  # bare core: delete
        "core.222": (elf_core, 0.25),  # 15 minutes old: keep
        "core.333": (b"not an elf at all" * 4, 2),  # wrong magic: keep
        "core.444": (elf_exec, 2),  # ELF but not ET_CORE: keep
    }
    for name, (data, hours) in files.items():
        (home / name).write_bytes(data)
        os.utime(home / name, (clock - hours * 3600,) * 2)
    autotier.prune_core_dumps(True)
    assert sorted(p.name for p in home.iterdir()) == ["core.222", "core.333", "core.444"]


def test_prune_dry_run_deletes_nothing_and_logs_sizes(prune_env, clock, capsys, monkeypatch):
    home = prune_env
    idle = _project(home, "idle", clock, source_days=10)
    monkeypatch.setattr(autotier, "paths_in_use_deep", lambda: set())
    monkeypatch.setattr(autotier, "prune_tool_caches", lambda apply: 0)
    monkeypatch.setattr(autotier, "prune_flatpak", lambda apply: 0)
    versions = home / "versions"
    versions.mkdir()
    for name in ("a", "b", "c"):
        (versions / name).write_bytes(b"v")
    monkeypatch.setattr(autotier, "VERSION_DIRS", (versions,))
    autotier.prune_regenerable(apply=False)
    assert (idle / "node_modules" / "pkg" / "blob").is_file()
    assert len(list(versions.iterdir())) == 3
    out = capsys.readouterr().out
    assert f"prune would delete project-cache {idle / 'node_modules'} bytes=4096" in out
    assert "prune would delete cli-version" in out


def test_tool_cache_resolving_to_forbidden_tier_is_skipped(prune_env, tmp_path, monkeypatch, capsys):
    cold = tmp_path / "cold" / "cache"
    cold.mkdir(parents=True)
    (cold / "blob").write_bytes(b"c")
    link = prune_env / ".npm" / "_cacache"
    link.parent.mkdir()
    link.symlink_to(cold)
    monkeypatch.setattr(autotier, "PRUNE_FORBIDDEN", (tmp_path / "cold",))
    assert autotier.remove_path(link, "tool-cache", True) == 0
    assert (cold / "blob").is_file()
    assert "forbidden" in capsys.readouterr().out


def test_remove_path_handles_read_only_cargo_tree(prune_env):
    src = prune_env / ".cargo" / "registry" / "src" / "crate"
    src.mkdir(parents=True)
    (src / "lib.rs").write_text("fn main() {}")
    os.chmod(src, 0o555)
    assert autotier.remove_path(src.parent, "tool-cache", True) == 4096
    assert not src.parent.exists()


def test_prune_due_when_low_or_not_yet_today(prune_env, monkeypatch):
    stamp = prune_env / "stamp"
    monkeypatch.setattr(autotier, "PRUNE_STAMP", stamp)
    assert autotier.prune_due(root_low=False)
    autotier.mark_pruned()
    assert not autotier.prune_due(root_low=False)
    assert autotier.prune_due(root_low=True)


def test_main_dry_run_flag_never_applies(monkeypatch):
    seen = []
    monkeypatch.setattr(autotier, "tier_workspace", lambda apply: seen.append(("ws", apply)) or 0)
    monkeypatch.setattr(autotier, "tier_root", lambda apply: seen.append(("root", apply)) or 0)
    monkeypatch.setattr(autotier, "maybe_prune", lambda apply: seen.append(("prune", apply)))
    monkeypatch.setattr(autotier.sys, "argv", [str(SCRIPT), "--dry-run"])
    assert autotier.main() == 0
    assert seen == [("ws", False), ("prune", False), ("root", False)]
