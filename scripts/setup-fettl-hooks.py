#!/usr/bin/env python3
"""Install native Fettl hook entries plus the installed Hermes shell-hook bridge.

Does not restart any process, change harness core code, log in, or run repairs.
Requires Linux bubblewrap, Python 3/PyYAML, git, and the pinned Fettl installer.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shlex
import shutil
import subprocess
import tempfile
import tomllib

import yaml

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "config/fettl"
POLICY = json.loads((SOURCE / "hooks.json").read_text())
HOME = Path.home()
CONFIG = HOME / ".config/fettl"
CACHE = Path(os.environ.get("XDG_CACHE_HOME", HOME / ".cache")) / "fettl-hooks"
STAMP = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")


def call(args: list[str], **kwargs) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, timeout=30, **kwargs)
    if result.returncode:
        raise RuntimeError(f"{shlex.join(args)} failed ({result.returncode}): {result.stderr.strip()}")
    return result


def save(path: Path, data: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        original = path.read_bytes()
        if original == data.encode():
            return
        relative = path.relative_to(HOME) if path.is_relative_to(HOME) else Path("external") / str(path).lstrip("/")
        backup = CONFIG / "backups" / STAMP / relative
        backup.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        backup.write_bytes(original)
        backup.chmod(0o600)
    temporary = path.with_name(path.name + ".fettl-new")
    temporary.write_text(data)
    temporary.chmod(path.stat().st_mode & 0o777 if path.exists() else 0o600)
    temporary.replace(path)


def link(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_symlink() and destination.resolve() == source.resolve():
        return
    if destination.exists() or destination.is_symlink():
        raise RuntimeError(f"Refusing to replace unrelated existing file: {destination}")
    destination.symlink_to(source)


def owned(entry: dict) -> bool:
    if entry.get("fettl-managed") == "dotfiles-fettl-hooks-v1":
        return True
    return "fettl-managed:" in entry.get("command", "") and "fettl-hook-installer" in entry["command"]


def install_hermes(home: Path, runtime: Path, native_entry: dict) -> str:
    hermes_path = home / "config.yaml"
    original_yaml = hermes_path.read_text() if hermes_path.exists() else ""
    hermes = yaml.safe_load(original_yaml) or {}
    hermes_hooks = hermes.get("hooks", {})
    if not isinstance(hermes_hooks, dict):
        raise RuntimeError(f"Existing Hermes hooks must be a mapping: {hermes_path}")
    entries = hermes_hooks.setdefault(POLICY["hermes_event"], [])
    entries[:] = [entry for entry in entries if not owned(entry)]
    command = shlex.join(["/usr/bin/python3", str(runtime), "hermes"])
    entries.append({"command": command, "matcher": POLICY["hermes_matcher"],
                    "timeout": POLICY["wall_seconds"] + 5,
                    "fettl-managed": "dotfiles-fettl-hooks-v1",
                    "fettl_native_command": native_entry["command"]})
    replacement = yaml.safe_dump({"hooks": hermes_hooks}, sort_keys=False)
    document = yaml.compose(original_yaml)
    block = next(((key, value) for key, value in document.value if key.value == "hooks"), None) if document else None
    if block:
        key, value = block
        new_yaml = original_yaml[:key.start_mark.index] + replacement + original_yaml[value.end_mark.index:]
    else:
        new_yaml = original_yaml.rstrip() + "\n" + replacement
    save(hermes_path, new_yaml)
    # Exact per-command consent only, never hooks_auto_accept for other commands.
    allowlist_path = home / "shell-hooks-allowlist.json"
    allowlist = json.loads(allowlist_path.read_text()) if allowlist_path.exists() else {"approvals": []}
    approvals = allowlist.setdefault("approvals", [])
    approval = next((item for item in approvals
                     if item.get("event") == POLICY["hermes_event"] and item.get("command") == command), None)
    script_mtime = datetime.fromtimestamp(runtime.stat().st_mtime, timezone.utc).isoformat().replace("+00:00", "Z")
    if approval is None:
        approval = {"event": POLICY["hermes_event"], "command": command}
        approvals.append(approval)
    if approval.get("script_mtime_at_approval") != script_mtime:
        approval.update({"approved_at": datetime.now(timezone.utc).isoformat(),
                         "script_mtime_at_approval": script_mtime})
        save(allowlist_path, json.dumps(allowlist, indent=2) + "\n")
    return command


def install(report_path: Path | None, explicit_homes: list[Path]) -> None:
    os.umask(0o077)
    binary = HOME / ".local/bin/fettl"
    pinned = tomllib.loads((ROOT / "fleet.toml").read_text())["hosts"]["desktop"]["fettl"]
    digest = hashlib.sha256(binary.read_bytes()).hexdigest()
    expected = pinned.get("binary_sha256") or pinned.get("sha256_binary")
    if expected and digest != expected:
        raise RuntimeError("Fettl binary does not match the fleet pin")
    version = call([str(binary), "--version"]).stdout.strip()
    if version != f"fettl {pinned['version']}":
        raise RuntimeError("Fettl version does not match fleet.toml")
    dependencies = {name: shutil.which(name) for name in ("bwrap", "git", "ionice")}
    if not all(dependencies.values()):
        raise RuntimeError("bwrap, git, and ionice must be installed; refusing an unsandboxed hook")
    call([dependencies["bwrap"], "--die-with-parent", "--unshare-net", "--ro-bind", "/", "/", "/usr/bin/true"])
    CONFIG.mkdir(parents=True, exist_ok=True, mode=0o700)
    for name in ("runtime", "run", "tmp", "repositories"):
        (CACHE / name).mkdir(parents=True, exist_ok=True, mode=0o700)
    # The canonical supervisor journal is external to every source worktree.
    env = {**os.environ, "XDG_CACHE_HOME": str(CACHE / "runtime"), "XDG_RUNTIME_DIR": str(CACHE / "run")}
    journal = CACHE / "runtime/fettl/journal/candidate"
    call([str(binary), "local-store", "init", "--root", str(journal)], env=env)
    native = {}
    # Let this exact binary author its ownership/executable identity and entries.
    # Stage away from real configs: its Hermes list schema is not the installed
    # Hermes mapping schema, so a direct global install would break existing hooks.
    with tempfile.TemporaryDirectory(prefix="fettl-hooks-install-") as stage:
        staged = Path(stage)
        staged_env = {**env, "HOME": stage, "HERMES_HOME": str(staged / ".hermes")}
        for agent in ("claude", "hermes"):
            call([str(binary), "hook", "install", "--agent", agent, "--global"], env=staged_env, cwd=stage)
        native["claude"] = json.loads((staged / ".claude/settings.json").read_text())
        native["hermes"] = yaml.safe_load((staged / ".hermes/config.yaml").read_text())
    runtime = CONFIG / "hook.py"
    for name in ("hook.py", "hooks.json", "mode.json"):
        link(SOURCE / name, CONFIG / name)
    state = {"schema_version": 1, "executable": str(binary.resolve()), "sha256": digest,
             "version": version, **dependencies, "native": native}
    save(CONFIG / "hooks-state.json", json.dumps(state, indent=2) + "\n")
    claude_path = HOME / ".claude/settings.json"
    claude = json.loads(claude_path.read_text()) if claude_path.exists() else {}
    hooks = claude.setdefault("hooks", {})
    for event in POLICY["claude_events"]:
        groups = hooks.setdefault(event, [])
        for group in groups:
            group["hooks"] = [item for item in group.get("hooks", []) if not owned(item)]
        groups[:] = [group for group in groups if group.get("hooks")]
        for group in native["claude"]["hooks"][event]:
            for item in group["hooks"]:
                prefix, marker = item["command"].split(" # fettl-managed:", 1)
                action = shlex.split(prefix)[-1]
                item["command"] = shlex.join(["/usr/bin/python3", str(runtime), "claude", action]) + " # fettl-managed:" + marker
                item["timeout"] = POLICY["wall_seconds"] + 5
            groups.append(group)
    save(claude_path, json.dumps(claude, indent=2) + "\n")
    native_hermes = native["hermes"]["hooks"]
    if len(native_hermes) != 1 or native_hermes[0]["event"] != POLICY["hermes_event"]:
        raise RuntimeError("Unsupported native Hermes installer output")
    targets = json.loads((SOURCE / "targets.json").read_text())["hermes_homes"]
    homes = explicit_homes or [Path(target).expanduser() for target in targets]
    command = shlex.join(["/usr/bin/python3", str(runtime), "hermes"])
    installed_homes = []
    for home in homes:
        home = home.expanduser()
        if not home.is_dir():
            continue
        command = install_hermes(home, runtime, native_hermes[0])
        installed_homes.append(str(home))
    omp_path = HOME / ".omp/agent/extensions/fettl/index.ts"
    link(SOURCE / "omp.ts", omp_path)
    status = call([str(binary), "hook", "status", "--agent", "claude", "--global", "--format", "json"])
    report = {"schema_version": 1, "installed_at": STAMP, "version": version,
              "claude_native_status": json.loads(status.stdout),
              "claude_events": POLICY["claude_events"], "hermes_command": command,
              "hermes_homes": installed_homes,
              "hermes_schema_adapter": "native installer list converted to installed shell-hook mapping; canonical payload bridge",
              "hermes_reload": "config and consent hot-sync; no gateway restart performed",
              "omp_extension": str(omp_path), "omp_activation": "new session/restart required for a newly discovered module",
              "network": "bubblewrap private network namespace", "source": "read-only bind mounts",
              "daemon": "private PID namespace dies with the hook; no daemon can outlive it",
              "limits": POLICY, "backup_directory": str(CONFIG / "backups" / STAMP)}
    save(CONFIG / "install-report.json", json.dumps(report, indent=2) + "\n")
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--hermes-home", type=Path, action="append", default=[],
                        help="Explicit existing Hermes home (repeatable); defaults to config/fettl/targets.json")
    args = parser.parse_args()
    install(args.report, args.hermes_home)
