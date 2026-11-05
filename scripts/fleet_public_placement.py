"""Route reviewed --public jobs to free GitHub CI (kvnloo/fleet-runner, ubuntu-latest).

Exit 0 = dispatch via fleet-avrea, 3 = GitHub-eligible but larger than ubuntu-latest
(4 vCPU / 16 GB) so Boat, 1 = stay on the home fleet. GitHub CI checks out
the exact pushed commit, so it needs a verified-public GitHub origin, a clean tree
and a HEAD that the public repository already has. Unknown state never moves work.
Boat is not chosen here: it is only for work GitHub can't run (fleet-build --boat-need).
"""
import argparse
import json
import re
import subprocess
import sys


def github_repo(url):
    match = re.fullmatch(r'(?:https://github\.com/|git@github\.com:|ssh://git@github\.com/)'
                         r'([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+?)(?:\.git)?/?', url.strip())
    return match[1] if match else None


GH_CPUS, GH_MEM_MIB = 4, 16 * 1024


def mem_mib(value):
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([GgMm])?i?', value or '')
    if not match:
        return 0
    number = float(match[1])
    return number if (match[2] or 'G') in 'Mm' else number * 1024


def too_big(cpus, mem):
    try:
        cpu_count = float(cpus) if cpus else 0
    except ValueError:
        cpu_count = 0
    return cpu_count > GH_CPUS or mem_mib(mem) > GH_MEM_MIB


def choose(public_repo, clean, pushed, big=False):
    decision = {'policy': 'public-github-ci-first', 'selected_lane': 'mbp'}
    if public_repo is not True:
        return {**decision, 'reason': 'source-not-verified-public'}
    if not clean:
        return {**decision, 'reason': 'dirty-tree'}
    if not pushed:
        return {**decision, 'reason': 'head-not-pushed'}
    if big:
        return {**decision, 'selected_lane': 'boat', 'reason': 'exceeds-ubuntu-latest-4vcpu-16gb'}
    return {**decision, 'selected_lane': 'github-ci', 'reason': 'public-clean-pushed-head'}


def git(src, *args):
    return subprocess.run(['git', '-C', src, *args], capture_output=True, text=True, timeout=10)


def gh(*args):
    return subprocess.run(['gh', 'api', *args], capture_output=True, text=True, timeout=20)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--src', required=True)
    parser.add_argument('--cpus', default='')
    parser.add_argument('--mem', default='')
    args = parser.parse_args()
    try:
        remote = git(args.src, 'remote', 'get-url', 'origin')
        repo = github_repo(remote.stdout) if remote.returncode == 0 else None
        public = clean = pushed = None
        if repo:
            meta = gh('repos/' + repo, '--jq', '.private')
            public = meta.stdout.strip() == 'false' if meta.returncode == 0 else None
        if public:
            status = git(args.src, 'status', '--porcelain')
            clean = status.returncode == 0 and not status.stdout.strip()
            head = git(args.src, 'rev-parse', 'HEAD').stdout.strip()
            if clean and re.fullmatch('[0-9a-f]{40}', head):
                commit = gh(f'repos/{repo}/commits/{head}', '--jq', '.sha')
                pushed = commit.returncode == 0 and commit.stdout.strip() == head
        decision = choose(public, clean, pushed, too_big(args.cpus, args.mem))
        if repo:
            decision['repository'] = repo
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        decision = {'policy': 'public-github-ci-first', 'selected_lane': 'mbp',
                    'reason': 'state-unavailable', 'error_type': type(exc).__name__}
    print('fleet-build: placement ' + json.dumps(decision), file=sys.stderr, flush=True)
    return {'github-ci': 0, 'boat': 3}.get(decision['selected_lane'], 1)


if __name__ == '__main__':
    sys.exit(main())
