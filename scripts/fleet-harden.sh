#!/usr/bin/env bash
# Harden a fleet node so it can take work permanently. Idempotent: every file is
# written only when its content changes, and a service is reloaded/restarted only
# when one of its files changed. Never reboots. Run as root ON the node.
#
#   fleet-harden.sh worker --controller-ip IP --controller-key PUBKEY_FILE [opts]
#   fleet-harden.sh server [--restart-k3s] [opts]          (groot; owner runs with sudo)
#   fleet-harden.sh plan worker|server [opts]              render into a temp dir, change nothing
#
# opts (written by `scripts/fleet enroll` from config/fleet/nodes.yaml):
#   --kubelet-arg K=V        repeatable; appended to the k3s kubelet args (last wins)
#   --lane-mem-max 4G --lane-cpu-quota 600% --lane-tasks-max 4096   (worker only)
#
# What it sets (see docs/fleet/README.md for the why):
#   journald   persistent, 500M cap, 2G keep-free, 1 month retention
#   sshd       key-only, no root password, short grace, agentjob keys root-owned
#   ufw        ssh 2222 on tailscale0 from the controller only; k3s ports tailnet only
#   k3s        Restart=always, no start limit, OOMScoreAdjust=-900, kubelet reservations
#   logind     laptops: lid close on AC does not suspend
#   agentjob   unprivileged user for host jobs, capped user slice, no LAN/tailnet egress
#   updates    daily `checkupdates -d` (download only) -> /var/lib/fleet/updates.json
#   probe      /usr/local/bin/fleet-node-probe (read by `fleet health` on groot)
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ROOT=""            # set by `plan`: write into this dir, run no system commands
CHANGED=()         # names of changed components
MODE=""; CTRL_IP=""; CTRL_KEY=""; RESTART_K3S=0
KUBELET_ARGS=(); LANE_MEM_MAX=4G; LANE_CPU=600%; LANE_TASKS=4096
LANE_USER=agentjob

die() { echo "fleet-harden: $*" >&2; exit 1; }
say() { echo "==> $*"; }
sys() { [ -z "$ROOT" ] && "$@"; return 0; }   # run a system command unless planning

# put <component> <path> <mode> : stdin is the content; prints nothing, records change.
put() {
  local comp=$1 path=$2 mode=$3 tmp dst
  dst="$ROOT$path"; tmp=$(mktemp)
  cat >"$tmp"
  if [ -f "$dst" ] && cmp -s "$tmp" "$dst"; then rm -f "$tmp"; return 0; fi
  install -d -m 0755 "$(dirname "$dst")"
  install -m "$mode" "$tmp" "$dst"; rm -f "$tmp"
  CHANGED+=("$comp"); say "wrote $path"
}
changed() { local c; for c in "${CHANGED[@]:-}"; do [ "$c" = "$1" ] && return 0; done; return 1; }

parse() {
  while [ $# -gt 0 ]; do
    case $1 in
      --controller-ip) CTRL_IP=$2; shift 2 ;;
      --controller-key) CTRL_KEY=$2; shift 2 ;;
      --kubelet-arg) KUBELET_ARGS+=("$2"); shift 2 ;;
      --lane-mem-max) LANE_MEM_MAX=$2; shift 2 ;;
      --lane-cpu-quota) LANE_CPU=$2; shift 2 ;;
      --lane-tasks-max) LANE_TASKS=$2; shift 2 ;;
      --restart-k3s) RESTART_K3S=1; shift ;;
      *) die "unknown option $1" ;;
    esac
  done
}

k3s_unit() { if [ "$MODE" = server ]; then echo k3s; else echo k3s-agent; fi; }

step_journald() {
  put journald /etc/systemd/journald.conf.d/50-fleet.conf 0644 <<'EOF'
# fleet-harden: keep logs across reboots, bounded.
[Journal]
Storage=persistent
SystemMaxUse=500M
SystemKeepFree=2G
MaxRetentionSec=1month
EOF
  if changed journald; then sys install -d -m 2755 -g systemd-journal /var/log/journal; sys systemctl restart systemd-journald; fi
}

step_sshd() {
  local authkeys=/etc/ssh/sshd_config.d/50-tailnet-keys.conf bak
  bak=$(mktemp -d); [ -z "$ROOT" ] && cp -a /etc/ssh/sshd_config.d "$bak/"
  if [ "$MODE" = worker ]; then
    put sshd $authkeys 0644 <<'EOF'
# fleet-harden: key-only OpenSSH. Port 2222 is opened by ufw on tailscale0 for
# the controller (groot) only; Tailscale SSH owns tailnet :22 for interactive use.
Port 22
Port 2222
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
AuthenticationMethods publickey
MaxAuthTries 3
LoginGraceTime 20
MaxStartups 10:30:60
ClientAliveInterval 60
ClientAliveCountMax 3
X11Forwarding no
# Host-lane jobs: keys live in a root-owned file the job cannot edit.
Match User agentjob
    AuthorizedKeysFile /etc/ssh/fleet_authorized_keys/%u
    AllowTcpForwarding no
    AllowStreamLocalForwarding no
    AllowAgentForwarding no
    PermitTunnel no
    PermitTTY no
EOF
    [ -n "$ROOT" ] || [ -r "$CTRL_KEY" ] || die "--controller-key file missing"
    local key; key=$(awk 'NF>=2{print $1" "$2; exit}' "${CTRL_KEY:-/dev/null}" 2>/dev/null || true)
    [ -n "$ROOT" ] && key=${key:-"ssh-ed25519 AAAA-plan-placeholder"}
    put sshd /etc/ssh/fleet_authorized_keys/$LANE_USER 0644 <<<"from=\"$CTRL_IP\",restrict $key fleet-controller"
  else
    # Server: only turn passwords off when the desktop user can still log in by key.
    local u=${SUDO_USER:-kvn} home; home=$(getent passwd "$u" | cut -d: -f6 || true)
    if [ -n "$ROOT" ] || [ -s "$home/.ssh/authorized_keys" ]; then
      put sshd /etc/ssh/sshd_config.d/50-fleet-server.conf 0644 <<'EOF'
# fleet-harden (server): key-only OpenSSH; console login is unaffected.
PasswordAuthentication no
KbdInteractiveAuthentication no
PermitRootLogin prohibit-password
MaxAuthTries 3
LoginGraceTime 20
X11Forwarding no
EOF
    else
      say "sshd: $u has no ~/.ssh/authorized_keys; leaving password auth alone (lockout guard)"
    fi
  fi
  if changed sshd && [ -z "$ROOT" ]; then
    if ! sshd -t; then
      rm -rf /etc/ssh/sshd_config.d && cp -a "$bak/sshd_config.d" /etc/ssh/
      die "sshd config invalid; previous config restored, sshd not reloaded"
    fi
    systemctl reload sshd
  fi
  rm -rf "$bak"
}

step_firewall() {
  [ -z "$ROOT" ] || return 0
  command -v ufw >/dev/null && ufw status | grep -q '^Status: active' || { say "ufw: not active, skipped (enable it: docs/fleet/README.md)"; return 0; }
  ufw default deny incoming >/dev/null; ufw default allow outgoing >/dev/null
  if [ "$MODE" = worker ]; then
    ufw allow in on tailscale0 from "$CTRL_IP" to any port 2222 proto tcp comment fleet-controller-ssh >/dev/null
    # Drop the older any-source rule once the scoped one exists.
    ufw --force delete allow in on tailscale0 to any port 2222 proto tcp >/dev/null 2>&1 || true
    bash "$REPO/scripts/setup-k3s.sh" firewall agent >/dev/null
  else
    bash "$REPO/scripts/setup-k3s.sh" firewall server >/dev/null
  fi
  say "ufw: incoming default deny; cluster and controller ports on tailscale0 only"
}

step_k3s() {
  local unit; unit=$(k3s_unit)
  put k3s-unit /etc/systemd/system/$unit.service.d/50-fleet.conf 0644 <<'EOF'
# fleet-harden: always come back, and be the last thing the OOM killer picks.
[Unit]
StartLimitIntervalSec=0
[Service]
Restart=always
RestartSec=10
OOMScoreAdjust=-900
EOF
  # (No pipe into put: it must run in this shell to record the change.)
  local body a
  body="# fleet-harden: kubelet reservations and eviction (config/fleet/nodes.yaml).
# Pods together can use at most capacity - system - kube reserved; the kubelet
# evicts before the host runs out. '+' appends to config.yaml's list; last wins.
kubelet-arg+:"
  for a in "${KUBELET_ARGS[@]:-}"; do [ -n "$a" ] && body+=$'\n'"  - \"$a\""; done
  put k3s-config /etc/rancher/k3s/config.yaml.d/50-fleet.yaml 0600 <<<"$body"
  [ -z "$ROOT" ] || return 0
  changed k3s-unit && systemctl daemon-reload
  if changed k3s-config || changed k3s-unit; then
    if [ "$MODE" = worker ] || [ "$RESTART_K3S" = 1 ]; then
      say "restarting $unit (running containers keep running)"; systemctl restart "$unit"
    else
      say "k3s server config changed: run again with --restart-k3s when a control-plane blip is ok"
    fi
  fi
}

step_logind() {
  ls /sys/class/power_supply/BAT* >/dev/null 2>&1 || [ -n "$ROOT" ] || return 0
  put logind /etc/systemd/logind.conf.d/50-fleet-worker.conf 0644 <<'EOF'
# fleet-harden (laptop worker): on AC power the lid does not suspend the node.
# On battery the default applies, and `fleet health` cordons a draining node.
[Login]
HandleLidSwitchExternalPower=ignore
HandleLidSwitchDocked=ignore
IdleAction=ignore
EOF
  if changed logind; then sys systemctl reload systemd-logind; fi
}

step_lane_user() {
  [ -z "$ROOT" ] || { step_lane_slice 1001; return 0; }
  if ! id "$LANE_USER" >/dev/null 2>&1; then
    useradd --create-home --home-dir /home/$LANE_USER --shell /bin/bash --user-group "$LANE_USER"
    CHANGED+=(lane-user); say "created user $LANE_USER"
  fi
  passwd -l "$LANE_USER" >/dev/null 2>&1 || true
  # No supplementary groups (docker, wheel, ...): a job must not reach root-equivalent sockets.
  usermod -G "" "$LANE_USER"
  chmod 0700 /home/$LANE_USER
  install -d -m 0700 -o "$LANE_USER" -g "$LANE_USER" /home/$LANE_USER/jobs
  loginctl enable-linger "$LANE_USER"
  step_lane_slice "$(id -u "$LANE_USER")"
}

# Root-owned ceiling for everything agentjob runs (ssh sessions and job scopes).
# IPAddressDeny filters by the cgroup that created the socket: sshd's own socket
# stays in sshd.service, so the controller's ssh connection is unaffected.
step_lane_slice() {
  local uid=$1
  put lane-slice /etc/systemd/system/user-$uid.slice.d/50-fleet-lane.conf 0644 <<EOF
# fleet-harden: limits for the $LANE_USER host-job lane (config/fleet/nodes.yaml).
[Slice]
MemoryMax=$LANE_MEM_MAX
MemorySwapMax=2G
CPUQuota=$LANE_CPU
TasksMax=$LANE_TASKS
CPUWeight=50
IOWeight=50
# Internet yes (package downloads); LAN, tailnet, pod and service ranges no.
IPAddressDeny=10.0.0.0/8 172.16.0.0/12 192.168.0.0/16 100.64.0.0/10 169.254.0.0/16 fc00::/7 fe80::/10
IPAddressAllow=localhost
EOF
  if changed lane-slice; then sys systemctl daemon-reload; fi
}

step_updates() {
  put updates /etc/systemd/system/fleet-updates.service 0644 <<'EOF'
# fleet-harden: Arch/CachyOS has no security-only channel and unattended
# `pacman -Syu` is unsafe, so this only downloads and reports. Apply with
# `fleet update <node>` (docs/fleet/README.md). Never reboots.
[Unit]
Description=fleet: download pending package updates and report them
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
Nice=19
IOSchedulingClass=idle
ExecStart=/usr/local/lib/fleet/updates-check
EOF
  put updates /etc/systemd/system/fleet-updates.timer 0644 <<'EOF'
[Unit]
Description=fleet: daily update download and report
[Timer]
OnCalendar=daily
RandomizedDelaySec=2h
Persistent=true
[Install]
WantedBy=timers.target
EOF
  put updates /usr/local/lib/fleet/updates-check 0755 <<'EOF'
#!/usr/bin/env bash
# Writes /var/lib/fleet/updates.json: pending count, kernel/k3s-relevant packages, reboot hint.
set -uo pipefail
install -d -m 0755 /var/lib/fleet
out=/var/lib/fleet/updates.json; tmp=$(mktemp)
if command -v checkupdates >/dev/null; then
  # -d downloads into the cache (its progress goes to stdout); -n then lists from
  # the same private sync db without syncing again. Neither touches the system db.
  checkupdates -d >/dev/null 2>&1
  list=$(checkupdates -n 2>/dev/null | grep -- ' -> '); rc=$?   # grep: 0 = updates, 1 = none
  [ $rc -eq 1 ] && rc=0
  tool=checkupdates
elif command -v apt-get >/dev/null; then
  apt-get update -qq >/dev/null 2>&1; apt-get -s -o Debug::NoLocking=1 dist-upgrade >/dev/null 2>&1
  list=$(apt list --upgradable 2>/dev/null | sed 1d); rc=0; tool=apt
else
  list=""; rc=127; tool=none
fi
pending=$(printf '%s\n' "$list" | grep -c . || true)
kernel=$(printf '%s\n' "$list" | grep -cE '^(linux|linux-lts|linux-cachyos|linux-cachyos-lts|linux-image-[^ ]+) ' || true)
security=$(printf '%s\n' "$list" | grep -cE '^(openssh|openssl|glibc|sudo|systemd|tailscale)[ /-]' || true)
reboot=false; [ -d "/usr/lib/modules/$(uname -r)" ] || reboot=true
printf '{"checked_at":%s,"tool":"%s","rc":%s,"pending":%s,"kernel_pending":%s,"core_pending":%s,"reboot_required":%s}\n' \
  "$(date +%s)" "$tool" "$rc" "$pending" "$kernel" "$security" "$reboot" >"$tmp"
install -m 0644 "$tmp" "$out"; rm -f "$tmp"
EOF
  if [ -z "$ROOT" ]; then
    changed updates && systemctl daemon-reload
    systemctl enable --now fleet-updates.timer >/dev/null 2>&1
    [ -s /var/lib/fleet/updates.json ] || systemctl start --no-block fleet-updates.service
  fi
}

step_probe() {
  put probe /usr/local/bin/fleet-node-probe 0755 <"$REPO/scripts/fleet-node-probe"
  sys install -d -m 0755 /var/lib/fleet
}

main() {
  local cmd=${1:-}; shift || true
  case $cmd in
    plan) MODE=${1:-worker}; shift || true; ROOT=$(mktemp -d); CTRL_IP=${CTRL_IP:-100.64.0.1} ;;
    worker|server) MODE=$cmd; [ "$(id -u)" -eq 0 ] || die "run as root" ;;
    *) sed -n '2,25p' "$0"; exit 2 ;;
  esac
  parse "$@"
  if [ -z "$ROOT" ]; then
    # Keep a local record even when the ssh session that started us goes away.
    exec > >(tee -a /var/log/fleet-harden.log) 2>&1
    say "fleet-harden $MODE $(date -Is)"
  fi
  if [ "$MODE" = worker ]; then [ -n "$CTRL_IP" ] || die "--controller-ip is required"; fi
  step_journald; step_sshd; step_firewall; step_k3s; step_logind; step_probe; step_updates
  [ "$MODE" = worker ] && step_lane_user
  if [ -n "$ROOT" ]; then say "plan rendered in $ROOT:"; (cd "$ROOT" && find . -type f | sort); fi
  if [ ${#CHANGED[@]} -eq 0 ]; then say "no changes"; else say "changed: $(printf '%s\n' "${CHANGED[@]}" | sort -u | paste -sd' ')"; fi
}

main "$@"
