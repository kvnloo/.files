#!/usr/bin/env python3
"""Groot-controlled, expired-lease-only MBP stage retention. Default: report only."""
import argparse
import hashlib
import importlib.util
import math
import json
import os
from pathlib import Path
import runpy
import shlex
import shutil
import stat
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
STAGES = Path('/home/agentjob/.local/state/fleet/kueue')


def load_leases():
    spec = importlib.util.spec_from_file_location('leases', Path(__file__).with_name('artifact-leases.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def terminal(job):
    return any(c.get('type') in ('Complete', 'Failed') and c.get('status') == 'True'
               for c in job.get('status', {}).get('conditions', []))


def protected(snapshot, name, path):
    # All namespaces, not just the normal fleet namespace. Suspended/queued Jobs
    # are live too. Search the entire JSON, including env, commands and volumes.
    for job in snapshot['jobs']:
        if not terminal(job):
            text = json.dumps(job)
            if job['metadata']['name'] == name or str(path) in text or name in text:
                return True
    for pod in snapshot['pods']:
        if pod.get('status', {}).get('phase') not in ('Succeeded', 'Failed'):
            if name in json.dumps(pod) or str(path) in json.dumps(pod):
                return True
    for workload in snapshot['workloads']:
        finished = any(c.get('type') == 'Finished' and c.get('status') == 'True'
                       for c in workload.get('status', {}).get('conditions', []))
        if not finished and name in json.dumps(workload):
            return True
    return False


def identity(path, uid):
    """Reject links, mounts, foreign ownership and special files throughout tree."""
    if not path.is_absolute() or '..' in path.parts:
        raise ValueError('unsafe path')
    for parent in (path, *path.parents):
        if parent.is_symlink():
            raise ValueError('symlink component')
    root = path.lstat()
    rows = []
    for base, dirs, files in os.walk(path, followlinks=False):
        for entry in [Path(base)] + [Path(base) / n for n in files + dirs]:
            st = entry.lstat()
            if st.st_uid != uid or st.st_dev != root.st_dev or not (stat.S_ISDIR(st.st_mode) or stat.S_ISREG(st.st_mode)):
                raise ValueError('foreign owner, filesystem or unsafe file type')
            rows.append((str(entry.relative_to(path)), st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns))
    return hashlib.sha256(json.dumps(sorted(rows)).encode()).hexdigest()


def digest(path):
    """Content proof; reject links and special files rather than follow them."""
    if any(parent.is_symlink() for parent in (path, *path.parents)):
        raise ValueError('symlink export component')
    if path.is_file():
        h = hashlib.sha256()
        with path.open('rb') as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b''):
                h.update(block)
        return {'file': h.hexdigest()}
    if not path.is_dir():
        raise ValueError('missing export')
    rows = {}
    for base, dirs, files in os.walk(path, followlinks=False):
        for name in dirs + files:
            item = Path(base) / name
            if item.is_symlink() or not (item.is_dir() or item.is_file()):
                raise ValueError('unsafe export')
            rows[str(item.relative_to(path))] = digest(item) if item.is_file() else 'directory'
    return rows


def eligible(path, receipt, snapshot, leases, now, uid):
    if protected(snapshot, path.name, path):
        return 'live or referenced'
    if receipt.get('job_id') != path.name:
        return 'missing identity'
    def elapsed(value):
        return (not isinstance(value, bool) and isinstance(value, (int, float))
                and math.isfinite(value) and 0 <= value < now)
    if receipt.get('keep') and not elapsed(receipt.get('keep_until')):
        return 'explicit keep (legacy or unexpired)'
    if 'retention_until' in receipt and not elapsed(receipt['retention_until']):
        return 'retention window not elapsed'
    if 'fetch_completed' in receipt and receipt['fetch_completed'] is not True:
        return 'fetch not completed'
    evidence = receipt.get('terminal', {}).get('job', {})
    if evidence.get('metadata', {}).get('name') != path.name or not terminal(evidence):
        return 'missing terminal Job evidence'
    if receipt.get('host'):
        return 'host scope requires independent liveness proof'
    workload = receipt.get('terminal', {}).get('workload', {})
    if workload and not any(c.get('type') == 'Finished' and c.get('status') == 'True'
                            for c in workload.get('status', {}).get('conditions', [])):
        return 'missing terminal Workload evidence'
    lease_path = path / leases.SIDECAR
    if lease_path.is_symlink():
        return 'symlink lease'
    lease = json.loads(lease_path.read_text())
    reason = leases.validate(lease, path, 'mbp', now)
    if reason or lease.get('kind') != 'spool':
        return reason or 'not spool'
    if lease.get('keep') or lease.get('pinned'):
        return 'explicit keep'
    identity(path, uid)
    for value in receipt.get('fetch', []):
        relative = Path(value)
        if relative.is_absolute() or '..' in relative.parts or not relative.parts:
            return 'unsafe export path'
        if receipt.get('_fetch_proof', {}).get(value) != digest(path / relative):
            return 'missing fetch proof'
    return None


def service_process(proc, uid):
    """Only the exact same-user init-owned manager and its sd-pam helper."""
    def facts(path):
        if path.stat().st_uid != uid:
            raise ValueError('foreign process')
        data = (path / 'stat').read_text()
        parent = int(data[data.rfind(')') + 2:].split()[1])
        command = (path / 'cmdline').read_bytes()
        return parent, command
    try:
        parent, command = facts(proc)
        manager_command = b'/usr/lib/systemd/systemd\x00--user\x00'
        if parent == 1 and command == manager_command:
            return True
        if command.rstrip(b'\x00') == b'(sd-pam)':
            grandparent, parent_command = facts(proc.parent / str(parent))
            return grandparent == 1 and parent_command == manager_command
    except (OSError, ValueError, IndexError):
        pass
    return False


def maintenance_ancestors(pid=None, proc_root=Path('/proc')):
    """Exclude only this invocation and its observed PPid chain, never peers."""
    current = os.getpid() if pid is None else pid
    seen = set()
    while current:
        if current in seen or current < 0:
            raise ValueError('invalid maintenance ancestry')
        seen.add(current)
        values = [line.split(':', 1)[1].strip()
                  for line in (proc_root / str(current) / 'status').read_text().splitlines()
                  if line.startswith('PPid:')]
        if len(values) != 1:
            raise ValueError('missing maintenance parent')
        current = int(values[0])
    return seen


def worker(payload, leases, apply=False, root=STAGES):
    if Path.home() != Path('/home/agentjob') or os.getuid() == 0:
        raise ValueError('requires unprivileged agentjob identity')
    references = []
    visibility_errors = []
    ancestors = maintenance_ancestors()
    for proc in Path('/proc').iterdir():
        if not proc.name.isdigit():
            continue
        if int(proc.name) in ancestors:
            continue
        try:
            # Container processes are represented by API Pod/Job references;
            # native host stages are excluded above. Inspect this actor's user.
            if proc.stat().st_uid != os.getuid():
                continue
            if service_process(proc, os.getuid()):
                continue
            references.append(os.readlink(proc / 'cwd'))
            references.append((proc / 'cmdline').read_bytes().decode(errors='replace'))
            references.append((proc / 'environ').read_bytes().decode(errors='replace'))
            references.extend(os.readlink(fd) for fd in (proc / 'fd').iterdir())
        except (FileNotFoundError, ProcessLookupError):
            pass
        except OSError as exc:
            visibility_errors.append(str(exc))
    rows = []
    for name, receipt in payload['receipts'].items():
        if not name.startswith('fleet-mbp-') or '/' in name or '..' in name:
            continue
        path = root / name
        try:
            if visibility_errors or any(str(path) in ref for ref in references):
                rows.append({'stage': str(path), 'action': 'keep', 'reason': 'local reference or visibility unknown'})
                continue
            reason = eligible(path, receipt, payload['snapshot'], leases, time.time(), os.getuid())
            token = identity(path, os.getuid()) if not reason else None
            row = {'stage': str(path), 'identity': token, 'reason': reason, 'action': 'keep' if reason else 'would-delete'}
            if apply and not reason:
                if payload.get('plan', {}).get(str(path)) != token:
                    row.update(action='keep', reason='absent or changed plan identity')
                else:
                    # Recheck immediately before the fd-safe stdlib remover.
                    if not shutil.rmtree.avoids_symlink_attacks or identity(path, os.getuid()) != token:
                        raise ValueError('unsafe deletion boundary')
                    archive = Path.home() / '.local/state/fleet/stage-retention-receipts' / (name + '-' + token)
                    leases.receipt_copy(path, json.loads((path / leases.SIDECAR).read_text()), archive)
                    if identity(path, os.getuid()) != token:
                        raise ValueError('stage changed during receipt archival')
                    shutil.rmtree(path)
                    row['action'] = 'deleted'
            rows.append(row)
        except (OSError, ValueError, TypeError, KeyError) as exc:
            rows.append({'stage': str(path), 'action': 'keep', 'reason': str(exc)})
    return rows


def checked(argv, **kwargs):
    return subprocess.run(argv, check=True, capture_output=True, text=True, timeout=120, **kwargs).stdout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    parser.add_argument('--apply-plan', type=Path)
    parser.add_argument('--automatic', action='store_true',
                        help='plan then apply under shared fleet submission lock')
    parser.add_argument('--submissions-quiesced', action='store_true',
                        help='operator confirms no submitters or other cleanup actors during apply')
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        payload = json.load(sys.stdin)
        print(json.dumps(worker(payload, load_leases(), payload.get('apply', False))))
        return
    if not args.output or not args.output.is_absolute():
        parser.error('--output must be an absolute report path')
    if args.automatic and args.apply_plan:
        parser.error('--automatic and --apply-plan are mutually exclusive')
    fleet = runpy.run_path(str(ROOT / 'scripts/fleet'))
    node = fleet['registry']()[1]['mbp']
    if node['ssh_user'] != 'agentjob':
        raise ValueError('registry must use agentjob')
    ssh = fleet['ssh_cmd'](node)
    kube = ['kubectl', '--kubeconfig', str(Path.home() / '.kube/k3s.yaml')]
    def snapshot():
        return {key: json.loads(checked(kube + ['get', kind, '-A', '-o', 'json']))['items']
                for key, kind in [('jobs', 'jobs'), ('pods', 'pods'), ('workloads', 'workloads.kueue.x-k8s.io')]}
    from fleet_paths import runs_dir
    receipts = {}
    for file in runs_dir().glob('fleet-mbp-*.json'):
        if file.is_symlink():
            continue
        receipt = json.loads(file.read_text())
        receipt['_fetch_proof'] = {}
        for value in receipt.get('fetch', []):
            relative = Path(value)
            if relative.is_absolute() or '..' in relative.parts:
                continue
            try:
                receipt['_fetch_proof'][value] = digest(runs_dir() / file.stem / relative)
            except (OSError, ValueError):
                pass
        receipts[file.stem] = receipt
    if args.apply_plan and not args.submissions_quiesced:
        parser.error('--apply-plan requires --submissions-quiesced')
    payload = {'snapshot': snapshot(), 'receipts': receipts, 'apply': bool(args.apply_plan)}
    if args.apply_plan:
        plan = json.loads(args.apply_plan.read_text())
        if time.time() - plan['created_at'] > 300 or plan['created_at'] > time.time():
            raise ValueError('plan expired (five minutes)')
        payload['plan'] = {r['stage']: r['identity'] for r in plan['rows'] if r['action'] == 'would-delete'}
        # A second complete API observation closes normal queued-reference races;
        # apply still requires submission quiescence (see operator docs).
        payload['snapshot'] = snapshot()
    sources = {name: (ROOT / 'scripts' / name).read_text() for name in ('fleet-stage-retention.py', 'artifact-leases.py')}
    wrapper = '''import json,pathlib,sys,tempfile,subprocess
p=json.load(sys.stdin)
with tempfile.TemporaryDirectory(prefix='fleet-retention-') as tmp:
 for name,source in p['sources'].items(): (pathlib.Path(tmp)/name).write_text(source)
 result=subprocess.run([sys.executable,str(pathlib.Path(tmp)/'fleet-stage-retention.py'),'--worker'],input=json.dumps(p['payload']),text=True,capture_output=True,check=True)
 print(result.stdout)
'''
    def execute():
        return json.loads(checked(ssh + ['python3 -c ' + shlex.quote(wrapper)],
                                  input=json.dumps({'sources': sources, 'payload': payload})))
    rows = execute()
    if args.automatic:
        payload['plan'] = {r['stage']: r['identity'] for r in rows if r['action'] == 'would-delete'}
        payload['snapshot'] = snapshot()
        payload['apply'] = True
        rows = execute()
    report = {'schema': 'z0.fleet-stage-retention.v1', 'created_at': time.time(), 'rows': rows}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + '\n')


if __name__ == '__main__':
    if '--worker' in sys.argv:
        main()
    else:
        from fleet_stage_lock import exclusive_retention_lock
        with exclusive_retention_lock():
            main()
