#!/usr/bin/env bash
# Extract the official verifier only inside a caller-owned destination.
set -euo pipefail
[ "$(uname -s)-$(uname -m)" = Linux-x86_64 ] || {
  echo 'fleet admission verifier requires Linux x86_64 (including the Linux MBP)' >&2
  exit 1
}
root=$(realpath -m "${1:?usage: bootstrap.sh OWNED_DESTINATION}")
mkdir -p "$root/downloads"
bend=${BEND_ARCHIVE:-$root/downloads/bend-2.0.34-linux-x64.tar.gz}
lean=${LEAN_ARCHIVE:-$root/downloads/lean-4.34.0-linux.tar.zst}
if [ ! -f "$bend" ]; then
  curl --fail --location --max-time 180 --max-filesize 40000000 --output "$bend" \
    https://github.com/bendlang/bend/releases/download/v2.0.34/bend-2.0.34-linux-x64.tar.gz
fi
if [ ! -f "$lean" ]; then
  curl --fail --location --max-time 600 --max-filesize 600000000 --output "$lean" \
    https://github.com/leanprover/lean4/releases/download/v4.34.0/lean-4.34.0-linux.tar.zst
fi
printf '%s  %s\n' 78106a97af242429dcc057258eb8d10f69cddebcd5e263022185a52d003e09bf "$bend" | sha256sum --check --strict -
printf '%s  %s\n' caaa98356098c85dc0fcbbd28e1ec66f39eb6551829972b752ff20e1286b646b "$lean" | sha256sum --check --strict -
tar -xzf "$bend" -C "$root"
tar --zstd -xf "$lean" -C "$root"
printf 'BEND=%s/bend/bin/bend\nLEAN_BIN=%s/lean-4.34.0-linux/bin\n' "$root" "$root"
