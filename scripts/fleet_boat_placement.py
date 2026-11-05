"""Prefer Boat for reviewed public jobs when the MBP is backlogged or under disk pressure.

Exit 0 = send to Boat, 1 = stay on the home fleet. Unknown state never moves work:
private, unverifiable or local-data sources always stay home (T0 rule).
"""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
from fleet_queue_health import node_blocked

KUBE = ['kubectl', '--kubeconfig', str(Path.home() / '.kube/k3s.yaml')]


def github_repo(url):
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)'
                         r'([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', url.strip())
    return match[1] if match else None


def choose(public_repo, queue, node):
    decision: dict = {'policy': 'public-boat-overflow', 'selected_lane': 'mbp'}
    if public_repo is not True:
        return {**decision, 'reason': 'source-not-verified-public'}
    pending = queue.get('status', {}).get('pendingWorkloads', 0) or 0
    decision['mbp_pending_workloads'] = pending
    conditions = {c['type']: c['status'] for c in node.get('status', {}).get('conditions', [])}
    if conditions.get('DiskPressure') == 'True':
        return {**decision, 'selected_lane': 'boat', 'reason': 'mbp-disk-pressure'}
    if pending > 0:
        return {**decision, 'selected_lane': 'boat', 'reason': 'mbp-queue-pending'}
    if queue.get('spec', {}).get('stopPolicy', 'None') != 'None' or node_blocked(node):
        return {**decision, 'selected_lane': 'boat', 'reason': 'mbp-unavailable'}
    return {**decision, 'reason': 'mbp-has-room'}


def is_public(src):
    remote = subprocess.run(['git', '-C', src, 'remote', 'get-url', 'origin'],
                            capture_output=True, text=True, timeout=10)
    repo = github_repo(remote.stdout) if remote.returncode == 0 else None
    if not repo:
        return None
    result = subprocess.run(['gh', 'api', 'repos/' + repo, '--jq', '.private'],
                            capture_output=True, text=True, timeout=20)
    return result.stdout.strip() == 'false' if result.returncode == 0 else None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', required=True)
    args = parser.parse_args()
    try:
        public = is_public(args.src)
        queue, node = {}, {}
        if public:
            queue = json.loads(subprocess.check_output(
                KUBE + ['get', 'clusterqueue', 'lanes', '-o', 'json'], stderr=subprocess.PIPE, timeout=15))
            node = json.loads(subprocess.check_output(
                KUBE + ['get', 'node', 'mbp', '-o', 'json'], stderr=subprocess.PIPE, timeout=15))
        decision = choose(public, queue, node)
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        decision = {'policy': 'public-boat-overflow', 'selected_lane': 'mbp',
                    'reason': 'mbp-state-unavailable', 'error_type': type(exc).__name__}
    print(json.dumps(decision), file=sys.stderr, flush=True)
    return 0 if decision['selected_lane'] == 'boat' else 1


if __name__ == '__main__':
    sys.exit(main())
