#!/usr/bin/env bash
# Put the Proton Pass session behind sudo.
#
#   sudo scripts/passvault-install.sh            # install
#   sudo scripts/passvault-install.sh --uninstall
#
# The session and its encryption key live in /var/lib/passvault (mode 700, owned
# by the `passvault` system user), so nothing running as the login user can read
# them. The only way in is `sudo -u passvault pass-cli-run`, and the sudoers rule
# makes sudo ask for the password on every call (no cached timestamp).
# After install, log in once with: pass-cli login
set -euo pipefail

user=passvault
home=/var/lib/passvault
libdir=/usr/local/lib/proton-pass
runner=$libdir/pass-cli-run
sudoers=/etc/sudoers.d/50-passvault
login_user=${SUDO_USER:-}

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
[[ -n "$login_user" && "$login_user" != root ]] || { echo "run with sudo from your login user" >&2; exit 1; }

if [[ "${1:-}" == "--uninstall" ]]; then
  rm -f "$sudoers" "$runner" "$libdir/pass-cli"
  echo "removed sudoers rule and runner; $home and user $user kept (delete by hand: userdel -r $user)"
  exit 0
fi

src=${PASS_CLI_BIN:-$(getent passwd "$login_user" | cut -d: -f6)/.local/lib/proton-pass/pass-cli}
[[ -x "$src" ]] || src=/usr/bin/pass-cli
[[ -x "$src" ]] || { echo "no pass-cli binary found; set PASS_CLI_BIN" >&2; exit 1; }

id "$user" >/dev/null 2>&1 || useradd --system --home-dir "$home" --no-create-home --shell /usr/bin/nologin "$user"
install -d -o "$user" -g "$user" -m 700 "$home"

# Root-owned copy, so the login user cannot swap the binary that runs as passvault.
install -d -o root -g root -m 755 "$libdir"
install -o root -g root -m 755 "$src" "$libdir/pass-cli"

cat >"$runner" <<EOF
#!/bin/sh
# Runs as $user via sudo. sudo has already reset the environment.
export HOME=$home
export PROTON_PASS_SESSION_DIR=$home/session
export PROTON_PASS_KEY_PROVIDER=fs
export PROTON_PASS_NO_UPDATE_CHECK=1
export PROTON_PASS_DISABLE_TELEMETRY=1
cd $home
exec $libdir/pass-cli "\$@"
EOF
chown root:root "$runner"
chmod 755 "$runner"

tmp=$(mktemp)
cat >"$tmp" <<EOF
# Proton Pass vault: $login_user may run pass-cli as $user, password every time.
Defaults!$runner timestamp_timeout=0
$login_user ALL=($user) $runner
EOF
visudo -cf "$tmp" >/dev/null
install -o root -g root -m 440 "$tmp" "$sudoers"
rm -f "$tmp"

echo "installed. Next, as $login_user: pass-cli login   (sudo asks for your password)"
