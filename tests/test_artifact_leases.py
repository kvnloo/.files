"""Lease actor safety: no expiry, no visibility or no archive means keep."""
import argparse
import importlib.util
import json
from pathlib import Path
import time
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('artifact_leases', Path(__file__).resolve().parents[1] / 'scripts/artifact-leases.py')
leases = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(leases)


def artifact(tmp_path, kind='cache', ttl=1, created=1):
    root = tmp_path / 'allowed'
    root.mkdir(exist_ok=True)
    path = root / 'job'
    path.mkdir(exist_ok=True)
    (path / 'payload.bin').write_bytes(b'x' * 8192)
    lease = dict(schema=leases.SCHEMA, owner='test-job', path=str(path), node='s22', kind=kind,
                 created_at=created, ttl=ttl, keep_receipts=[])
    leases.atomic_json(path / leases.SIDECAR, lease)
    return root, path, lease


def inspect(root, path, refs=None, errors=None):
    with patch.dict(leases.ROOTS, {'s22': [str(root)]}):
        return leases.inspect(path, 's22', refs or {}, errors or [], time.time())


def test_expired_allowlisted_nonlive(tmp_path):
    root, path, _ = artifact(tmp_path)
    assert inspect(root, path)['eligible']


def test_unexpired_is_kept(tmp_path):
    root, path, _ = artifact(tmp_path, created=time.time())
    assert not inspect(root, path)['eligible']


def test_unknown_visibility_is_kept(tmp_path):
    root, path, _ = artifact(tmp_path)
    assert not inspect(root, path, errors=['permission denied'])['eligible']


def test_live_open_file_is_kept(tmp_path):
    root, path, _ = artifact(tmp_path)
    assert not inspect(root, path, refs={str(path / 'payload.bin'): {'open:123'}})['eligible']


def test_symlink_to_artifact_is_kept(tmp_path):
    root, path, _ = artifact(tmp_path)
    link = root / 'alias'
    link.symlink_to(path, target_is_directory=True)
    assert not inspect(root, link)['eligible']


def test_outside_allowlist_and_root_itself_are_kept(tmp_path):
    root, path, _ = artifact(tmp_path)
    assert not leases.allowed(root, [str(root)])
    assert not leases.allowed(path, [str(tmp_path / 'unrelated')])


def test_forged_identity_and_nan_are_kept(tmp_path):
    _, path, lease = artifact(tmp_path)
    assert leases.validate({**lease, 'node': 'groot'}, path, 's22', time.time())
    assert leases.validate({**lease, 'ttl': float('nan')}, path, 's22', time.time())
    assert leases.validate({**lease, 'ttl': True}, path, 's22', time.time())
    assert leases.validate({**lease, 'keep_receipts': ['../secret']}, path, 's22', time.time())


def test_symlink_lease_is_kept(tmp_path):
    root, path, _ = artifact(tmp_path)
    source = tmp_path / 'lease.json'
    (path / leases.SIDECAR).rename(source)
    (path / leases.SIDECAR).symlink_to(source)
    assert not inspect(root, path)['eligible']


def test_nonterminal_spool_is_kept(tmp_path):
    root, path, _ = artifact(tmp_path, kind='spool')
    assert not inspect(root, path)['eligible']
    (path / 'exit').write_text('0\n')
    assert inspect(root, path)['eligible']


def test_git_cannot_bypass_archive_via_cache_kind(tmp_path):
    root, path, _ = artifact(tmp_path)
    (path / '.git').mkdir()
    assert not inspect(root, path)['eligible']


def test_real_apply_retains_receipts(tmp_path):
    root, path, _ = artifact(tmp_path)
    (path / 'receipt.json').write_text('{"result": "measured"}')
    out = tmp_path / 'output'
    args = argparse.Namespace(node='s22', output=str(out), enroll=False, apply=True)
    with patch.dict(leases.ROOTS, {'s22': [str(root)]}), patch.object(leases, 'local_references', return_value=({}, [])):
        leases.run(args)
    report = json.loads((out / 'report.json').read_text())
    assert report['removed_bytes'] > 0
    assert not path.exists()
    assert list((out / 'receipts').rglob('receipt.json'))


def test_newly_live_before_removal_is_kept(tmp_path):
    root, path, _ = artifact(tmp_path)
    out = tmp_path / 'output'
    args = argparse.Namespace(node='s22', output=str(out), enroll=False, apply=True)
    refs = [({}, []), ({}, []), ({str(path / 'payload.bin'): {'process:7'}}, [])]
    with patch.dict(leases.ROOTS, {'s22': [str(root)]}), patch.object(leases, 'local_references', side_effect=refs):
        leases.run(args)
    assert path.exists()


def test_retrolease_starts_now_not_old_mtime(tmp_path):
    root, path, _ = artifact(tmp_path)
    (path / leases.SIDECAR).unlink()
    args = argparse.Namespace(node='s22', output=str(tmp_path / 'output'), enroll=True, apply=True)
    before = time.time()
    with patch.dict(leases.ROOTS, {'s22': [str(root)]}), patch.object(leases, 'local_references', return_value=({}, [])):
        leases.run(args)
    lease = json.loads((path / leases.SIDECAR).read_text())
    assert lease['created_at'] >= before
    assert lease['ttl'] == 604800
    assert path.exists()


def test_legacy_mutation_requires_real_expired_allowlisted_lease(tmp_path):
    reaper = leases.backend()
    root, path, _ = artifact(tmp_path, kind='worktree')
    # Caller-supplied --root does not widen the actor's fixed allowlist.
    assert not reaper.lease_allows_reaping(str(path), time.time())
    (path / leases.SIDECAR).unlink()
    assert not reaper.lease_allows_reaping(str(path), time.time())


def test_omp_owner_marker_protects_parked_live_task(tmp_path):
    import os
    root, path, _ = artifact(tmp_path)
    leases.atomic_json(path / '.omp-isolation-owner.json', {'pid': os.getpid(), 'id': 'parked'})
    assert not inspect(root, path)['eligible']


def test_omp_unknown_owner_and_retained_mount_are_kept(tmp_path):
    root, path, _ = artifact(tmp_path)
    (path / '.omp-isolation-owner.json').write_text('{broken')
    assert not inspect(root, path)['eligible']
    (path / '.omp-isolation-owner.json').unlink()
    (path / '.omp-retained-backend.json').write_text('{\"backend\": 1}')
    assert not inspect(root, path)['eligible']


def test_report_never_scans_home_or_descendants(tmp_path):
    root, path, _ = artifact(tmp_path)
    args = argparse.Namespace(node='s22', output=str(tmp_path / 'report'), enroll=False, apply=False)
    with patch.dict(leases.ROOTS, {'s22': [str(root)]}), \
            patch.object(leases, 'local_references', side_effect=AssertionError('HOME scan')), \
            patch.object(leases, 'size_bytes', side_effect=AssertionError('deep traversal')):
        leases.run(args)
    report = json.loads((tmp_path / 'report/report.json').read_text())
    assert report['unknown_size_count'] == 1
    assert report['items'][0]['bytes'] is None
    assert report['items'][0]['live'] == 'UNKNOWN'
    assert not report['items'][0]['eligible']
    assert (tmp_path / 'report/items/0.json').exists()


def test_approved_worktree_lease_scopes_identity_and_rejects_forgery(tmp_path):
    import subprocess
    root = tmp_path / 'explicitly-approved'
    root.mkdir()
    def git(*args):
        return subprocess.run(['git', '-C', str(root), *args],
                              check=True, capture_output=True)
    git('init')
    git('config', 'user.email', 'test@example.invalid')
    git('config', 'user.name', 'Test')
    (root / 'tracked').write_text('original')
    git('add', '.')
    git('commit', '-m', 'initial')
    (root / '.gitignore').write_text('private\n')
    (root / 'private').write_text('ignored but valuable')
    reaper = leases.backend()
    before = reaper.inspect(str(root), [str(tmp_path)], {}, time.time())
    with patch.object(leases, 'APPROVALS', tmp_path / 'approval-receipts'):
        lease = leases.enroll_approved_worktree(
            root, 'test-owner', 'explicit test approval', reaper)
        assert lease['action'] == 'archive-then-remove'
        assert leases.validate(lease, root, 'groot', time.time()) is None
        assert leases.worktree_lease_allows(root, reaper, time.time())
        after = reaper.inspect(str(root), [str(tmp_path)], {}, time.time())
        assert after['dirty_count'] == before['dirty_count']
        assert after['untracked_count'] == before['untracked_count']
        assert after['mtime_timestamp'] == before['mtime_timestamp']
        (root / 'private').write_text('changed ignored file')
        assert not leases.worktree_lease_allows(root, reaper, time.time())
        (root / 'private').write_text('ignored but valuable')
        assert leases.worktree_lease_allows(root, reaper, time.time())
        forged = {**lease, 'owner': 'someone else'}
        leases.atomic_json(root / leases.SIDECAR, forged)
        assert not leases.worktree_lease_allows(root, reaper, time.time())


def test_approval_enrollment_rejects_symlink_target(tmp_path):
    import pytest
    root = tmp_path / 'real'
    root.mkdir()
    alias = tmp_path / 'alias'
    alias.symlink_to(root, target_is_directory=True)
    with pytest.raises(ValueError):
        leases.enroll_approved_worktree(alias, 'owner', 'approval', leases.backend())
