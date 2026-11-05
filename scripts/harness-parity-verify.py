#!/usr/bin/env python3
"""Verify applied sync records against live files and adjacent backups, read-only.

Run on MBP with the sync-apply.json manifest on stdin. No secret values print.
"""
import hashlib
import json
from pathlib import Path
import socket
import stat
import sys

import yaml

manifest = json.load(sys.stdin)
if socket.gethostname() != 'mbp' or not manifest.get('apply'):
    raise SystemExit('expected applied MBP manifest')
results = []
for record in manifest['changed']:
    path, backup = Path(record['path']), Path(record['backup'])
    if not path.is_relative_to(Path.home()) or backup != Path(str(path) + '.bak-ayo'):
        raise SystemExit('manifest path outside owner home or unexpected backup suffix')
    before, after = backup.read_bytes(), path.read_bytes()
    checks = {
        'backup_sha256': hashlib.sha256(before).hexdigest() == record['before_sha256'],
        'live_sha256': hashlib.sha256(after).hexdigest() == record['after_sha256'],
        'mode_preserved': stat.S_IMODE(backup.stat().st_mode) == stat.S_IMODE(path.stat().st_mode),
    }
    parse = yaml.safe_load if path.suffix == '.yaml' else json.loads
    original, actual = parse(before), parse(after)
    expected = dict(original)
    for dotted, value in record['changes'].items():
        if dotted.startswith('model.'):
            expected['model'] = dict(expected['model'], **{dotted.split('.', 1)[1]: value})
        else:
            expected[dotted] = value
    checks['only_authorized_fields_changed'] = actual == expected
    results.append({'path': str(path), 'backup': str(backup), 'checks': checks, 'pass': all(checks.values())})
print(json.dumps({'files_checked': len(results), 'pass': all(r['pass'] for r in results), 'results': results}, indent=2))
raise SystemExit(0 if all(r['pass'] for r in results) else 1)
