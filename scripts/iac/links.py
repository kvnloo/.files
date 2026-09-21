#!/usr/bin/env python3
"""Symlink-safe rollout planning for .files path migrations.

The scan phase is read-only. It finds symlinks whose resolved targets live
inside an active .files checkout, maps them to a candidate worktree, and writes
a frozen plan plus stage/cutover/rollback scripts.

Generated scripts are dry-run unless passed --apply.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shlex
import stat
import sys
from typing import Any

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - current CachyOS Python has tomllib
    tomllib = None  # type: ignore[assignment]


def _under(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _resolved_link(path: Path) -> tuple[str, Path]:
    raw = os.readlink(path)
    target = Path(raw)
    if not target.is_absolute():
        target = path.parent / target
    return raw, target.resolve(strict=False)


def _iter_symlinks(root: Path, *, excludes: list[Path], errors: list[str]):
    if root.is_symlink():
        yield root
        return
    try:
        root_dev = root.stat().st_dev
    except OSError as exc:
        errors.append(f"{root}: {exc}")
        return

    def onerror(exc: OSError) -> None:
        errors.append(f"{getattr(exc, 'filename', root)}: {exc}")

    for base, dirs, files in os.walk(root, topdown=True, followlinks=False, onerror=onerror):
        base_path = Path(base)

        kept_dirs: list[str] = []
        for name in dirs:
            path = base_path / name
            if any(_under(path.resolve(strict=False), ex) for ex in excludes):
                continue
            try:
                mode = path.lstat().st_mode
            except OSError as exc:
                errors.append(f"{path}: {exc}")
                continue
            if stat.S_ISLNK(mode):
                yield path
                continue
            try:
                if path.stat().st_dev != root_dev:
                    continue
            except OSError:
                continue
            kept_dirs.append(name)
        dirs[:] = kept_dirs

        for name in files:
            path = base_path / name
            if any(_under(path.resolve(strict=False), ex) for ex in excludes):
                continue
            try:
                if path.is_symlink():
                    yield path
            except OSError as exc:
                errors.append(f"{path}: {exc}")


def _load_moves(path: Path | None) -> list[dict[str, str]]:
    if path is None:
        return []
    if tomllib is None:
        raise SystemExit("Python 3.11+ is required when --map is used")
    data = tomllib.loads(path.read_text())
    rows = data.get("move", [])
    if not isinstance(rows, list):
        raise SystemExit("path map must use [[move]] entries")
    out: list[dict[str, str]] = []
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get("from"), str) or not isinstance(row.get("to"), str):
            raise SystemExit("every [[move]] needs string 'from' and 'to'")
        src = Path(row["from"]).as_posix().strip("/")
        dst = Path(row["to"]).as_posix().strip("/")
        if not src or src.startswith("../") or dst.startswith("../"):
            raise SystemExit(f"unsafe move mapping: {row!r}")
        out.append({"from": src, "to": dst})
    out.sort(key=lambda row: len(row["from"]), reverse=True)
    return out


def _map_relative(rel: str, moves: list[dict[str, str]]) -> str:
    rel_path = Path(rel).as_posix().lstrip("./")
    for row in moves:
        src = row["from"]
        if rel_path == src:
            return row["to"]
        prefix = src + "/"
        if rel_path.startswith(prefix):
            tail = rel_path[len(prefix):]
            return str(Path(row["to"]) / tail)
    return rel_path


def build_plan(
    old_root: Path,
    new_root: Path,
    scan_roots: list[Path],
    *,
    moves: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    old_root = old_root.resolve(strict=True)
    new_root = new_root.resolve(strict=True)
    moves = moves or []
    errors: list[str] = []
    records: list[dict[str, str]] = []
    seen: set[str] = set()
    excludes = [old_root, new_root]

    for root in scan_roots:
        root = root.expanduser()
        if not root.exists() and not root.is_symlink():
            errors.append(f"{root}: does not exist")
            continue
        for link in _iter_symlinks(root, excludes=excludes, errors=errors):
            key = str(link)
            if key in seen:
                continue
            seen.add(key)
            try:
                raw, resolved = _resolved_link(link)
            except OSError as exc:
                errors.append(f"{link}: {exc}")
                continue
            if not _under(resolved, old_root):
                continue
            rel = resolved.relative_to(old_root).as_posix()
            mapped = _map_relative(rel, moves)
            stage_target = new_root / mapped
            final_target = old_root / mapped
            records.append({
                "link": str(link),
                "raw_target": raw,
                "old_resolved": str(resolved),
                "old_relative": rel,
                "new_relative": mapped,
                "stage_target": str(stage_target),
                "final_target": str(final_target),
                "stage_target_exists": str(stage_target.exists()).lower(),
                "final_target_exists_now": str(final_target.exists()).lower(),
            })

    records.sort(key=lambda row: row["link"])
    return {
        "schema_version": 1,
        "old_root": str(old_root),
        "new_root": str(new_root),
        "scan_roots": [str(path.expanduser()) for path in scan_roots],
        "moves": moves,
        "links": records,
        "scan_errors": errors,
    }


_RUNNER = r'''#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import sys

PLAN = json.loads(__PLAN_JSON__)
MODE = __MODE_JSON__


def replace_link(link: Path, target: str) -> None:
    tmp = link.with_name(link.name + f".iac-tmp-{os.getpid()}")
    try:
        tmp.unlink(missing_ok=True)
        os.symlink(target, tmp)
        os.replace(tmp, link)
    finally:
        try:
            tmp.unlink()
        except FileNotFoundError:
            pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true", help="perform the relinks; default is dry-run")
    args = parser.parse_args()

    failures = []
    changed = 0
    for row in PLAN["links"]:
        link = Path(row["link"])
        if MODE == "stage":
            target = row["stage_target"]
            allowed = {row["raw_target"]}
        elif MODE == "cutover":
            target = row["final_target"]
            allowed = {row["raw_target"], row["stage_target"]}
        else:
            target = row["raw_target"]
            allowed = {row["stage_target"], row["final_target"], row["raw_target"]}

        if not link.is_symlink():
            failures.append(f"{link}: no longer a symlink")
            continue
        current = os.readlink(link)
        if current not in allowed:
            failures.append(f"{link}: changed since scan ({current!r})")
            continue

        if MODE != "rollback" and not Path(target).exists():
            failures.append(f"{link}: target does not exist: {target}")
            continue

        print(f"{MODE}: {link} -> {target}")
        if args.apply and current != target:
            try:
                replace_link(link, target)
                changed += 1
            except PermissionError:
                failures.append(f"{link}: permission denied; rerun this frozen script with appropriate privileges")
            except OSError as exc:
                failures.append(f"{link}: {exc}")

    if failures:
        print("\nFAILURES:", file=sys.stderr)
        for item in failures:
            print("  " + item, file=sys.stderr)
        return 1
    print(f"\n{'changed' if args.apply else 'would change'}: {changed if args.apply else len(PLAN['links'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
'''


def _write_runner(path: Path, plan: dict[str, Any], mode: str) -> None:
    source = _RUNNER.replace("__PLAN_JSON__", repr(json.dumps(plan, separators=(",", ":"))))
    source = source.replace("__MODE_JSON__", repr(mode))
    path.write_text(source)
    path.chmod(0o700)


def write_bundle(plan: dict[str, Any], out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    plan_path = out_dir / "plan.json"
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n")
    for mode in ("stage", "cutover", "rollback"):
        _write_runner(out_dir / f"{mode}.py", plan, mode)


def default_roots() -> list[Path]:
    roots = [Path.home()]
    for path in (Path("/etc"), Path("/usr/local/bin")):
        if path.exists():
            roots.append(path)
    return roots


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="iac links")
    sub = parser.add_subparsers(dest="command", required=True)
    scan = sub.add_parser("scan", help="scan .files-owned symlinks and generate rollout scripts")
    scan.add_argument("--old-root", type=Path, required=True, help="active/canonical .files checkout")
    scan.add_argument("--new-root", type=Path, required=True, help="candidate worktree")
    scan.add_argument("--map", type=Path, help="optional TOML [[move]] path map")
    scan.add_argument("--root", dest="roots", type=Path, action="append", help="scan root; repeatable")
    scan.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    if args.command == "scan":
        roots = args.roots or default_roots()
        plan = build_plan(args.old_root, args.new_root, roots, moves=_load_moves(args.map))
        write_bundle(plan, args.output_dir)
        print(args.output_dir / "plan.json")
        print(f"links: {len(plan['links'])}; scan_errors: {len(plan['scan_errors'])}")
        return 0
    raise AssertionError(args.command)


if __name__ == "__main__":
    raise SystemExit(main())
