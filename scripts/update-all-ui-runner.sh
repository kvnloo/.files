#!/usr/bin/env bash
set -u

state_dir=${XDG_RUNTIME_DIR:-/tmp}/reforge-groot
log_file=$state_dir/update.log
mkdir -p "$state_dir"
rm -f "$state_dir"/*.status "$log_file"
printf 'running\n' >"$state_dir/overall.status"

status() {
  printf '%s\n' "$2" >"$state_dir/$1.status"
}

log() {
  printf '[%(%H:%M:%S)T] [%s] %s\n' -1 "$1" "$2" | tee -a "$log_file"
}

run_command() {
  local lane=$1 label=$2
  shift 2
  log "$lane" "$label"
  "$@" > >(while IFS= read -r line; do log "$lane" "$line"; done) \
       2> >(while IFS= read -r line; do log "$lane" "$line"; done >&2)
}

lane_system() {
  status system running
  if command -v paru >/dev/null 2>&1; then
    run_command system 'Updating official repositories and AUR' paru -Syu
  elif command -v yay >/dev/null 2>&1; then
    run_command system 'Updating official repositories and AUR' yay -Syu
  else
    run_command system 'Updating official repositories' sudo pacman -Syu
  fi
  local result=$?
  status system "$([[ $result -eq 0 ]] && echo success || echo failed)"
  return "$result"
}

lane_flatpak() {
  status flatpak running
  if command -v flatpak >/dev/null 2>&1; then
    run_command flatpak 'Updating Flatpak applications' flatpak update -y
    local result=$?
    status flatpak "$([[ $result -eq 0 ]] && echo success || echo failed)"
    return "$result"
  fi
  status flatpak skipped
}

lane_firmware() {
  status firmware running
  if command -v fwupdmgr >/dev/null 2>&1; then
    run_command firmware 'Refreshing firmware metadata' fwupdmgr refresh --force
    run_command firmware 'Applying firmware updates' fwupdmgr update -y
    local result=$?
    status firmware "$([[ $result -eq 0 ]] && echo success || echo failed)"
    return "$result"
  fi
  status firmware skipped
}

lane_rust() {
  status rust running
  local result=0
  if command -v rustup >/dev/null 2>&1; then
    run_command rust 'Updating Rust toolchains' rustup update || result=$?
  fi
  if command -v cargo >/dev/null 2>&1 && cargo install-update --version >/dev/null 2>&1; then
    run_command rust 'Updating Cargo-installed applications' cargo install-update -a || result=$?
  fi
  status rust "$([[ $result -eq 0 ]] && echo success || echo failed)"
  return "$result"
}

lane_python() {
  status python running
  if command -v pipx >/dev/null 2>&1; then
    run_command python 'Updating pipx applications' pipx upgrade-all
    local result=$?
    status python "$([[ $result -eq 0 ]] && echo success || echo failed)"
    return "$result"
  fi
  status python skipped
}

lane_node() {
  status node running
  if command -v npm >/dev/null 2>&1; then
    local npm_prefix
    npm_prefix=$(npm config get prefix 2>/dev/null)
    if [[ -n $npm_prefix && -w $npm_prefix/lib/node_modules ]]; then
      run_command node 'Updating global npm packages' npm update -g
      local result=$?
      status node "$([[ $result -eq 0 ]] && echo success || echo failed)"
      return "$result"
    fi
    log node "Skipped: npm prefix is not user-writable ($npm_prefix)"
  fi
  status node skipped
}

for lane in system flatpak firmware rust python node; do status "$lane" queued; done

if command -v sudo >/dev/null 2>&1; then
  printf 'Reforge Groot needs authorization before parallel updates begin.\n'
  sudo -v || { status system failed; status firmware skipped; printf 'failed\n' >"$state_dir/overall.status"; exit 1; }
fi

pids=()
for lane in system flatpak firmware rust python node; do
  "lane_$lane" &
  pids+=("$!")
done

result=0
for pid in "${pids[@]}"; do
  wait "$pid" || result=1
done

printf '%s\n' "$([[ $result -eq 0 ]] && echo success || echo failed)" >"$state_dir/overall.status"
log reforge "$([[ $result -eq 0 ]] && echo 'Groot has been reforged.' || echo 'Reforge finished with failures. Expand logs for details.')"
printf '\nUpdates finished. Press Enter to close this terminal.\n'
read -r _
exit "$result"
