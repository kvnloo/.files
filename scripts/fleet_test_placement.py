"""Overflow direct Python test runners to the existing uncapped phone lane."""
import argparse
from decimal import Decimal
import json
from pathlib import Path
import re
import subprocess
import sys


def quantity(value, binary_request=False):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([KMGT]i?|m)?(?:B)?', str(value))
    if not match:
        raise ValueError(f'unsupported resource quantity: {value}')
    amount, suffix = Decimal(match[1]), match[2] or ''
    if suffix == 'm':
        return amount / 1000
    if not suffix:
        return amount
    base = 1024 if suffix.endswith('i') or binary_request else 1000
    return amount * base ** ('KMGT'.index(suffix[0]) + 1)


def python_test(command):
    if not command:
        return False
    executable = Path(command[0]).name
    return executable == 'pytest' or (
        re.fullmatch(r'python(?:3(?:\.\d+)?)?', executable) is not None and
        len(command) >= 3 and command[1] == '-m' and command[2] in ('pytest', 'unittest'))


def choose(command, memory, cpus, queue, memory_explicit=False):
    decision = {'policy': 'python-test-capacity-overflow', 'selected_lane': 'mbp',
                'requested_memory': memory, 'requested_cpus': cpus,
                'memory_explicit': memory_explicit}
    if not python_test(command):
        return {**decision, 'reason': 'not-a-direct-python-test-runner'}
    if memory_explicit and quantity(memory, binary_request=True) > 1024**3:
        return {**decision, 'reason': 'explicit-memory-above-phone-test-scope'}
    quota = {r['name']: quantity(r['nominalQuota'])
             for group in queue['spec']['resourceGroups'] for flavor in group['flavors']
             if flavor['name'] == 'node-mbp' for r in flavor['resources']}
    reserved = {r['name']: quantity(r['total'])
                for flavor in queue.get('status', {}).get('flavorsReservation', [])
                if flavor['name'] == 'node-mbp' for r in flavor['resources']}
    free = {resource: quota[resource] - reserved.get(resource, Decimal(0))
            for resource in ('cpu', 'memory')}
    decision['mbp_free'] = {key: str(value) for key, value in free.items()}
    if quantity(cpus) > free['cpu'] or quantity(memory, binary_request=True) > free['memory']:
        return {**decision, 'selected_lane': 'phones', 'reason': 'mbp-owned-quota-unavailable',
                'phone_resource_policy': ('overflow: mem unspecified, default not applied on phone (O10)'
                                          if not memory_explicit else
                                          'overflow: explicit MBP request recorded, no caps applied on phone (O10)')}
    return {**decision, 'reason': 'mbp-owned-quota-available'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mem', default='3G')
    parser.add_argument('--cpus', default='2')
    parser.add_argument('--mem-explicit', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    if not python_test(command):
        decision = {'policy': 'python-test-capacity-overflow', 'selected_lane': 'mbp',
                    'reason': 'not-a-direct-python-test-runner'}
    elif args.mem_explicit and quantity(args.mem, binary_request=True) > 1024**3:
        decision = choose(command, args.mem, args.cpus, {}, memory_explicit=True)
    else:
        try:
            queue = json.loads(subprocess.check_output([
                'kubectl', '--kubeconfig', str(Path.home()/'.kube/k3s.yaml'),
                'get', 'clusterqueue', 'lanes', '-o', 'json'], stderr=subprocess.PIPE, timeout=15))
            decision = choose(command, args.mem, args.cpus, queue, args.mem_explicit)
        except (OSError, ValueError, KeyError, subprocess.SubprocessError) as exc:
            # Unknown capacity is not authority to move work. Normal Kueue
            # admission remains the owner and exposes its own failure if down.
            decision = {'policy': 'python-test-capacity-overflow', 'selected_lane': 'mbp',
                        'reason': 'mbp-capacity-unavailable', 'error_type': type(exc).__name__}
    print(json.dumps(decision), flush=True)
    return 0 if decision['selected_lane'] == 'phones' else 1


if __name__ == '__main__':
    sys.exit(main())
