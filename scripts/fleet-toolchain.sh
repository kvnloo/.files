#!/usr/bin/env bash
# Install build toolchains on a Linux fleet worker so host-lane jobs (`fleet run`,
# `fleet-build`) can build our stacks there instead of on groot. Idempotent: a
# package or SDK component is installed only when it is missing, the env file is
# written only when it changes, and a run with nothing to do prints "no changes".
# Run as root ON the node (`scripts/fleet toolchain <node>` copies and runs it).
#
#   fleet-toolchain.sh install TOOLCHAIN...     jdk17 jdk21 bun android-sdk corepack pnpm rust
#   fleet-toolchain.sh check   TOOLCHAIN...     report only, exit 1 if anything is missing
#
# What it puts where (all on the node's own disk, root-owned, read-only for jobs).
# JDK/Bun use pinned release tarballs, not pacman. Node/npm prerequisites use the
# existing distro package manager, never a database refresh or full upgrade.
#   jdk17, jdk21  Eclipse Temurin  /opt/fleet/jdk-17, /opt/fleet/jdk-21  (Adoptium sha256)
#   bun           oven-sh release  /opt/fleet/bun/bun                    (GitHub sha256)
#   android-sdk   /opt/android-sdk: cmdline-tools pinned by Google's own sha1
#                 (repository2-3.xml), then ANDROID_PKGS through sdkmanager
# A pin change (new URL/sha) reinstalls that toolchain; otherwise nothing is touched.
#   corepack,pnpm pinned npm packages in separate /opt/fleet/<name> prefixes;
#                 distro Node/npm if absent; no lifecycle scripts or global shims.
#   rust          distro /usr/bin/rustup installs root-owned /opt/fleet/rust;
#                 jobs use actual compiler binaries, with private writable caches.
#   env           /etc/fleet/toolchain.env, sourced by every Linux `fleet run` job:
#                 JAVA_HOME (17), JAVA17_HOME, JAVA21_HOME, ANDROID_HOME, PATH, and
#                 GRADLE_USER_HOME=$HOME/.gradle (agentjob's home: caches survive jobs)
set -euo pipefail

# Android SDK components our Android repos need. Keep in sync with:
#   noop-oura android/app/build.gradle.kts   compileSdk 35, targetSdk 34, AGP 8.5.2 (build-tools 34)
#   lawnchair build.gradle                   compileSdk release(37) minor 2, buildToolsVersion 37.0.0
ANDROID_PKGS=(
  "platform-tools"
  "platforms;android-34" "platforms;android-35" "platforms;android-37.2"
  "build-tools;34.0.0" "build-tools;35.0.0" "build-tools;37.0.0"
)
SDK=/opt/android-sdk
OPT=/opt/fleet
# name|url|sha256 (x86_64). Bump url and sha together.
JDK17_PIN="https://github.com/adoptium/temurin17-binaries/releases/download/jdk-17.0.20.1%2B1/OpenJDK17U-jdk_x64_linux_hotspot_17.0.20.1_1.tar.gz|3808d1d15e3ec6bd5b84057fb5d84c33d8a1536a258146bcea2e603fc726e08e"
JDK21_PIN="https://github.com/adoptium/temurin21-binaries/releases/download/jdk-21.0.12.1%2B1/OpenJDK21U-jdk_x64_linux_hotspot_21.0.12.1_1.tar.gz|ce79869e1307ed8ee1e2baa86a412b1eb5b75d10a01006d788a6f968bcfaee94"
BUN_PIN="https://github.com/oven-sh/bun/releases/download/bun-v1.4.3/bun-linux-x64.zip|3e730528d89775f03f87f05c06787c4df4099d0a37f3f252e7b829cb23816e18"
CMDLINE_URL=https://dl.google.com/android/repository/commandlinetools-linux-16111833_latest.zip   # cmdline-tools 23.0
CMDLINE_SHA1=e025545c62a8e64c7559119566a569fb1dec5f60
ENV_FILE=/etc/fleet/toolchain.env
# Corepack 0.33.0 is already used by this repo's npm-global inventory. Separate
# prefixes avoid Corepack's bundled pnpm shim overwriting the standalone pnpm.
COREPACK_VERSION=0.33.0
PNPM_VERSION=10.11.0

CHANGED=(); MISSING=()
die() { echo "fleet-toolchain: $*" >&2; exit 1; }
say() { echo "==> $*"; }

pkg_dir() { echo "$SDK/${1//;//}"; }      # "build-tools;34.0.0" -> $SDK/build-tools/34.0.0

# need_archive <toolchain> <dest dir> <url|sha256> <check binary, relative to dest>
need_archive() {
  local tc=$1 dest=$2 url=${3%%|*} sha=${3##*|} bin=$4 tmp
  if [ -x "$dest/$bin" ] && [ "$(cat "$dest/.fleet-pin" 2>/dev/null)" = "$sha" ]; then return 0; fi
  if [ "$MODE" = check ]; then MISSING+=("$tc"); return 0; fi
  tmp=$(mktemp -d)
  curl -fsSL --retry 3 -o "$tmp/a" "$url"
  echo "$sha  $tmp/a" | sha256sum -c --quiet - || { rm -rf "$tmp"; die "$tc checksum mismatch"; }
  mkdir "$tmp/x"
  case $url in
    *.zip) unzip -q "$tmp/a" -d "$tmp/x" ;;
    *) tar -xzf "$tmp/a" -C "$tmp/x" ;;
  esac
  # Archives hold one top directory (jdk-17.0.20.1+1/, bun-linux-x64/): that becomes $dest.
  install -d -m 0755 "$(dirname "$dest")"
  rm -rf "$dest.new"; mv "$tmp/x"/* "$dest.new"
  echo "$sha" >"$dest.new/.fleet-pin"
  chmod -R a+rX,go-w "$dest.new"
  rm -rf "$dest"; mv "$dest.new" "$dest"; rm -rf "$tmp"
  "$dest/$bin" --version >/dev/null 2>&1 || "$dest/$bin" -version >/dev/null 2>&1 || die "$tc: $dest/$bin does not run"
  CHANGED+=("$tc"); say "installed $tc in $dest"
}

arch_ok() { [ "$(uname -m)" = x86_64 ] || die "pins are x86_64 only; add $(uname -m) pins first"; }
tc_jdk17() { arch_ok; need_archive jdk17 "$OPT/jdk-17" "$JDK17_PIN" bin/java; }
tc_jdk21() { arch_ok; need_archive jdk21 "$OPT/jdk-21" "$JDK21_PIN" bin/java; }
tc_bun()   { arch_ok; need_archive bun "$OPT/bun" "$BUN_PIN" bun; }

distro_install() {
  # No sync-database refresh, full upgrade, curl-to-shell or privileged AUR helper.
  if command -v pacman >/dev/null 2>&1; then
    pacman -S --needed --noconfirm "$@"
  elif command -v apt-get >/dev/null 2>&1; then
    apt-get install -y "$@"
  elif command -v dnf >/dev/null 2>&1; then
    dnf install -y "$@"
  elif command -v yum >/dev/null 2>&1; then
    yum install -y "$@"
  else
    die "install distro packages first (no supported package manager): $*"
  fi
}

tc_node() {
  local missing=() bin
  for bin in node npm; do command -v "$bin" >/dev/null 2>&1 || missing+=("$bin"); done
  [ ${#missing[@]} -gt 0 ] || return 0
  if [ "$MODE" = check ]; then MISSING+=("${missing[@]}"); return 0; fi
  # A stale-repository failure needs an owner-planned update, not an implicit Syu.
  distro_install nodejs npm
  for bin in node npm; do command -v "$bin" >/dev/null 2>&1 || die "$bin missing after package installation"; done
  CHANGED+=(node); say "installed distro Node.js/npm prerequisites"
}

need_npm_tool() {
  local tc=$1 version=$2 bin="$OPT/$1/bin/$1"
  tc_node
  # Accept a distro-provided tool; do not replace or upgrade an existing command.
  if command -v "$tc" >/dev/null 2>&1 || [ -x "$bin" ]; then return 0; fi
  if [ "$MODE" = check ]; then MISSING+=("$tc"); return 0; fi
  npm install --global --prefix "$OPT/$tc" --ignore-scripts --engine-strict \
    --no-audit --no-fund "$tc@$version"
  [ -x "$bin" ] || die "$tc: $bin missing after npm installation"
  chmod -R a+rX,go-w "$OPT/$tc"
  CHANGED+=("$tc"); say "installed $tc@$version in $OPT/$tc"
}

tc_corepack() { need_npm_tool corepack "$COREPACK_VERSION"; }
tc_pnpm() { need_npm_tool pnpm "$PNPM_VERSION"; }

rust_present() {
  local bin="$OPT/rust/current/bin"
  [ -x "$bin/cargo" ] && [ -x "$bin/rustc" ] &&
    "$bin/cargo" --version >/dev/null 2>&1 &&
    "$bin/rustc" --version >/dev/null 2>&1
}

tc_rust() {
  local root="$OPT/rust" cargo toolchain
  if rust_present; then return 0; fi
  if [ "$MODE" = check ]; then MISSING+=("rust:cargo/rustc"); return 0; fi
  # Only the trusted distro installer runs as root. Never use owner/agentjob
  # rustup, PATH discovery, their homes, or their installer state.
  if [ ! -x /usr/bin/rustup ]; then
    distro_install rustup
    [ -x /usr/bin/rustup ] || die "distro rustup package did not supply /usr/bin/rustup"
    CHANGED+=(rustup)
  fi
  install -d -m 0755 -o root -g root "$root"
  env -u RUSTUP_TOOLCHAIN CARGO_HOME="$root/installer-cargo" RUSTUP_HOME="$root/rustup" \
    /usr/bin/rustup toolchain install stable --profile minimal --no-self-update
  cargo=$(env -u RUSTUP_TOOLCHAIN CARGO_HOME="$root/installer-cargo" RUSTUP_HOME="$root/rustup" \
    /usr/bin/rustup which --toolchain stable cargo)
  case $cargo in "$root"/rustup/toolchains/*/bin/cargo) ;; *) die "rustup returned an unmanaged cargo path";; esac
  toolchain=${cargo%/bin/cargo}
  [ -x "$cargo" ] && [ -x "$toolchain/bin/rustc" ] || die "Rust installation lacks cargo/rustc"
  ln -sfnT "$toolchain" "$root/current"
  chown -R root:root "$root"
  chmod -R a+rX,go-w "$root"
  rust_present || die "installed cargo/rustc do not run"
  CHANGED+=(rust); say "installed root-owned stable Rust toolchain in $root"
}

tc_android_sdk() {
  local java=$OPT/jdk-17
  [ -x "$java/bin/java" ] || { [ "$MODE" = check ] && { MISSING+=("android-sdk(needs jdk17)"); return 0; }; tc_jdk17; }
  local sm="$SDK/cmdline-tools/latest/bin/sdkmanager" missing=() p
  if [ ! -x "$sm" ]; then
    if [ "$MODE" = check ]; then MISSING+=("android-sdk:cmdline-tools"); else
      local tmp; tmp=$(mktemp -d)
      curl -fsSL --retry 3 -o "$tmp/c.zip" "$CMDLINE_URL"
      echo "$CMDLINE_SHA1  $tmp/c.zip" | sha1sum -c --quiet - || die "cmdline-tools checksum mismatch"
      unzip -q "$tmp/c.zip" -d "$tmp"
      install -d -m 0755 "$SDK/cmdline-tools"
      rm -rf "$SDK/cmdline-tools/latest"; mv "$tmp/cmdline-tools" "$SDK/cmdline-tools/latest"
      rm -rf "$tmp"; CHANGED+=(android-sdk); say "installed cmdline-tools 23.0 in $SDK"
    fi
  fi
  for p in "${ANDROID_PKGS[@]}"; do
    [ -f "$(pkg_dir "$p")/source.properties" ] || missing+=("$p")
  done
  [ ${#missing[@]} -eq 0 ] && return 0
  if [ "$MODE" = check ]; then MISSING+=("${missing[@]/#/android-sdk:}"); return 0; fi
  # Licenses are Google's standard SDK terms; the owner already accepts them on groot.
  yes | JAVA_HOME=$java "$sm" --sdk_root="$SDK" --licenses >/dev/null 2>&1 || true
  JAVA_HOME=$java "$sm" --sdk_root="$SDK" "${missing[@]}" | grep -vE '^\[=*' || true
  for p in "${missing[@]}"; do
    [ -f "$(pkg_dir "$p")/source.properties" ] || die "sdkmanager did not install $p"
  done
  chmod -R a+rX "$SDK"
  CHANGED+=(android-sdk); say "installed ${missing[*]}"
}

write_env() {
  [ "$MODE" = check ] && return 0
  local tmp; tmp=$(mktemp)
  cat >"$tmp" <<'EOF'
# fleet-toolchain: build toolchain for host-lane jobs (scripts/fleet-toolchain.sh).
# Sourced by every Linux `fleet run` job before its command. Only names what exists.
[ -x /opt/fleet/jdk-17/bin/java ] && export JAVA17_HOME=/opt/fleet/jdk-17
[ -x /opt/fleet/jdk-21/bin/java ] && export JAVA21_HOME=/opt/fleet/jdk-21
[ -x /opt/fleet/bun/bun ] && PATH=/opt/fleet/bun:$PATH
[ -d /opt/fleet/corepack/bin ] && PATH=/opt/fleet/corepack/bin:$PATH
[ -d /opt/fleet/pnpm/bin ] && PATH=/opt/fleet/pnpm/bin:$PATH
# Actual root-owned binaries, not rustup proxies or an owner's ~/.cargo/bin.
[ -x /opt/fleet/rust/current/bin/cargo ] && PATH=/opt/fleet/rust/current/bin:$PATH
export CARGO_HOME=$HOME/.cargo
export JAVA_HOME=${FLEET_JAVA_HOME:-${JAVA17_HOME:-${JAVA21_HOME:-}}}
if [ -d /opt/android-sdk/platform-tools ]; then
  export ANDROID_HOME=/opt/android-sdk ANDROID_SDK_ROOT=/opt/android-sdk
  PATH=$ANDROID_HOME/platform-tools:$ANDROID_HOME/cmdline-tools/latest/bin:$PATH
fi
[ -n "$JAVA_HOME" ] && PATH=$JAVA_HOME/bin:$PATH
export PATH
# Gradle/Bun caches live in agentjob's home on this node's disk and outlive each job dir.
export GRADLE_USER_HOME=${GRADLE_USER_HOME:-$HOME/.gradle}
EOF
  if [ -f "$ENV_FILE" ] && cmp -s "$tmp" "$ENV_FILE"; then rm -f "$tmp"; return 0; fi
  install -d -m 0755 "$(dirname "$ENV_FILE")"
  install -m 0644 "$tmp" "$ENV_FILE"; rm -f "$tmp"
  CHANGED+=(env); say "wrote $ENV_FILE"
}

MODE=${1:-}; shift || true
case $MODE in
  install|check) ;;
  *) sed -n '2,19p' "$0"; exit 2 ;;
esac
[ "$(id -u)" -eq 0 ] || [ "$MODE" = check ] || die "run as root"
for t in curl unzip tar sha256sum sha1sum; do command -v $t >/dev/null || die "needs $t"; done
[ $# -gt 0 ] || die "name at least one toolchain"
for tc in "$@"; do
  case $tc in
    jdk17|jdk21|bun|node|corepack|pnpm|rust) "tc_$tc" ;;
    android-sdk) tc_android_sdk ;;
    *) die "unknown toolchain $tc" ;;
  esac
done
write_env
if [ "$MODE" = check ]; then
  if [ ${#MISSING[@]} -eq 0 ]; then say "all present: $*"; else say "missing: ${MISSING[*]}"; exit 1; fi
elif [ ${#CHANGED[@]} -eq 0 ]; then say "no changes"
else say "changed: $(printf '%s\n' "${CHANGED[@]}" | sort -u | paste -sd' ')"; fi
