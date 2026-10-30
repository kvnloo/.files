import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]


def module(name):
    loader = importlib.machinery.SourceFileLoader(name.replace('-', '_'), str(ROOT / 'scripts' / name))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    result = importlib.util.module_from_spec(spec)
    loader.exec_module(result)
    return result


class VaultScopes(unittest.TestCase):
    def test_allowlist_and_bootstrap_token_not_in_consumer(self):
        exe = module('bws-env-exec')
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'map.json'
            config.write_text(json.dumps({'scopes': {'omp': {'TYPESAFE_API_KEY': 'TYPE'}}}))
            with mock.patch.object(exe, 'vault', return_value={'TYPE': 'fixture', 'UNRELATED': 'private'}), \
                 mock.patch.dict(os.environ, {'BWS_ACCESS_TOKEN': 'bootstrap-fixture'}, clear=True), \
                 mock.patch('sys.argv', ['bws-env-exec', '--scope', 'omp', '--config', str(config), '--', 'consumer']), \
                 mock.patch.object(os, 'execvpe') as execute:
                exe.main()
            name, command, env = execute.call_args.args
            self.assertEqual((name, command), ('consumer', ['consumer']))
            self.assertEqual(env, {'TYPESAFE_API_KEY': 'fixture'})

    def test_missing_required_secret_fails_closed(self):
        exe = module('bws-env-exec')
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'map.json'
            config.write_text(json.dumps({'scopes': {'omp': {'TYPESAFE_API_KEY': 'TYPE'}}}))
            with mock.patch.object(exe, 'vault', return_value={}), \
                 mock.patch('sys.argv', ['bws-env-exec', '--scope', 'omp', '--config', str(config), '--', 'consumer']), \
                 mock.patch.object(os, 'execvpe') as execute:
                with self.assertRaises(RuntimeError):
                    exe.main()
                execute.assert_not_called()

    def test_runtime_modes_and_escaping(self):
        exe = module('bws-env-exec')
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'map.json'
            config.write_text(json.dumps({'scopes': {'omp': {'KEY': 'TYPE'}}}))
            with mock.patch.object(exe, 'vault', return_value={'TYPE': 'fixture"\\value'}), \
                 mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}), \
                 mock.patch('sys.argv', ['bws-env-exec', '--refresh', '--config', str(config)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                exe.main()
            runtime = Path(directory) / 'bws-secrets'
            self.assertEqual(runtime.stat().st_mode & 0o777, 0o700)
            self.assertEqual((runtime / 'omp.env').stat().st_mode & 0o777, 0o600)
            self.assertEqual((runtime / 'omp.env').read_text(), 'KEY="fixture\\"\\\\value"\n')

    def test_headless_launch_uses_selected_profile_cache_without_keyring(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / 'bws-secrets'
            runtime.mkdir(mode=0o700)
            cache = runtime / 'hermes-clean.env'
            cache.write_text('ANTHROPIC_TOKEN="clean-fixture"\nUNRELATED="not-allowed"\n')
            cache.chmod(0o600)
            config = root / 'map.json'
            config.write_text(json.dumps({'scopes': {
                'hermes-clean': {'ANTHROPIC_TOKEN': 'CLEAN_TOKEN'},
                'hermes-root': {'ANTHROPIC_TOKEN': 'ROOT_TOKEN'},
            }}))
            marker = root / 'keyring-called'
            bootstrap = root / 'bootstrap'
            bootstrap.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            bootstrap.chmod(0o700)
            env = dict(os.environ, XDG_RUNTIME_DIR=directory,
                       HERMES_HOME=str(root / 'profiles/clean'),
                       HERMES_KEYRING_BOOTSTRAP=str(bootstrap),
                       BWS_ACCESS_TOKEN='must-not-reach-consumer')
            env.pop('UNRELATED', None)
            consumer = (
                'import os,sys; sys.exit(0 if '
                'os.environ.get("ANTHROPIC_TOKEN") == "clean-fixture" and '
                '"BWS_ACCESS_TOKEN" not in os.environ and '
                '"UNRELATED" not in os.environ else 23)'
            )
            result = subprocess.run(
                [sys.executable, str(ROOT / 'scripts/bws-env-exec'),
                 '--scope', 'hermes', '--config', str(config), '--',
                 sys.executable, '-c', consumer],
                env=env, capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(marker.exists())
            self.assertNotIn('clean-fixture', result.stdout + result.stderr)

    def test_cache_round_trip_preserves_literal_secret_characters(self):
        exe = module('bws-env-exec')
        secret = 'space "quote" \\\\ $dollar `literal` #hash'
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / 'map.json'
            mappings = {'KEY': 'VAULT_KEY'}
            config.write_text(json.dumps({'scopes': {'fixture': mappings}}))
            with mock.patch.object(exe, 'vault', return_value={'VAULT_KEY': secret}), \
                 mock.patch.dict(os.environ, {'XDG_RUNTIME_DIR': directory}, clear=True), \
                 mock.patch('sys.argv', ['bws-env-exec', '--refresh', '--config', str(config)]), \
                 contextlib.redirect_stdout(io.StringIO()):
                exe.main()
            self.assertEqual(exe.cached_values({'XDG_RUNTIME_DIR': directory}, 'fixture', mappings),
                             {'VAULT_KEY': secret})

    def test_unsafe_or_incomplete_cache_fails_closed(self):
        exe = module('bws-env-exec')
        for fault in ('directory-mode', 'file-mode', 'symlink', 'missing-key', 'duplicate-key'):
            with self.subTest(fault=fault), tempfile.TemporaryDirectory() as directory:
                runtime = Path(directory) / 'bws-secrets'
                runtime.mkdir(mode=0o700)
                cache = runtime / 'fixture.env'
                cache.write_text('KEY="fixture"\n')
                cache.chmod(0o600)
                if fault == 'directory-mode':
                    runtime.chmod(0o755)
                elif fault == 'file-mode':
                    cache.chmod(0o644)
                elif fault == 'symlink':
                    target = runtime / 'other.env'
                    cache.rename(target)
                    cache.symlink_to(target)
                elif fault == 'missing-key':
                    cache.write_text('OTHER="fixture"\n')
                else:
                    cache.write_text('KEY="fixture"\nKEY="second"\n')
                with self.assertRaises((RuntimeError, OSError)):
                    exe.cached_values({'XDG_RUNTIME_DIR': directory}, 'fixture', {'KEY': 'VAULT_KEY'})

    def test_migration_preserves_nonsecret_and_backup_is_private(self):
        installer = module('install-bws-secrets')
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            source = home / '.config/environment.d/typesafe.conf'
            source.parent.mkdir(parents=True)
            source.write_text('# keep\nTYPESAFE_API_KEY=fixture\nNONSECRET=value\n')
            plan = installer.migration_plan(home, {}, {'TYPESAFE_API_KEY': 'fixture'})
            backup = home / 'backup'
            backup.mkdir(mode=0o700)
            with contextlib.redirect_stdout(io.StringIO()):
                installer.apply_migration(home, plan, backup)
            self.assertEqual(source.read_text(), '# keep\nNONSECRET=value\n')
            saved = backup / source.relative_to(home)
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            self.assertIn('TYPESAFE_API_KEY=fixture', saved.read_text())

    def test_migration_mismatch_never_removes_original(self):
        installer = module('install-bws-secrets')
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            source = home / '.omp/.env'
            source.parent.mkdir(parents=True)
            source.write_text('TYPESAFE_API_KEY=fixture\n')
            with self.assertRaises(RuntimeError):
                installer.migration_plan(home, {}, {'TYPESAFE_API_KEY': 'different-fixture'})
            self.assertEqual(source.read_text(), 'TYPESAFE_API_KEY=fixture\n')

    def test_retired_snapshot_moves_to_private_backup(self):
        installer = module('install-bws-secrets')
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            source = home / '.config/retired.env'
            source.parent.mkdir(parents=True)
            source.write_bytes(b'fixture-secret')
            backup = home / 'backup'
            backup.mkdir(mode=0o700)
            with contextlib.redirect_stdout(io.StringIO()):
                installer.quarantine_files(home, [source], backup)
            self.assertFalse(source.exists())
            saved = backup / '.config/retired.env'
            self.assertEqual(saved.read_bytes(), b'fixture-secret')
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)

    def test_vault_keeps_secret_values_out_of_process_arguments(self):
        exe = module('bws-env-exec')
        responses = [
            mock.Mock(stdout='export BWS_ACCESS_TOKEN=bootstrap-fixture\n'),
            mock.Mock(stdout=json.dumps([{'key': 'TYPE', 'value': 'credential-fixture'}])),
        ]
        with mock.patch.object(exe.subprocess, 'run', side_effect=responses) as run:
            self.assertEqual(exe.vault({}), {'TYPE': 'credential-fixture'})
        for call in run.call_args_list:
            self.assertNotIn('bootstrap-fixture', ' '.join(call.args[0]))
            self.assertNotIn('credential-fixture', ' '.join(call.args[0]))
        self.assertEqual(run.call_args_list[1].kwargs['env']['BWS_ACCESS_TOKEN'], 'bootstrap-fixture')

    def test_retired_dotenv_and_provider_json_preserve_other_settings(self):
        installer = module('install-bws-secrets')
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            dotenv = home / '.omp/agent/.env'
            dotenv.parent.mkdir(parents=True)
            dotenv.write_text('API_KEY=fixture\nOTHER=value\n')
            native = home / '.config/codexbar/config.json'
            native.parent.mkdir(parents=True)
            native.write_text(json.dumps({'providers': [{'id': 'openrouter', 'enabled': True, 'apiKey': 'fixture'}]}))
            values = {'API_KEY': 'fixture'}
            plan = installer.migration_plan(home, {}, values, {'.omp/agent/.env': {'API_KEY': 'API_KEY'}})
            plan += installer.provider_json_plan(home, {'.config/codexbar/config.json': {'openrouter': {'apiKey': 'API_KEY'}}}, values)
            backup = home / 'backup'
            backup.mkdir(mode=0o700)
            with contextlib.redirect_stdout(io.StringIO()):
                installer.apply_migration(home, plan, backup)
            self.assertEqual(dotenv.read_text(), 'OTHER=value\n')
            self.assertEqual(json.loads(native.read_text()), {'providers': [{'id': 'openrouter', 'enabled': True}]})

    def test_render_is_exact_secret_free_and_never_accesses_vault(self):
        import subprocess
        import sys
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'config').mkdir()
            (root / 'config/bws-consumers.json').write_text(json.dumps({
                'units': {'fixture.service': 'fixture'},
                'scopes': {'fixture': {'TYPESAFE_API_KEY': 'fixture-secret-not-for-output'}},
            }))
            marker = root / 'forbidden-vault-access'
            forbidden = root / 'forbidden'
            forbidden.write_text('#!/bin/sh\ntouch "' + str(marker) + '"\nexit 99\n')
            forbidden.chmod(0o700)
            env = dict(os.environ, BWS_BIN=str(forbidden), HERMES_KEYRING_BOOTSTRAP=str(forbidden),
                       TYPESAFE_API_KEY='fixture-secret-not-for-output')
            result = subprocess.run([sys.executable, str(ROOT / 'scripts/install-bws-secrets'),
                                     '--source', str(root), '--render', 'fixture.service'],
                                    env=env, capture_output=True, text=True, check=False)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout, '[Unit]\nRequires=bws-secrets-sync.service\nAfter=bws-secrets-sync.service\n\n'
                             '[Service]\nEnvironmentFile=%t/bws-secrets/fixture.env\n')
            self.assertNotIn('fixture-secret-not-for-output', result.stdout + result.stderr)
            self.assertFalse(marker.exists())


if __name__ == '__main__':
    unittest.main()
