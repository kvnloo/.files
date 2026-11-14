#!/usr/bin/env python3
"""Keep Claude Code's plugin marketplaces present, and loud when they are not.

A config dir can list ``z0intelligence@z0intelligence`` in ``settings.json``
``enabledPlugins`` while its marketplace checkout is gone. Claude Code then
answers ``claude plugin list`` with ``Marketplace z0intelligence failed to load:
cache-miss``, registers no hooks, and every ``claude -p`` turn runs with capture
silently off. Nothing else complains: the tick that consumes the captured rows
just reports zeros, which is how a 21-hour gap went unnoticed.

Two subcommands, wired on one timer so a break is detected, healed, and then
reported as a unit failure if the heal did not take:

  check   Exit non-zero when a plugin this config dir installed and enabled is
          not loaded, or when a marketplace backing it has no readable catalog.
  ensure  Re-create a missing or unreadable marketplace checkout from a tracked
          source: another config dir on this host, then the repo it was
          registered from. Never touches a healthy checkout.

``claude`` is only needed by ``check``; ``ensure`` is pure filesystem plus the
registered git source, so it also works as a pre-start gate for the tick that
reads the captured rows.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

CATALOG = Path(".claude-plugin") / "marketplace.json"
DEFAULT_CONFIG_DIRS = ("~/.claude", "~/.claude-sub2", "~/.claude-ultra", "~/.claude-work")
CLEAN, BROKEN, UNUSABLE = 0, 1, 2
CLONE_TIMEOUT_S = 300


def log(message: str) -> None:
    print(message, flush=True)


def read_json(path: Path) -> dict:
    """Best-effort JSON object; a missing or unreadable file reads as empty."""
    try:
        value = json.loads(path.read_text())
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def expand(text: str) -> Path:
    return Path(os.path.expanduser(text))


class ConfigDir:
    """One Claude Code config dir: its settings, registry and plugin state."""

    def __init__(self, path: Path):
        self.path = path
        self.settings = read_json(path / "settings.json")
        self.registry = self._registry()

    def _registry(self) -> dict:
        # installed_plugins.json v2 nests the plugin records under "plugins".
        state = read_json(self.path / "plugins" / "installed_plugins.json")
        plugins = state.get("plugins")
        return plugins if isinstance(plugins, dict) else {}

    @property
    def present(self) -> bool:
        return (self.path / "settings.json").exists()

    def enabled(self) -> dict[str, bool]:
        flags = self.settings.get("enabledPlugins")
        return flags if isinstance(flags, dict) else {}

    def installed(self) -> set[str]:
        return {name for name, rows in self.registry.items() if rows}

    def marketplaces(self) -> dict[str, dict]:
        """Registered marketplaces by name, newest registration winning.

        ``plugins/known_marketplaces.json`` is written by Claude Code and carries
        the ``installLocation``; ``settings.json extraKnownMarketplaces`` only
        declares the source, and exists so a rebuilt host can re-register.
        """
        found: dict[str, dict] = {}
        for holder in (self.settings.get("extraKnownMarketplaces"),
                       read_json(self.path / "plugins" / "known_marketplaces.json")):
            if not isinstance(holder, dict):
                continue
            for name, source in holder.items():
                if isinstance(source, dict):
                    found[name] = source
        return found

    def needed_marketplaces(self) -> set[str]:
        """Marketplaces that back a plugin this dir both installed and enabled.

        A plugin enabled in settings but never installed here is an orphaned
        entry, not a broken hook, and is deliberately ignored.
        """
        enabled = {name for name, on in self.enabled().items() if on}
        return {name.rsplit("@", 1)[1] for name in sorted(enabled & self.installed())}

    def marketplaces_source(self, name: str) -> dict:
        """Registration record for one marketplace, by name."""
        return self.marketplaces().get(name, {})

    def marketplace_root(self, name: str) -> Path:
        """Where Claude Code keeps this marketplace's checkout on disk."""
        source = self.marketplaces_source(name)
        for key in ("installLocation", "path"):
            value = source.get(key)
            if isinstance(value, str) and value:
                return expand(value)
        return self.path / "plugins" / "marketplaces" / name


def catalog_ok(root: Path) -> tuple[bool, str]:
    """A marketplace is usable when its catalog manifest parses."""
    manifest = root / CATALOG
    try:
        payload = json.loads(manifest.read_text())
    except FileNotFoundError:
        return False, "no checkout"
    except (OSError, ValueError) as exc:
        return False, f"unreadable catalog: {exc}"
    if not isinstance(payload, dict):
        return False, "unreadable catalog: not an object"
    return True, ""


def plugin_list(config: ConfigDir, claude: str) -> list[dict] | None:
    """``claude plugin list --json`` for this config dir, or None if unavailable."""
    env = dict(os.environ, CLAUDE_CONFIG_DIR=str(config.path))
    try:
        done = subprocess.run(
            [claude, "plugin", "list", "--json"],
            capture_output=True, text=True, env=env, timeout=180, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"{config.path}: cannot run {claude} plugin list: {exc}")
        return None
    if done.returncode != 0:
        log(f"{config.path}: claude plugin list exited {done.returncode}: "
            f"{(done.stderr or done.stdout).strip()[:200]}")
        return None
    try:
        rows = json.loads(done.stdout)
    except ValueError:
        log(f"{config.path}: claude plugin list --json was not JSON")
        return None
    return rows if isinstance(rows, list) else []


def faults(config: ConfigDir, rows: list[dict] | None) -> tuple[list[str], bool]:
    """(problems, claude_usable): every reason a hook this dir wants would not
    be registered, plus whether ``claude`` ran at all. The marketplace catalog
    is an independent invariant, so it is checked even when ``claude`` is down.
    """
    problems: list[str] = []
    usable = rows is not None

    if usable:
        listed: dict[str, list[dict]] = {}
        for row in rows:
            if isinstance(row, dict) and isinstance(row.get("id"), str):
                listed.setdefault(row["id"], []).append(row)

        for plugin in sorted(set(config.enabled()) & config.installed()):
            entries = listed.get(plugin, [])
            if not entries:
                problems.append(f"{plugin}: installed and enabled but not listed")
                continue
            if not any(entry.get("enabled") for entry in entries):
                problems.append(f"{plugin}: listed but not enabled")
            for entry in entries:
                for error in entry.get("errors") or []:
                    if isinstance(error, str) and error:
                        problems.append(f"{plugin}: {error}")

    # Filesystem invariant, independent of how a Claude Code release renders
    # plugin errors: a marketplace backing a live plugin must have its catalog.
    for name in sorted(config.needed_marketplaces()):
        ok, why = catalog_ok(config.marketplace_root(name))
        if not ok:
            problems.append(f"marketplace {name}: {why} "
                            f"({config.marketplace_root(name)})")
    return problems, usable


def clone_url(source: dict) -> str | None:
    """The git URL Claude Code would use to (re)register this marketplace."""
    kind = source.get("source")
    if kind == "github":
        repo = source.get("repo")
        return f"https://github.com/{repo}.git" if repo else None
    url = source.get("url")
    return url if isinstance(url, str) and url else None


def local_source(source: dict) -> Path | None:
    if source.get("source") in ("local", "path", None):
        for key in ("path", "url", "installLocation"):
            value = source.get(key)
            if isinstance(value, str) and value and not value.startswith(("http:", "https:", "git@")):
                return expand(value)
    return None


def stage_copy(seeds: list[Path], staging: Path) -> Path | None:
    """Copy the first seed that carries a readable catalog into staging."""
    for seed in seeds:
        if seed is None:
            continue
        ok, _ = catalog_ok(seed)
        if not ok:
            continue
        try:
            shutil.copytree(seed, staging, symlinks=True)
        except (OSError, shutil.Error) as exc:
            log(f"  copy from {seed} failed: {exc}")
            shutil.rmtree(staging, ignore_errors=True)
            continue
        log(f"  staged from {seed}")
        return staging
    return None


def stage_clone(url: str, staging: Path) -> Path | None:
    """Shallow-clone the registered repo into staging; no credentials needed."""
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    try:
        done = subprocess.run(
            ["git", "clone", "--depth", "1", url, str(staging)],
            capture_output=True, text=True, env=env,
            timeout=CLONE_TIMEOUT_S, check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"  clone from {url} failed: {exc}")
        return None
    if done.returncode != 0 or not staging.is_dir():
        log(f"  clone from {url} exited {done.returncode}: "
            f"{(done.stderr or done.stdout).strip()[:200]}")
        return None
    log(f"  cloned {url}")
    return staging


def retire_broken(root: Path) -> Path | None:
    """Move an unusable checkout aside; never delete host state."""
    spare = root.with_name(f"{root.name}.broken-{time.strftime('%Y%m%dT%H%M%S')}")
    try:
        os.replace(root, spare)
    except OSError as exc:
        log(f"  could not set aside {root}: {exc}")
        return None
    log(f"  set aside {spare}")
    return spare


def heal(config: ConfigDir, name: str, source: dict, seeds: list[Path], quiet: bool) -> bool:
    root = config.marketplace_root(name)
    ok, why = catalog_ok(root)
    if ok:
        return True

    staging = root.parent / f".staged-{name}-{os.getpid()}"
    shutil.rmtree(staging, ignore_errors=True)
    local = local_source(source)
    url = clone_url(source)
    staged = (stage_copy(([local] if local else []) + seeds, staging)
              or (stage_clone(url, staging) if url else None))
    if staged is None:
        shutil.rmtree(staging, ignore_errors=True)
        log(f"{config.path}: marketplace {name} still {why}; no source available")
        return False

    healthy, why = catalog_ok(staging)
    if not healthy:
        log(f"{config.path}: staged marketplace {name} is unusable ({why})")
        shutil.rmtree(staging, ignore_errors=True)
        return False

    root.parent.mkdir(parents=True, exist_ok=True)
    if root.exists():
        retire_broken(root)
    os.replace(staged, root)
    if not quiet:
        log(f"{config.path}: marketplace {name} re-created at {root}")
    return True


def ensure(configs: list[ConfigDir], quiet: bool) -> int:
    healed, failed = 0, []
    for config in configs:
        if not config.present:
            continue
        for name in sorted(config.needed_marketplaces()):
            seeds = [
                other.marketplace_root(name)
                for other in configs
                if other.path != config.path and name in other.needed_marketplaces()
            ]
            source = config.marketplaces_source(name)
            if heal(config, name, source, seeds, quiet):
                healed += 1
            else:
                failed.append(f"{config.path}: {name}")
    if failed:
        for line in failed:
            log(f"UNHEALED {line}")
        return BROKEN
    if not quiet:
        log(f"ensure: {healed} marketplace checkout(s) healthy")
    return CLEAN


def check(configs: list[ConfigDir], claude: str, as_json: bool) -> int:
    report, problems, unusable = [], [], False
    for config in configs:
        if not config.present:
            continue
        found, usable = faults(config, plugin_list(config, claude))
        if not usable and not found:
            unusable = True
        report.append({"config_dir": str(config.path),
                       "claude_available": usable, "faults": found})
        problems.extend(f"{config.path}: {line}" for line in found)
    if as_json:
        log(json.dumps({"ok": not problems and not unusable, "faults": report},
                       indent=2))
    elif problems:
        log("BROKEN Claude plugin marketplaces:")
        for line in problems:
            log(f"  {line}")
    elif unusable:
        log("UNUSABLE: claude plugin list could not run in one or more config dirs")
    else:
        log("ok: every installed, enabled Claude plugin is loaded")
    if problems:
        return BROKEN
    if unusable:
        return UNUSABLE
    return CLEAN


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ensure and verify Claude Code plugin marketplaces")
    parser.add_argument("command", choices=("ensure", "check"))
    parser.add_argument("--config-dir", action="append", default=[],
                        help="Claude config dir to cover (repeatable; default "
                             f"{', '.join(DEFAULT_CONFIG_DIRS)})")
    parser.add_argument("--claude", default=os.environ.get("CLAUDE_BIN", "claude"),
                        help="claude CLI used by check (default: claude)")
    parser.add_argument("--json", action="store_true", help="machine-readable check output")
    parser.add_argument("--quiet", action="store_true", help="only report problems and heals")
    args = parser.parse_args(argv)

    dirs = args.config_dir or list(DEFAULT_CONFIG_DIRS)
    if os.environ.get("CLAUDE_CONFIG_DIRS"):
        dirs = [d for d in os.environ["CLAUDE_CONFIG_DIRS"].split(":") if d]
    configs = [ConfigDir(expand(d)) for d in dirs]

    try:
        if args.command == "ensure":
            return ensure(configs, args.quiet)
        return check(configs, args.claude, args.json)
    except Exception as exc:  # a broken check must never look like success
        log(f"UNUSABLE {type(exc).__name__}: {exc}")
        return UNUSABLE


if __name__ == "__main__":
    sys.exit(main())
