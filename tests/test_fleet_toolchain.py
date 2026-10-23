"""Toolchain function tests with temporary prefixes and fake installers only."""
import os
from pathlib import Path
import shlex
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "scripts/fleet-toolchain.sh").read_text().split('\nMODE=${1:-};', 1)[0]


class Toolchain(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.capture = self.root / "installer-calls"

    def call(self, body, mode="check"):
        setup = (f'\nOPT={shlex.quote(str(self.root / "opt"))}\n'
                 f'ENV_FILE={shlex.quote(str(self.root / "toolchain.env"))}\n'
                 f'CAPTURE={shlex.quote(str(self.capture))}\n'
                 f'MODE={mode}\n')
        return subprocess.run(["bash", "-c", SOURCE + setup + body],
                              env={**os.environ, "HOME": str(self.root)}, capture_output=True, text=True)

    def test_bunx_check_never_repairs_missing_native_entry(self):
        result = self.call('''
arch_ok() { :; }
need_archive() { :; }
tc_bun
printf '%s\\n' "${MISSING[@]}"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "bunx")
        self.assertFalse((self.root / "opt/bun/bunx").exists())

    def test_bunx_native_symlink_is_installed_once(self):
        result = self.call('''
arch_ok() { :; }
need_archive() {
  mkdir -p "$OPT/bun"
  printf '#!/bin/sh\\nexit 0\\n' > "$OPT/bun/bun"
  chmod +x "$OPT/bun/bun"
}
tc_bun; tc_bun
printf 'changes=%s\\n' "${#CHANGED[@]}"
''', mode="install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue((self.root / "opt/bun/bunx").is_symlink())
        self.assertEqual(os.readlink(self.root / "opt/bun/bunx"), "bun")
        self.assertIn("changes=1", result.stdout)

    def test_check_missing_pnpm_and_corepack_never_installs(self):
        result = self.call('''
tc_node() { :; }
command() {
  case "$*" in '-v pnpm'|'-v corepack') return 1 ;; esac
  builtin command "$@"
}
npm() { echo UNEXPECTED_INSTALL; exit 99; }
tc_corepack; tc_pnpm; write_env
printf '%s\\n' "${MISSING[@]}"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.splitlines(), ["corepack", "pnpm"])
        self.assertFalse((self.root / "toolchain.env").exists())

    def test_distro_install_reuses_arch_patterns_without_upgrade(self):
        result = self.call('''
pacman() { printf '%s\\n' "$*" > "$CAPTURE"; }
distro_install nodejs npm
''', mode="install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.capture.read_text().strip(), "-S --needed --noconfirm nodejs npm")

    def test_debian_install_does_not_refresh_database(self):
        result = self.call('''
command() {
  if [ "$*" = '-v pacman' ]; then return 1; fi
  builtin command "$@"
}
apt-get() { printf '%s\\n' "$*" > "$CAPTURE"; }
distro_install rustup
''', mode="install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.capture.read_text().strip(), "install -y rustup")

    def test_npm_prefixes_are_separate_and_installs_are_idempotent(self):
        result = self.call('''
tc_node() { :; }
command() {
  case "$*" in '-v pnpm'|'-v corepack') return 1 ;; esac
  builtin command "$@"
}
npm() {
  printf '%s\\n' "$*" >> "$CAPTURE"
  local tool=${!#}; tool=${tool%@*}
  mkdir -p "$4/bin"
  printf '#!/bin/sh\\nexit 0\\n' > "$4/bin/$tool"
  chmod +x "$4/bin/$tool"
}
tc_corepack; tc_pnpm; tc_corepack; tc_pnpm
write_env
''', mode="install")
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.capture.read_text().splitlines()
        self.assertEqual(len(calls), 2)
        for name, call in zip(("corepack", "pnpm"), calls):
            self.assertIn(f"--prefix {self.root / 'opt' / name}", call)
            self.assertIn("--ignore-scripts --engine-strict", call)
            self.assertIn("--no-audit --no-fund", call)
        self.assertTrue((self.root / "opt/corepack/bin/corepack").is_file())
        self.assertTrue((self.root / "opt/pnpm/bin/pnpm").is_file())
        env = (self.root / "toolchain.env").read_text()
        self.assertIn("/opt/fleet/corepack/bin", env)
        self.assertIn("/opt/fleet/pnpm/bin", env)
        self.assertIn("/opt/fleet/rust/current/bin", env)
        self.assertIn("export CARGO_HOME=$HOME/.cargo", env)
        self.assertNotIn("PATH=$HOME/.cargo/bin", env)
        self.assertNotIn("/home/kvn", env)

    def test_rust_check_missing_binaries_is_report_only(self):
        result = self.call('''
distro_install() { echo UNEXPECTED_INSTALL; exit 99; }
tc_rust
printf '%s\\n' "${MISSING[@]}"
''')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rust:cargo/rustc")

    def rust_binary(self, name, status=0):
        path = self.root / "opt/rust/current/bin" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(f"#!/bin/sh\nexit {status}\n")
        path.chmod(0o755)

    def test_rust_check_requires_both_actual_binaries(self):
        self.rust_binary("cargo")
        result = self.call('tc_rust; printf "%s\\\\n" "${MISSING[@]}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rust:cargo/rustc")

    def test_rust_check_rejects_nonworking_compiler(self):
        self.rust_binary("cargo")
        self.rust_binary("rustc", status=1)
        result = self.call('tc_rust; printf "%s\\\\n" "${MISSING[@]}"')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "rust:cargo/rustc")

    def test_rust_keeps_healthy_managed_install(self):
        self.rust_binary("cargo")
        self.rust_binary("rustc")
        result = self.call('''
distro_install() { echo UNEXPECTED_INSTALL; exit 99; }
tc_rust
[ "${#CHANGED[@]}" -eq 0 ]
[ "${#MISSING[@]}" -eq 0 ]
''', mode="install")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout, "")

    def test_rust_installer_uses_only_trusted_system_rustup(self):
        start = SOURCE.index("tc_rust() {")
        end = SOURCE.index("tc_android_sdk() {", start)
        installer = SOURCE[start:end]
        self.assertIn("/usr/bin/rustup toolchain install stable --profile minimal --no-self-update", installer)
        self.assertIn('RUSTUP_HOME="$root/rustup"', installer)
        self.assertIn('CARGO_HOME="$root/installer-cargo"', installer)
        self.assertIn('chown -R root:root "$root"', installer)
        self.assertIn('chmod -R a+rX,go-w "$root"', installer)
        self.assertNotIn("$HOME/.cargo/bin", installer)
        self.assertNotIn("/home/kvn", installer)


if __name__ == "__main__":
    unittest.main()
