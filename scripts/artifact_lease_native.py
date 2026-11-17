"""Android transport adapter. Shared lease validation stays in artifact-leases.py."""
import base64
import hashlib
import importlib.util
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
import time

# Only direct native spool children and named edge-probe artifacts are admitted.
PATH = re.compile(r'/data/local/tmp/(?:fleet-jobs/[A-Za-z0-9_.-]+|edge-probe-[A-Za-z0-9_.-]+)\Z')

SCAN = r'''set -eu
set -o pipefail
printf 'IDENTITY\t%s\t%s\n' "$(getprop ro.serialno)" "$(getprop ro.product.model)"
encode() { base64 | tr -d '\n'; }
unknown() { printf 'UNKNOWN\t%s\n' "$1"; }
[ -d /proc/1 ] && [ -r /proc/1/maps ] || unknown hidden-or-unreadable-proc-1
ls /proc >/dev/null 2>&1 || unknown unreadable-proc-directory
if [ -r /proc/self/mountinfo ]; then
 printf 'CONFIG\t'; cat /proc/self/mountinfo | encode; printf '\n'
else unknown /proc/self/mountinfo; fi
for proc in /proc/[0-9]*; do
 [ -d "$proc" ] || continue
 for link in cwd exe; do
  if value=$(readlink "$proc/$link" 2>/dev/null); then
   printf 'REF\t'; printf '%s' "$value" | encode; printf '\n'
  else unknown "$proc/$link"; fi
 done
 if [ -r "$proc/maps" ]; then
  printf 'MAPS\t'; cat "$proc/maps" | encode; printf '\n'
 else unknown "$proc/maps"; fi
 if ls "$proc/fd" >/dev/null 2>&1; then
  for fd in "$proc"/fd/*; do
   [ -L "$fd" ] || continue
   if value=$(readlink "$fd" 2>/dev/null); then
    printf 'REF\t'; printf '%s' "$value" | encode; printf '\n'
   else unknown "$fd"; fi
  done
 else unknown "$proc/fd"; fi
done
# Both native restart desired state and runtime/model configuration are refs.
for config in /data/local/tmp/phone-native-inference /data/local/tmp/edge-probe-config; do
 if [ -e "$config" ]; then
  if [ -f "$config" ] && [ -r "$config" ] && [ ! -L "$config" ]; then
   printf 'CONFIG\t'; cat "$config" | encode; printf '\n'
  else unknown "$config"; fi
 fi
done
inspect() {
 item=$1
 [ -d "$item" ] || return 0
 safe=yes
 parent=$item
 while [ "$parent" != / ]; do
  [ ! -L "$parent" ] || safe=no
  parent=${parent%/*}; [ -n "$parent" ] || parent=/
 done
 bytes=$(du -sk "$item" 2>/dev/null) || { unknown "$item/size"; return 0; }
 bytes=${bytes%%[!0-9]*}
 identity=$(stat -c '%d:%i:%Y:%Z' "$item") || { unknown "$item/stat"; return 0; }
 fingerprint=$(find "$item" -xdev -exec stat -c '%d:%i:%s:%Y:%Z:%n' {} \; | sort | sha256sum)
 fingerprint=${fingerprint%% *}
 printf 'ITEM\t'; printf '%s' "$item" | encode
 printf '\t%s\t%s\t%s\t%s\n' "$bytes" "$identity" "$safe" "$fingerprint"
 if [ -f "$item/exit" ] && [ ! -L "$item/exit" ] && [ -r "$item/exit" ]; then
  printf 'TERMINAL\t'; printf '%s' "$item" | encode; printf '\t'
  head -c 32 "$item/exit" | encode; printf '\n'
 fi
 if [ -f "$item/.artifact-lease.json" ] && [ ! -L "$item/.artifact-lease.json" ] && [ -r "$item/.artifact-lease.json" ]; then
  size=$(stat -c %s "$item/.artifact-lease.json")
  if [ "$size" -le 16384 ]; then
   printf 'LEASE\t'; printf '%s' "$item" | encode; printf '\t'
   cat "$item/.artifact-lease.json" | encode; printf '\n'
  else unknown "$item/oversize-lease"; fi
 fi
}
for item in /data/local/tmp/fleet-jobs/* /data/local/tmp/edge-probe-*; do inspect "$item"; done
'''


def core():
    spec = importlib.util.spec_from_file_location('artifact_lease_core', Path(__file__).with_name('artifact-leases.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def snapshot(adb, serial, node, run):
    raw = run([adb, '-s', serial, 'shell', 'sh'], SCAN)
    lines = raw.splitlines()
    if not lines or lines[0].split('\t') != ['IDENTITY', node['serial'], node['model']]:
        raise RuntimeError('native identity mismatch')
    result = {'items': [], 'references': [], 'unknown': []}
    leases = {}
    for line in lines[1:]:
        fields = line.split('\t')
        if fields[0] == 'UNKNOWN':
            result['unknown'].append(fields[1])
        elif fields[0] in {'REF', 'MAPS', 'CONFIG'}:
            result['references'].append(base64.b64decode(fields[1], validate=True).decode(errors='replace'))
        elif fields[0] == 'ITEM':
            path = base64.b64decode(fields[1], validate=True).decode()
            result['items'].append({'path': path, 'bytes': int(fields[2]) * 1024,
                                    'identity': fields[3], 'safe_ancestors': fields[4] == 'yes',
                                    'fingerprint': fields[5]})
        elif fields[0] == 'LEASE':
            path = base64.b64decode(fields[1], validate=True).decode()
            lease_bytes = base64.b64decode(fields[2], validate=True)
            try: leases[path] = json.loads(lease_bytes)
            except (ValueError, UnicodeError): leases[path] = None
            for item in result['items']:
                if item['path'] == path:
                    item['lease_sha256'] = hashlib.sha256(lease_bytes).hexdigest()
        elif fields[0] == 'TERMINAL':
            path = base64.b64decode(fields[1], validate=True).decode()
            value = base64.b64decode(fields[2], validate=True).decode().strip()
            for item in result['items']:
                if item['path'] == path:
                    item['terminal'] = bool(re.fullmatch(r'-?[0-9]+', value))
        else:
            raise RuntimeError('unrecognized native inventory record')
    for item in result['items']:
        item['lease'] = leases.get(item['path'])
    return result


def classify(item, evidence, name, now, validate):
    reasons = []
    if not PATH.fullmatch(item['path']) or PurePosixPath(item['path']).name in {'.', '..'}:
        reasons.append('outside fixed allowlist')
    if not item['safe_ancestors']:
        reasons.append('symlink ancestor')
    if evidence['unknown']:
        reasons.append('incomplete native process/config visibility')
    if not isinstance(item['lease'], dict):
        reasons.append('missing or invalid lease')
    else:
        reason = validate(item['lease'], item['path'], name, now)
        if reason: reasons.append(reason)
        if item['lease'].get('kind') not in {'spool', 'tmp', 'cache'}:
            reasons.append('native model/runtime/worktree protected')
        if item['lease'].get('kind') == 'spool' and not item.get('terminal'):
            reasons.append('spool completion unknown')
    if any(item['path'] in ref for ref in evidence['references']):
        reasons.append('live process/config reference')
    return reasons


def host_references(node):
    """Serving state read failures never mean an empty serving configuration."""
    state = Path.home() / '.local/state/phone-native-inference' / (node['name'] + '.json')
    try:
        return [state.read_text()], []
    except OSError as exc:
        return [], ['host serving config unavailable: ' + str(exc)]


def receipts(adb, serial, item, destination):
    paths = ['.artifact-lease.json', *item['lease']['keep_receipts']]
    # Save known logs regardless of keep_receipts, without following symlinks.
    command = 'set -eu; cd ' + shlex.quote(item['path']) + '; '
    for path in paths:
        command += 'test -f ' + shlex.quote(path) + '; test ! -L ' + shlex.quote(path) + '; '
        parent = PurePosixPath(path).parent
        for ancestor in parent.parents:
            if str(ancestor) != '.':
                command += 'test ! -L ' + shlex.quote(str(ancestor)) + '; '
        if str(parent) != '.': command += 'test ! -L ' + shlex.quote(str(parent)) + '; '
    command += 'set -- ' + shlex.join(paths) + '; '
    command += 'for log in log* stdout* stderr*; do [ ! -e "$log" ] || { test -f "$log"; test ! -L "$log"; set -- "$@" "$log"; }; done; '
    command += 'tar -czf - -- "$@"'
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with destination.open('xb') as stream:
        p = subprocess.run([adb, '-s', serial, 'exec-out', 'sh', '-c', shlex.quote(command)],
                           stdout=stream, stderr=subprocess.PIPE, timeout=120)
        stream.flush()
        import os
        os.fsync(stream.fileno())
    if p.returncode or destination.stat().st_size == 0:
        raise RuntimeError('native receipt archive failed')
    with destination.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def delete(adb, serial, node, item, run):
    """Pin cwd before find -delete; never recursively remove an absolute path."""
    if not PATH.fullmatch(item['path']):
        raise RuntimeError('native actor path outside fixed allowlist')
    reason = core().validate(item['lease'], item['path'], node['name'], time.time())
    if reason:
        raise RuntimeError('native actor lease rejected: ' + reason)
    path = shlex.quote(item['path'])
    lease_hash = hashlib.sha256(json.dumps(item['lease'], sort_keys=True).encode()).hexdigest()
    # Directory identity and all ancestors checked once more inside the actor.
    script = 'set -eu\nset -o pipefail\n'
    script += '[ "$(getprop ro.serialno)" = ' + shlex.quote(node['serial']) + ' ]\n'
    script += 'mkdir /data/local/tmp/.artifact-lease-delete-lock\ntrap "rmdir /data/local/tmp/.artifact-lease-delete-lock" EXIT\n'
    script += 'target=' + path + '\nparent=$target\nwhile [ "$parent" != / ]; do [ ! -L "$parent" ]; parent=${parent%/*}; [ -n "$parent" ] || parent=/; done\n'
    script += '[ "$(stat -c \'%d:%i:%Y:%Z\' "$target")" = ' + shlex.quote(item['identity']) + ' ]\n'
    # Repeat full reference visibility under the native actor lock.
    script += 'evidence=$(' + SCAN + ')\n'
    script += 'if printf "%s\\n" "$evidence" | grep "^UNKNOWN" >/dev/null; then exit 1; fi\n'
    script += """printf "%s\\n" "$evidence" | while IFS="$(printf '\\t')" read -r kind data rest; do case "$kind" in REF|MAPS|CONFIG) if printf "%s" "$data" | base64 -d | grep -F -- "$target" >/dev/null; then exit 1; fi;; esac; done\n"""
    script += '[ "$(sha256sum "$target/.artifact-lease.json" | cut -d " " -f 1)" = ' + shlex.quote(item['lease_sha256']) + ' ]\n'
    script += """fingerprint=$(find "$target" -xdev -exec stat -c '%d:%i:%s:%Y:%Z:%n' {} \\; | sort | sha256sum)\n"""
    script += '[ "${fingerprint%% *}" = ' + shlex.quote(item['fingerprint']) + ' ]\n'
    script += 'cd "$target"\n[ "$(stat -c \'%d:%i:%Y:%Z\' .)" = ' + shlex.quote(item['identity']) + ' ]\n'
    script += 'find . -xdev -depth ! -name . -delete\ncd /\nrmdir "$target"\nprintf "REMOVED\\n"\n'
    answer = run([adb, '-s', serial, 'shell', 'sh'], script)
    if answer.strip() != 'REMOVED': raise RuntimeError('native actor did not confirm removal')
    return {'event': 'removed', 'path': item['path'], 'bytes': item['bytes'], 'lease_digest': lease_hash}


def inventory(adb, serial, node, apply, run):
    name = node['name']
    policy = core()
    evidence = snapshot(adb, serial, node, run)
    refs, unknown = host_references(node)
    evidence['references'].extend(refs)
    evidence['unknown'].extend(unknown)
    now = time.time()
    items = evidence['items']
    for item in items:
        item['reasons'] = classify(item, evidence, name, now, policy.validate)
        item['eligible'] = not item['reasons']
    actions = []
    stamp = str(time.time_ns())
    root = Path.home() / '.local/state/artifact-leases/native' / name / stamp
    eligible = [item for item in items if item['eligible']]
    for index, item in enumerate(sorted(eligible, key=lambda row: row['lease']['created_at'] + row['lease']['ttl'])):
        if not apply or not item['eligible']: continue
        digest = receipts(adb, serial, item, root / (str(index) + '.tar.gz'))
        fresh = snapshot(adb, serial, node, run)
        fresh_refs, fresh_unknown = host_references(node)
        fresh['references'].extend(fresh_refs)
        fresh['unknown'].extend(fresh_unknown)
        current = next((row for row in fresh['items'] if row['path'] == item['path']), None)
        if current != {key: value for key, value in item.items() if key not in {'reasons', 'eligible'}} or classify(current, fresh, name, time.time(), policy.validate):
            actions.append({'event': 'kept_after_receipt', 'path': item['path']})
            continue
        root.mkdir(parents=True, exist_ok=True)
        policy.atomic_json(root / (str(index) + '.intent.json'), {'item': item, 'receipt_sha256': digest})
        action = delete(adb, serial, node, item, run)
        action['receipt_sha256'] = digest
        actions.append(action)
        policy.atomic_json(root / 'actions.json', actions)
    return {'schema': 'z0.artifact-native-inventory.v1', 'identity': node['serial'],
            'transport': serial, 'mode': 'apply' if apply else 'dry-run',
            'proc_visibility': 'unknown' if evidence['unknown'] else 'observed',
            'unknown': evidence['unknown'], 'items': items, 'actions': actions,
            'would_reap_bytes': sum(item['bytes'] for item in items if item['eligible']),
            'removed_bytes': sum(action.get('bytes', 0) for action in actions if action['event'] == 'removed')}
