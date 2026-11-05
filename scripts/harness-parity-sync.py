#!/usr/bin/env python3
"""Sync a narrow, non-secret MBP setting set from an allowlisted groot snapshot.

Default is a dry run. --apply backs up each changed file to FILE.bak-ayo,
refuses existing backups and symlinks, preserves unrelated settings, and
checks for concurrent writes. No harness process, auth store, or service runs.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import stat
import sys
import tempfile

import yaml
from yaml.nodes import MappingNode, ScalarNode


def sha(data):
    return hashlib.sha256(data).hexdigest()


def yaml_model(text, desired):
    root = yaml.compose(text)
    if not isinstance(root, MappingNode):
        raise ValueError('config root is not a mapping')
    pairs = [(key, value) for key, value in root.value if key.value == 'model']
    if len(pairs) != 1 or not isinstance(pairs[0][1], MappingNode):
        raise ValueError('expected exactly one model mapping')
    mapping = pairs[0][1]
    if mapping.flow_style:
        raise ValueError('flow-style model mapping is not supported')
    keys = {key.value: (key, value) for key, value in mapping.value}
    if len(keys) != len(mapping.value):
        raise ValueError('duplicate model keys')
    if set(keys) - {'default', 'provider', 'reasoning_effort', 'aliases', 'max_tokens'}:
        raise ValueError('model has endpoint or other host-specific keys; manual review required')
    edits = []
    missing = []
    for key, value in desired.items():
        if key in keys:
            node = keys[key][1]
            if not isinstance(node, ScalarNode):
                raise ValueError('model setting is not scalar')
            if node.value != value:
                edits.append((node.start_mark.index, node.end_mark.index, json.dumps(value)))
        else:
            missing.append(' ' * mapping.start_mark.column + key + ': ' + json.dumps(value) + '\n')
    if missing:
        index = mapping.end_mark.index
        prefix = '' if not text[:index] or text[index - 1] == '\n' else '\n'
        edits.append((index, index, prefix + ''.join(missing)))
    for start, end, value in sorted(edits, reverse=True):
        text = text[:start] + value + text[end:]
    return text


def replace(path, raw, updated, changes, apply):
    if updated == raw:
        return None
    if path.is_symlink() or not path.is_file():
        raise ValueError('refusing symlink or non-regular file')
    backup = Path(str(path) + '.bak-ayo')
    if backup.exists() or backup.is_symlink():
        raise ValueError('backup already exists; not overwriting')
    record = {'path': str(path), 'backup': str(backup), 'changes': changes, 'before_sha256': sha(raw), 'after_sha256': sha(updated), 'applied': apply}
    if not apply:
        return record
    mode = stat.S_IMODE(path.stat().st_mode)
    if path.read_bytes() != raw:
        raise ValueError('file changed concurrently before backup')
    fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, 'wb') as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=path.name + '.tmp-ayo-', dir=path.parent)
    try:
        with os.fdopen(tmp_fd, 'wb') as stream:
            stream.write(updated)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(tmp_name, mode)
        if path.read_bytes() != raw:
            raise ValueError('file changed concurrently before replacement; backup preserved')
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return record


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    source = json.load(sys.stdin)
    if socket.gethostname() != 'mbp' or source.get('host') != 'groot':
        raise SystemExit('only groot snapshot to owner MBP is supported')
    values = source['values']
    desired = {k: values['.hermes/config.yaml:model.' + k] for k in ['default', 'provider', 'reasoning_effort']}
    if desired['provider'] != 'anthropic' or not desired['default'].startswith('claude-'):
        raise SystemExit('source model is not the owner Anthropic baseline')
    home = Path.home()
    records, skipped = [], []
    paths = [home / '.hermes/config.yaml'] + sorted((home / '.hermes/profiles').glob('*/config.yaml'))
    for path in paths:
        if not path.is_file() or path.parent.name.startswith('.') and path != home / '.hermes/config.yaml':
            continue
        raw = path.read_bytes()
        data = yaml.safe_load(raw)
        model = data.get('model') or {}
        # MBP-only GPT profiles get the groot global baseline, not another profile's identity.
        is_gpt = str(model.get('default', '')).lower().startswith(('gpt-', 'openai/gpt-'))
        if path != home / '.hermes/config.yaml' and not is_gpt:
            continue
        try:
            updated = yaml_model(raw.decode(), desired).encode()
            actual = yaml.safe_load(updated)
            expected = dict(data)
            expected['model'] = dict(model, **desired)
            if actual != expected:
                raise ValueError('parsed config changed outside the three model fields')
            record = replace(path, raw, updated, {'model.' + k: v for k, v in desired.items()}, args.apply)
            if record:
                records.append(record)
        except ValueError as exc:
            skipped.append({'path': str(path), 'reason': str(exc)})
    for rel, keys in {'.fx/settings.json': ['models'], '.claude/settings.json': ['effortLevel', 'modelSettings']}.items():
        path = home / rel
        if not path.is_file():
            skipped.append({'path': str(path), 'reason': 'target missing'})
            continue
        raw = path.read_bytes()
        data = json.loads(raw)
        changes = {k: values[rel + ':' + k] for k in keys}
        if any(v == '<unset>' for v in changes.values()):
            raise ValueError('source setting missing')
        if all(data.get(k) == v for k, v in changes.items()):
            continue
        updated = json.dumps(dict(data, **changes), indent=2, ensure_ascii=False).encode() + b'\n'
        try:
            record = replace(path, raw, updated, changes, args.apply)
            if record:
                records.append(record)
        except ValueError as exc:
            skipped.append({'path': str(path), 'reason': str(exc)})
    print(json.dumps({'host': socket.gethostname(), 'apply': args.apply, 'changed': records, 'skipped': skipped}, indent=2))


if __name__ == '__main__':
    main()
