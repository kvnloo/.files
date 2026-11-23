"""Private network overlay: the owner's tailnet identity, read at run time, never committed.

This public repo names no real tailnet address or MagicDNS name. Those values live in
one untracked directory:

  $DOTFILES_PRIVATE_DIR            (default: ~/.config/dotfiles)
    private.env                    KEY=VALUE pairs for env files, units, shell and scripts
    hosts.private.yaml             structured per-node data merged into config/fleet/nodes.yaml;
                                   its strings may reference private.env as ${KEY}

Every key is documented in config/private.example.env and config/hosts.private.example.yaml.
A missing required key raises PrivateOverlayError with a message naming the key and the
file; nothing falls back to a hard-coded host.

Stdlib only, except load_hosts(), which imports PyYAML when hosts.private.yaml exists.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

ENV_FILE = "private.env"
HOSTS_FILE = "hosts.private.yaml"
EXAMPLE_ENV = "config/private.example.env"
EXAMPLE_HOSTS = "config/hosts.private.example.yaml"
_VAR = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")


class PrivateOverlayError(RuntimeError):
    """A required private value is missing or unreadable."""


def private_dir() -> Path:
    return Path(os.environ.get("DOTFILES_PRIVATE_DIR") or "~/.config/dotfiles").expanduser()


def parse_env(text: str, source: str = ENV_FILE) -> dict:
    """KEY=VALUE lines; `export ` prefixes, blank lines, # comments and matching quotes allowed."""
    out = {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].lstrip()
        key, sep, value = line.partition("=")
        key = key.strip()
        if not sep or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise PrivateOverlayError(f"{source}:{number}: expected KEY=VALUE")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key] = value
    return out


def load_env(directory: Path | None = None) -> dict:
    """The private KEY=VALUE map; {} when the file does not exist."""
    path = (directory or private_dir()) / ENV_FILE
    try:
        return parse_env(path.read_text(), str(path))
    except FileNotFoundError:
        return {}
    except OSError as exc:
        raise PrivateOverlayError(f"cannot read {path}: {exc.strerror}") from exc


def values() -> dict:
    """private.env, overridden by the process environment."""
    return {**load_env(), **os.environ}


def _missing(keys) -> PrivateOverlayError:
    return PrivateOverlayError(
        f"missing private key(s) {', '.join(sorted(keys))} in {private_dir() / ENV_FILE}; "
        f"copy {EXAMPLE_ENV} there and fill it (or set DOTFILES_PRIVATE_DIR)")


def require(*keys: str, env: dict | None = None):
    """The value of one key, or a tuple for several; missing or empty keys are an error."""
    env = values() if env is None else env
    missing = [k for k in keys if not env.get(k)]
    if missing:
        raise _missing(missing)
    return env[keys[0]] if len(keys) == 1 else tuple(env[k] for k in keys)


def expand(text: str, env: dict | None = None) -> str:
    """Replace every ${KEY} with its private value; any unset key is an error."""
    env = values() if env is None else env
    missing = {m.group(1) for m in _VAR.finditer(text) if not env.get(m.group(1))}
    if missing:
        raise _missing(missing)
    return _VAR.sub(lambda m: env[m.group(1)], text)


def expand_tree(node, env: dict | None = None):
    """expand() applied to every string inside a JSON-shaped value."""
    env = values() if env is None else env
    if isinstance(node, str):
        return expand(node, env)
    if isinstance(node, list):
        return [expand_tree(v, env) for v in node]
    if isinstance(node, dict):
        return {k: expand_tree(v, env) for k, v in node.items()}
    return node


def load_hosts(directory: Path | None = None) -> dict:
    """The parsed hosts.private.yaml; {} when the file does not exist."""
    path = (directory or private_dir()) / HOSTS_FILE
    if not path.exists():
        return {}
    try:
        import yaml
    except ModuleNotFoundError as exc:  # never silently ignore an overlay that exists
        raise PrivateOverlayError(f"PyYAML is required to read {path}") from exc
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise PrivateOverlayError(f"cannot read {path}: {exc}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("nodes") or {}, dict):
        raise PrivateOverlayError(f"{path}: expected a mapping with a `nodes` mapping")
    # Values may be ${KEY} references into private.env, so each address is written once.
    return expand_tree(data)


def deep_merge(base, overlay):
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return overlay
    out = dict(base)
    for key, value in overlay.items():
        out[key] = deep_merge(out[key], value) if key in out else value
    return out


def merge_registry(registry: dict, hosts: dict | None = None, strict: bool = True) -> dict:
    """config/fleet/nodes.yaml with the `nodes` of hosts.private.yaml merged in.

    The overlay may only add values to nodes the public registry declares, so a typo
    cannot enroll a phantom node (strict); strict=False ignores them for partial exports.
    """
    hosts = load_hosts() if hosts is None else hosts
    private = hosts.get("nodes") or {}
    public = registry.get("nodes") or {}
    unknown = sorted(set(private) - set(public))
    if unknown and strict:
        raise PrivateOverlayError(f"{private_dir() / HOSTS_FILE}: nodes {', '.join(unknown)} "
                                  "are not declared in config/fleet/nodes.yaml")
    merged = dict(registry)
    merged["nodes"] = {name: deep_merge(node, private.get(name) or {}) for name, node in public.items()}
    return merged


def missing_node_keys(nodes: dict, needs: dict) -> list:
    """needs: {node: [dotted.key, ...]} -> the `nodes.<node>.<key>` paths without a value."""
    missing = []
    for name, keys in needs.items():
        for dotted in keys:
            value = nodes.get(name, {})
            for part in dotted.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            if value in (None, ""):
                missing.append(f"nodes.{name}.{dotted}")
    return missing


def hosts_error(missing) -> PrivateOverlayError:
    return PrivateOverlayError(
        f"missing private host value(s) {', '.join(missing)} in {private_dir() / HOSTS_FILE}; "
        f"copy {EXAMPLE_HOSTS} there and fill it (or set DOTFILES_PRIVATE_DIR)")
