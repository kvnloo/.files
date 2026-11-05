#!/usr/bin/env python3
"""Read-only, allowlisted harness inventory. Never reads auth or environment files.

Run on each owner host with python3, then use --diff LEFT RIGHT.
Exit 1 from --diff means differences remain, not an inspection failure.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import socket
import subprocess

import yaml

CONFIGS = {
    '.fx/settings.json': ['provider', 'effort', 'fast_mode', 'fast_mode_model_bound', 'models', 'skill_symlink_authorities'],
    '.pi/agent/settings.json': ['defaultProvider', 'defaultModel', 'defaultThinkingLevel', 'packages', 'extensions', 'skills'],
    '.pi/agent/sol-pi.json': ['version', 'actionFusion', 'observationPack', 'evidencePreservingReducer', 'onlineContextCompact', 'cacheWriteReadRatio'],
    '.claude/settings.json': ['model', 'effortLevel', 'modelSettings', 'enabledPlugins', 'hooks', 'statusLine', 'permissions', 'sandbox', 'autoMode', 'tui', 'skipDangerousModePermissionPrompt', 'skipWorkflowUsageWarning'],
    '.config/opencode/opencode.jsonc': ['model', 'small_model', 'instructions', 'plugin'],
}
HERMES_FIELDS = ['model.default', 'model.provider', 'model.reasoning_effort', 'model.max_tokens', 'model.aliases', 'context.engine', 'delegation.model', 'delegation.provider', 'delegation.fallback_providers', 'fallback_providers', 'system_prompt', 'system_prompt_file', 'agent.system_prompt_file', 'terminal.cwd']
RULES = ['AGENTS.md', 'CLAUDE.md', '.codex/AGENTS.md', '.claude/CLAUDE.md', '.pi/agent/AGENTS.md', '.omp/agent/AGENTS.md', '.config/opencode/AGENTS.md', '.hermes/SOUL.md', '.hermes/AGENTS.md']
SECRET_KEY = re.compile(r'api.?key|token|password|secret|credential|authorization|auth', re.I)


def safe(value):
    if isinstance(value, dict):
        return {k: safe(v) for k, v in value.items() if not SECRET_KEY.search(k)}
    if isinstance(value, list):
        return [safe(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r'(?i)(https?://)[^/@\s]+:[^/@\s]+@', r'\1[REDACTED]@', value)
        value = re.sub(r'(?i)([?&](?:key|token|secret|password)=)[^&\s]+', r'\1[REDACTED]', value)
    return value


def command(args):
    try:
        result = subprocess.run(args, text=True, capture_output=True, timeout=8)
        return {'exit': result.returncode, 'stdout': result.stdout.strip()}
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {'error': type(exc).__name__}


def load(path):
    text = path.read_text()
    if path.suffix in ('.yaml', '.yml'):
        return yaml.safe_load(text) or {}
    if path.suffix == '.jsonc':
        text = re.sub(r'("(?:\\.|[^"\\])*"|/\*.*?\*/|//[^\n]*)', lambda m: m[0] if m[0].startswith('"') else '', text, flags=re.S)
        text = re.sub(r',\s*([}\]])', r'\1', text)
    return json.loads(text)


def field(data, dotted):
    for key in dotted.split('.'):
        if not isinstance(data, dict) or key not in data:
            return '<unset>'
        data = data[key]
    return safe(data)


def snapshot():
    home = Path.home()
    values = {}
    sources = {}
    errors = []
    configs = dict(CONFIGS)
    configs['.hermes/config.yaml'] = HERMES_FIELDS
    profiles = home / '.hermes/profiles'
    if profiles.is_dir():
        for p in sorted(profiles.iterdir()):
            if p.is_dir() and not p.name.startswith('.'):
                configs[str(p.relative_to(home) / 'config.yaml')] = HERMES_FIELDS
    for rel, fields in configs.items():
        path = home / rel
        values[rel + ':exists'] = path.is_file()
        if not path.is_file():
            continue
        sources[rel] = str(path.resolve())
        try:
            data = load(path)
            for key in fields:
                values[rel + ':' + key] = field(data, key)
            if rel.endswith('config.yaml'):
                for lane, settings in (data.get('auxiliary') or {}).items():
                    if isinstance(settings, dict):
                        for key in ('model', 'provider', 'fallback_providers'):
                            values[rel + ':auxiliary.' + lane + '.' + key] = field(settings, key)
            # Key names identify settings we have not safely classified yet.
            if rel.endswith('sol-pi.json'):
                values[rel + ':unclassified_keys'] = sorted(k for k in data if k not in fields and not SECRET_KEY.search(k))
        except (ValueError, OSError, yaml.YAMLError) as exc:
            errors.append({'path': rel, 'error': type(exc).__name__})
    rules = [home / rel for rel in RULES]
    for directory in [home / '.claude/rules', home / '.hermes/profiles']:
        if directory.name == 'rules' and directory.is_dir():
            rules.extend(sorted(directory.glob('*.md')))
        elif directory.is_dir():
            for p in sorted(directory.iterdir()):
                if p.is_dir() and not p.name.startswith('.'):
                    rules.extend([p / 'SOUL.md', p / 'AGENTS.md'])
    rules.extend([Path('/workspace/CLAUDE.md'), Path('/workspace/AGENTS.md'), home / 'workspace/CLAUDE.md', home / 'workspace/AGENTS.md'])
    active = home / '.hermes/active_profile'
    values['hermes:active_profile'] = active.read_text().strip() if active.is_file() else '<unset>'
    for path in rules:
        rel = str(path.relative_to(home)) if path.is_relative_to(home) else str(path)
        values[rel + ':exists'] = path.is_file()
        if path.is_file():
            values[rel + ':sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
            sources[rel] = str(path.resolve())
    for name in ['hermes', 'fx', 'pi', 'claude', 'agy', 'opencode']:
        exe = shutil.which(name)
        # Include common owner paths even when a noninteractive PATH omits them.
        if not exe:
            exe = next((str(p) for p in [home / '.local/bin' / name, home / '.npm-global/bin' / name, home / '.bun/bin' / name] if p.is_file()), None)
        values[name + ':installed'] = exe is not None
        sources[name + ':executable'] = str(Path(exe).resolve()) if exe else None
        if name in ['fx', 'claude', 'pi'] and exe:
            values[name + ':version'] = command([exe, '--version'])
    repo = home / '.hermes/hermes-agent'
    values['hermes:revision'] = command(['git', '-C', str(repo), 'rev-parse', 'HEAD'])
    stamp = repo / 'install-stamp.json'
    values['hermes:install_version'] = field(load(stamp), 'baseVersion') if stamp.is_file() else '<no install stamp>'
    version_file = repo / 'pyproject.toml'
    if version_file.is_file():
        match = re.search(r'^version\s*=\s*"([^"]+)"', version_file.read_text(), re.M)
        values['hermes:package_version'] = match[1] if match else '<unknown>'
    return {'host': socket.gethostname(), 'values': values, 'sources': sources, 'errors': errors}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--diff', nargs=2, metavar=('LEFT', 'RIGHT'))
    args = parser.parse_args()
    if args.diff:
        left, right = [json.loads(Path(p).read_text()) for p in args.diff]
        diffs = [{'setting': k, 'groot': left['values'].get(k, '<missing>'), 'mbp': right['values'].get(k, '<missing>')} for k in sorted(left['values'].keys() | right['values'].keys()) if left['values'].get(k, '<missing>') != right['values'].get(k, '<missing>')]
        print(json.dumps({'differences': diffs, 'count': len(diffs), 'inspection_errors': left['errors'] + right['errors']}, indent=2))
        return 2 if left['errors'] or right['errors'] else int(bool(diffs))
    print(json.dumps(snapshot(), indent=2, sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
